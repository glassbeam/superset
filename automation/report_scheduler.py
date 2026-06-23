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

CONFIG_PATH = "/ebs/scrips/daily_reports/config.json"

with open(CONFIG_PATH, "r") as config_file:
    config = json.load(config_file)

VERTICA = config["vertica"]

VERTICA_CONFIG = {
    "host": VERTICA["ums_host"],
    "port": VERTICA["port"],
    "user": VERTICA["user"],
    "password": VERTICA["password"],
    "database": VERTICA["database"],
    "autocommit": True
}

PATHS = config["paths"]

BASE_SCRIPT_PATH = PATHS["base_script_path"]
LOG_FILE = PATHS["log_file"]
LOCK_FILE = PATHS["lock_file"]

SCHEDULER = config["scheduler"]

PYTHON_PATH = SCHEDULER["python_path"]
DEFAULT_TIMEOUT = SCHEDULER["default_timeout_seconds"]
MAX_WORKERS = SCHEDULER.get("max_parallel_jobs", 5)

SERVER_NAME = socket.gethostname()

REPORT_MAPPINGS = {
    VERTICA["ct_report_type"]: "ct_subscribers.py",
    VERTICA["mr_report_type"]: "mr_subscribers.py",
    VERTICA["cathlab_report_type"]: "cathlab_subscribers.py",
    VERTICA["system_alert_report_type"]: "SA_subscribers.py"
}

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logging.info("=================================================")
logging.info("MASTER SCHEDULER STARTED")
logging.info("=================================================")

lock_file = open(LOCK_FILE, "w")

try:
    fcntl.flock(
        lock_file,
        fcntl.LOCK_EX | fcntl.LOCK_NB
    )
except IOError:
    logging.warning(
        "Another Scheduler Instance Already Running"
    )
    sys.exit(0)


def get_connection():
    """Establish and return a Vertica connection."""
    return vertica_python.connect(
        **VERTICA_CONFIG
    )


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
            stdout_log,
            stderr_log,
            error_message
        )
    )



# MAIN SCHEDULER INITIALIZATION


try:
    master_connection = get_connection()
    master_cursor = master_connection.cursor()
    logging.info("Connected To Vertica Successfully")

except Exception as e:
    logging.error(f"Vertica Connection Failed: {str(e)}")
    sys.exit(1)

# Reset stale running jobs (jobs that have been running for > 2 hours)
try:
    RESET_QUERY = """i
    UPDATE medicalcommon.dailyreport_scheduler_config_test
    SET
        is_running = FALSE,
        updated_at = CURRENT_TIMESTAMP
    WHERE is_running = TRUE
    AND started_at < CURRENT_TIMESTAMP - INTERVAL '2 HOURS'
    """

    master_cursor.execute(RESET_QUERY)
    logging.info("Reset Stale Running Jobs Successfully")

except Exception as e:
    logging.error(f"Failed Resetting Stale Jobs: {str(e)}")


# FETCH ACTIVE JOBS DUE FOR EXECUTION


FETCH_QUERY = """
SELECT
    job_id,
    customer_name,
    report_type,
    cron_expression,
    script_arguments,
    retry_count,
    max_retries,
    next_run_time
FROM medicalcommon.dailyreport_scheduler_config_test
WHERE status = 'ACTIVE'
AND is_running = FALSE
AND mps NOT IN (
    SELECT DISTINCT mps
    FROM operational_extract.exclude_mps_bdls
)
"""

master_cursor.execute(FETCH_QUERY)
all_jobs = master_cursor.fetchall()

jobs = []
current_time = datetime.now()

# Filter jobs that are due for execution
for job in all_jobs:
    (
        job_id,
        customer_name,
        report_type,
        cron_expression,
        script_arguments,
        retry_count,
        max_retries,
        next_run_time
    ) = job

    try:
        # Execute if next_run_time is NULL or has passed
        if next_run_time is None or next_run_time <= current_time:
            jobs.append(job)

    except Exception as e:
        logging.error(
            f"Failed checking schedule for Job {job_id}: {str(e)}"
        )

logging.info(f"Total Runnable Jobs Found: {len(jobs)}")


# JOB EXECUTION FUNCTION



def execute_job(job):
    """
    Execute a single scheduled job.
    
    Args:
        job: Tuple containing job details from database
    """
    (
        job_id,
        customer_name,
        report_type,
        cron_expression,
        script_arguments,
        retry_count,
        max_retries,
        next_run_time
    ) = job

    connection = None
    cursor = None
    process = None
    stdout = ""
    stderr = ""
    start_time = None
    end_time = None
    duration = 0
    process_id = None

    try:
        logging.info(f"Starting Job: {customer_name} (Job ID: {job_id})")

        # Check if max retries exceeded
        if retry_count >= max_retries:
            logging.warning(
                f"Max Retries Exceeded for Job {job_id}: {customer_name}"
            )
            return

        # Validate report type exists
        if report_type not in REPORT_MAPPINGS:
            raise Exception(f"Invalid Report Type: {report_type}")

        # Get script path
        script_name = REPORT_MAPPINGS[report_type]
        script_full_path = os.path.join(BASE_SCRIPT_PATH, script_name)

        # Validate script exists
        if not os.path.exists(script_full_path):
            raise Exception(f"Script Not Found: {script_full_path}")

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
            text=True
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



# MAIN EXECUTION WITH THREAD POOL


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


# CLEANUP AND SHUTDOWN

try:
    master_cursor.close()
    master_connection.close()

except Exception as e:
    logging.error(f"Error closing master connection: {str(e)}")

logging.info("MASTER SCHEDULER COMPLETED SUCCESSFULLY")
logging.info("=================================================")
