import os
import sys
import json
import socket
import logging
import traceback
import subprocess
import fcntl

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import vertica_python
from croniter import croniter

from credential_manager import get_vertica_config

CONFIG_PATH = "/ebs/scripts/daily_reports/config.json"

try:
    with open(CONFIG_PATH, "r") as config_file:
        config = json.load(config_file)
except FileNotFoundError:
    print(f"ERROR: Configuration file not found at {CONFIG_PATH}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"ERROR: Invalid JSON in configuration file: {e}")
    sys.exit(1)

# Load Vertica credentials from secure path
try:
    VERTICA_CONFIG = get_vertica_config(config)
except Exception as e:
    print(f"ERROR: Failed to load Vertica credentials: {e}")
    sys.exit(1)

PATHS = config.get("paths", {})
BASE_SCRIPT_PATH = PATHS.get("base_script_path", "/ebs/scripts/daily_reports")
LOG_FILE = PATHS.get("log_file", "/var/log/daily_reports/scheduler.log")
LOCK_FILE = PATHS.get("lock_file", "/var/run/daily_reports.lock")

SCHEDULER = config.get("scheduler", {})
PYTHON_PATH = SCHEDULER.get("python_path", "/usr/bin/python3")
DEFAULT_TIMEOUT = SCHEDULER.get("default_timeout_seconds", 3600)
MAX_WORKERS = SCHEDULER.get("max_parallel_jobs", 5)

SERVER_NAME = socket.gethostname()

VERTICA_CONFIG_SECTION = config.get("vertica", {})
REPORT_MAPPINGS = {
    VERTICA_CONFIG_SECTION.get("mr_report_type", "Daily MR Report"): "mr_subscribers.py",
    VERTICA_CONFIG_SECTION.get("ct_report_type", "Daily CT Report"): "ct_subscribers.py",
    VERTICA_CONFIG_SECTION.get("cathlab_report_type", "Daily CathLab Report"): "cathlab_subscribers.py",
    VERTICA_CONFIG_SECTION.get("system_alert_report_type", "System Alert Report"): "SA_subscribers.py"
}

# Ensure log directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logging.info("=================================================")
logging.info("MASTER SCHEDULER STARTED")
logging.info("=================================================")
logging.info(f"Server: {SERVER_NAME}")
logging.info(f"Config: {CONFIG_PATH}")
logging.info(f"Max Workers: {MAX_WORKERS}")
logging.info(f"Default Timeout: {DEFAULT_TIMEOUT}s")

lock_file = None
try:
    lock_file = open(LOCK_FILE, "w")
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    logging.info("Lock acquired successfully")
except IOError:
    logging.warning("Another Scheduler Instance Already Running")
    sys.exit(0)
except Exception as e:
    logging.error(f"Error acquiring lock: {e}")
    sys.exit(1)


def get_connection():
    """Establish and return a Vertica connection."""
    try:
        return vertica_python.connect(**VERTICA_CONFIG)
    except Exception as e:
        logging.error(f"Failed to establish Vertica connection: {e}")
        raise


def insert_job_history(
    cursor,
    job_id,
    customer_name,
    report_type,
    cron_expression,
    start_time,
    end_time,
    duration,
    execution_status,
    retry_attempt,
    process_id,
    stdout_log,
    stderr_log,
    error_message
):
    """Insert job execution history into the database."""
    INSERT_HISTORY_QUERY = """
    INSERT INTO medicalcommon.dailyreport_scheduler_job_history
    (
        job_id,
        customer_name,
        report_type,
        cron_expression,
        start_time,
        end_time,
        execution_duration_seconds,
        execution_status,
        retry_attempt,
        server_name,
        process_id,
        stdout_log,
        stderr_log,
        error_message
    )
    VALUES
    (
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s
    )
    """

    cursor.execute(
        INSERT_HISTORY_QUERY,
        (
            job_id,
            customer_name,
            report_type,
            cron_expression,
            start_time,
            end_time,
            int(duration),
            execution_status,
            retry_attempt,
            SERVER_NAME,
            process_id,
            stdout_log[:10000] if stdout_log else "",  # Truncate to prevent overflow
            stderr_log[:10000] if stderr_log else "",
            error_message[:500] if error_message else ""
        )
    )


# ============================================================================
# JOB INSERTION FUNCTIONS
# ============================================================================

def insert_new_job(
    cursor,
    connection,
    job_id,
    customer_name,
    report_type,
    cron_expression,
    script_arguments,
    mps,
    max_retries=3
):
    """
    Insert a new job with properly calculated next_run_time.
    
    Args:
        cursor: Database cursor
        connection: Database connection
        job_id: Unique job identifier
        customer_name: Name of the customer
        report_type: Type of report (must be in REPORT_MAPPINGS)
        cron_expression: Cron expression for scheduling (e.g., "0 08 * * *")
        script_arguments: Arguments to pass to the script
        mps: MPS identifier (e.g., "ps/stanford/prod")
        max_retries: Maximum number of retries (default: 3)
    
    Returns:
        True if successful, False otherwise
    """
    
    try:
        # Validate report type
        if report_type not in REPORT_MAPPINGS:
            logging.error(f"Invalid Report Type: {report_type}")
            return False
        
        # Calculate initial next_run_time using cron expression
        base_time = datetime.now()
        try:
            next_run = croniter(cron_expression.strip(), base_time).get_next(datetime)
        except Exception as e:
            logging.error(f"Invalid cron expression '{cron_expression}': {str(e)}")
            return False
        
        logging.info(f"Calculated next_run_time for Job {job_id}: {next_run}")
        
        # Insert job with calculated next_run_time
        INSERT_JOB_QUERY = """
        INSERT INTO medicalcommon.dailyreport_scheduler_config_test
        (
            job_id,
            customer_name,
            report_type,
            cron_expression,
            script_arguments,
            status,
            retry_count,
            max_retries,
            next_run_time,
            is_running,
            last_run_time,
            last_run_status,
            last_error_message,
            created_at,
            updated_at,
            mps,
            started_at
        )
        VALUES
        (
            %s, %s, %s, %s,
            %s, 'ACTIVE', 0, %s,
            %s, FALSE, NULL, NULL,
            NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
            %s, NULL
        )
        """
        
        cursor.execute(INSERT_JOB_QUERY, (
            job_id,
            customer_name,
            report_type,
            cron_expression,
            script_arguments,
            max_retries,
            next_run,
            mps
        ))
        
        connection.commit()
        
        logging.info(f"Successfully inserted Job {job_id}: {customer_name} (MPS: {mps})")
        logging.info(f"  Report Type: {report_type}")
        logging.info(f"  Cron Expression: {cron_expression}")
        logging.info(f"  Next Run Time: {next_run}")
        
        return True
        
    except Exception as e:
        logging.error(f"Failed to insert job {job_id}: {str(e)}")
        logging.error(traceback.format_exc())
        return False


def insert_jobs_from_list(cursor, connection, jobs_list):
    """
    Insert multiple jobs at once.
    
    Args:
        cursor: Database cursor
        connection: Database connection
        jobs_list: List of dictionaries with job details
    """
    
    success_count = 0
    failed_count = 0
    
    for job in jobs_list:
        try:
            success = insert_new_job(
                cursor=cursor,
                connection=connection,
                job_id=job.get("job_id"),
                customer_name=job.get("customer_name"),
                report_type=job.get("report_type"),
                cron_expression=job.get("cron_expression"),
                script_arguments=job.get("script_arguments"),
                mps=job.get("mps"),
                max_retries=job.get("max_retries", 3)
            )
            
            if success:
                success_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logging.error(f"Error inserting job: {str(e)}")
            failed_count += 1
    
    logging.info(f"Job insertion complete: {success_count} succeeded, {failed_count} failed")
    return success_count, failed_count


# ============================================================================
# FETCH JOBS TO RUN
# ============================================================================

try:
    master_connection = get_connection()
    master_cursor = master_connection.cursor()

    FETCH_JOBS_QUERY = """
    SELECT
        job_id,
        customer_name,
        report_type,
        cron_expression,
        script_arguments,
        status,
        max_retries,
        retry_count,
        is_running,
        last_run_status,
        mps
    FROM medicalcommon.dailyreport_scheduler_config_test
    WHERE status = 'ACTIVE'
      AND next_run_time <= CURRENT_TIMESTAMP
      AND is_running = FALSE
    ORDER BY next_run_time ASC
    LIMIT 100;
    """

    master_cursor.execute(FETCH_JOBS_QUERY)
    columns = [desc[0] for desc in master_cursor.description]
    jobs = [dict(zip(columns, row)) for row in master_cursor.fetchall()]

    logging.info(f"Fetched {len(jobs)} jobs to execute")

except Exception as e:
    logging.error(f"Failed to fetch jobs: {str(e)}")
    jobs = []


# ============================================================================
# JOB EXECUTION FUNCTION
# ============================================================================

def execute_job(job):
    """Execute a single job in a thread."""
    job_id = job["job_id"]
    customer_name = job["customer_name"]
    report_type = job["report_type"]
    cron_expression = job["cron_expression"]
    script_arguments = job["script_arguments"]
    retry_count = job["retry_count"]
    max_retries = job["max_retries"]

    connection = None
    cursor = None
    process = None
    start_time = None
    end_time = None
    duration = 0
    process_id = None
    stdout = ""
    stderr = ""

    try:
        # Check if max retries exceeded
        if retry_count >= max_retries:
            logging.warning(f"Job {job_id} exceeded max retries ({max_retries})")
            connection = get_connection()
            cursor = connection.cursor()
            
            UPDATE_EXHAUSTED_QUERY = """
            UPDATE medicalcommon.dailyreport_scheduler_config_test
            SET
                status = 'DISABLED',
                last_run_status = 'MAX_RETRIES_EXCEEDED',
                last_error_message = 'Job exceeded maximum retry attempts',
                is_running = FALSE,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """
            cursor.execute(UPDATE_EXHAUSTED_QUERY, (job_id,))
            connection.commit()
            return

        # Get script path
        script_name = REPORT_MAPPINGS.get(report_type)
        if not script_name:
            logging.error(f"Unknown report type for job {job_id}: {report_type}")
            return

        script_full_path = os.path.join(BASE_SCRIPT_PATH, script_name)

        # Establish connection for job
        connection = get_connection()
        cursor = connection.cursor()

        # Mark job as running
        UPDATE_RUNNING_QUERY = """
        UPDATE medicalcommon.dailyreport_scheduler_config_test
        SET
            is_running = TRUE,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        cursor.execute(UPDATE_RUNNING_QUERY, (job_id,))
        connection.commit()

        # Build command
        command = [PYTHON_PATH, script_full_path]

        if script_arguments:
            arguments = script_arguments.split()
            command.extend(arguments)

        logging.info(f"Executing Command: {' '.join(command)}")

        # Execute subprocess
        start_time = datetime.now(timezone.utc)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=BASE_SCRIPT_PATH
        )

        try:
            stdout, stderr = process.communicate(timeout=DEFAULT_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(DEFAULT_TIMEOUT, "Job execution timeout")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        process_id = process.pid

        logging.info(f"Job Duration: {duration} Seconds")

        
        # HANDLE SUCCESS CASE
        
        if process.returncode == 0:
            insert_job_history(
                cursor=cursor,
                job_id=job_id,
                customer_name=customer_name,
                report_type=report_type,
                cron_expression=cron_expression,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                execution_status='SUCCESS',
                retry_attempt=retry_count,
                process_id=process_id,
                stdout_log=stdout,
                stderr_log=stderr,
                error_message=None
            )

            # Calculate next run time based on cron expression
            base_time = datetime.now()
            next_run = croniter(
                cron_expression.strip(),
                base_time
            ).get_next(datetime)

            logging.info(
                f"Job={job_id}, Cron='{cron_expression}', NextRun={next_run}"
            )

            # Update job config with success status
            UPDATE_SUCCESS_QUERY = """
            UPDATE medicalcommon.dailyreport_scheduler_config_test
            SET
                last_run_time = CURRENT_TIMESTAMP,
                next_run_time = %s,
                last_run_status = 'SUCCESS',
                last_error_message = NULL,
                retry_count = 0,
                is_running = FALSE,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """

            cursor.execute(UPDATE_SUCCESS_QUERY, (next_run, job_id))
            connection.commit()

            logging.info(f"Job Success: {customer_name}")

        else:
            # Job failed with non-zero exit code
            raise Exception(f"Job failed with exit code {process.returncode}: {stderr}")

    except subprocess.TimeoutExpired as e:
        
        # HANDLE TIMEOUT CASE
        
        if process:
            process.kill()
            try:
                stdout, stderr = process.communicate()
            except Exception:
                pass

        if not end_time:
            end_time = datetime.now(timezone.utc)

        if not duration and start_time:
            duration = (end_time - start_time).total_seconds()

        error_message = f"Job Timeout After {DEFAULT_TIMEOUT} Seconds"

        logging.error(error_message)

        if cursor and connection:
            try:
                insert_job_history(
                    cursor=cursor,
                    job_id=job_id,
                    customer_name=customer_name,
                    report_type=report_type,
                    cron_expression=cron_expression,
                    start_time=start_time,
                    end_time=end_time,
                    duration=duration,
                    execution_status='TIMEOUT',
                    retry_attempt=retry_count,
                    process_id=process.pid if process else None,
                    stdout_log=stdout,
                    stderr_log=stderr,
                    error_message=error_message
                )

                # Exponential backoff for retry: 2^(retry_count+1), max 60 minutes
                retry_delay_minutes = min(2 ** (retry_count + 1), 60)

                UPDATE_TIMEOUT_QUERY = """
                UPDATE medicalcommon.dailyreport_scheduler_config_test
                SET
                    retry_count = retry_count + 1,
                    next_run_time = CURRENT_TIMESTAMP + INTERVAL '%s MINUTE',
                    last_run_status = 'TIMEOUT',
                    last_error_message = %s,
                    is_running = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """

                cursor.execute(UPDATE_TIMEOUT_QUERY, (retry_delay_minutes, error_message, job_id))
                connection.commit()

            except Exception as db_error:
                logging.error(f"Failed to update timeout status: {str(db_error)}")

    except Exception as e:
        
        # HANDLE GENERAL FAILURE CASE
        
        error_message = str(e)

        logging.error(f"Job Failed: {customer_name}")
        logging.error(error_message)
        logging.error(traceback.format_exc())

        if not end_time:
            end_time = datetime.now(timezone.utc)

        if not duration and start_time:
            duration = (end_time - start_time).total_seconds()

        if cursor and connection:
            try:
                insert_job_history(
                    cursor=cursor,
                    job_id=job_id,
                    customer_name=customer_name,
                    report_type=report_type,
                    cron_expression=cron_expression,
                    start_time=start_time,
                    end_time=end_time,
                    duration=duration,
                    execution_status='FAILED',
                    retry_attempt=retry_count,
                    process_id=process_id if process else None,
                    stdout_log=stdout if stdout else "",
                    stderr_log=stderr if stderr else "",
                    error_message=error_message
                )

                # Exponential backoff for retry: 2^(retry_count+1), max 60 minutes
                retry_delay_minutes = min(2 ** (retry_count + 1), 60)

                UPDATE_FAILED_QUERY = """
                UPDATE medicalcommon.dailyreport_scheduler_config_test
                SET
                    retry_count = retry_count + 1,
                    next_run_time = CURRENT_TIMESTAMP + INTERVAL '%s MINUTE',
                    last_run_status = 'FAILED',
                    last_error_message = %s,
                    is_running = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
                """

                cursor.execute(UPDATE_FAILED_QUERY, (retry_delay_minutes, error_message, job_id))
                connection.commit()

            except Exception as db_error:
                logging.error(f"Failed to update failure status: {str(db_error)}")

    finally:
        
        # CLEANUP
        
        try:
            if cursor:
                cursor.close()

            if connection:
                connection.close()

        except Exception as cleanup_error:
            logging.error(f"Error during cleanup: {str(cleanup_error)}")


# ============================================================================
# MAIN EXECUTION WITH THREAD POOL
# ============================================================================

if jobs:
    logging.info(f"Submitting {len(jobs)} jobs to thread pool (max_workers={MAX_WORKERS})")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(execute_job, job) for job in jobs]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Thread Execution Failed: {str(e)}")
                logging.error(traceback.format_exc())

else:
    logging.info("No Runnable Jobs Found")


# ============================================================================
# CLEANUP AND SHUTDOWN
# ============================================================================

try:
    if master_cursor:
        master_cursor.close()
    if master_connection:
        master_connection.close()

except Exception as e:
    logging.error(f"Error closing master connection: {str(e)}")

logging.info("MASTER SCHEDULER COMPLETED SUCCESSFULLY")
logging.info("=================================================")

# Release lock
if lock_file:
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()
    except Exception:
        pass