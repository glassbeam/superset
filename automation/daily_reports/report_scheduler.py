import os
import sys
import json
import socket
import logging
import traceback
import subprocess
import fcntl
import boto3
from botocore.exceptions import ClientError

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import vertica_python
from croniter import croniter

CONFIG_PATH = "/ebs/scrips/daily_reports/config.json"

with open(CONFIG_PATH, "r") as config_file:
    config = json.load(config_file)


def get_credentials_from_aws(secret_name, region="us-east-1"):
    """Fetch credentials from AWS Secrets Manager."""
    try:
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        creds = json.loads(response["SecretString"])
        logging.info(f"Successfully fetched credentials from AWS: {secret_name}")
        return creds
    except ClientError as e:
        logging.error(f"Unable to retrieve secret {secret_name}: {e}")
        raise
    except Exception as e:
        logging.error(f"Error fetching credentials from AWS: {e}")
        raise


# Get host and port from config
VERTICA_HOST = config["vertica"]["ums_host"]
VERTICA_PORT = config["vertica"]["port"]

# Fetch Vertica credentials from AWS Secrets Manager
vertica_secret_name = config["vertica"].get("credentials_path", "stage/vert-ui/creds")
VERTICA_CREDS = get_credentials_from_aws(
    secret_name=vertica_secret_name,
    region="us-east-1"
)

VERTICA_CONFIG = {
    "host": VERTICA_HOST,
    "port": VERTICA_PORT,  # Port from config, not AWS
    "user": VERTICA_CREDS.get("username"),
    "password": VERTICA_CREDS.get("password"),
    "database": VERTICA_CREDS.get("database", config["vertica"].get("database", "glassbeam")),
    "autocommit": True,
    "tlsmode": "disable"
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
    config["vertica"]["ct_report_type"]: "ct_subscribers.py",
    config["vertica"]["mr_report_type"]: "mr_subscribers.py",
    config["vertica"]["cathlab_report_type"]: "cathlab_subscribers.py",
    config["vertica"]["system_alert_report_type"]: "SA_subscribers.py"
}


# ============================================================================
# INITIALIZE DIRECTORIES AND LOGGING
# ============================================================================

def ensure_directory_exists(directory_path, description=""):
    """
    Ensure a directory exists. Create it if it doesn't.
    
    Args:
        directory_path: Path to the directory
        description: Human-readable description for logging
    
    Returns:
        True if successful, False otherwise
    """
    try:
        if not os.path.exists(directory_path):
            print(f"[INIT] Creating directory: {directory_path}")
            os.makedirs(directory_path, mode=0o755, exist_ok=True)
            print(f"[INIT] ✓ Directory created: {directory_path}")
        else:
            print(f"[INIT] Directory exists: {directory_path}")
        
        # Verify directory is writable
        if not os.access(directory_path, os.W_OK):
            print(f"[WARN] Directory exists but NOT writable: {directory_path}")
            return False
        
        return True
    
    except PermissionError as e:
        print(f"[ERROR] Permission denied creating directory {directory_path}: {e}")
        return False
    except OSError as e:
        print(f"[ERROR] Failed to create directory {directory_path}: {e}")
        return False


def initialize_logging():
    """Initialize logging after ensuring log directory exists."""
    log_dir = os.path.dirname(LOG_FILE)
    
    if not ensure_directory_exists(log_dir, "log directory"):
        print(f"[WARN] Could not ensure log directory. Logs may fail.")
    
    try:
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s"
        )
        print(f"[INIT] ✓ Logging initialized: {LOG_FILE}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to initialize logging: {e}")
        return False


def ensure_lock_file_ready():
    """
    Ensure lock file directory exists and is writable.
    Creates directory if needed.
    
    Returns:
        True if lock file can be created, False otherwise
    """
    lock_dir = os.path.dirname(LOCK_FILE)
    
    # If lock file path has no directory (e.g., "scheduler.lock"), use current dir
    if not lock_dir:
        lock_dir = os.getcwd()
        print(f"[INIT] Lock file in current directory: {os.getcwd()}")
    
    print(f"[INIT] === LOCK FILE SETUP ===")
    print(f"[INIT] Lock file path: {LOCK_FILE}")
    print(f"[INIT] Lock directory: {lock_dir}")
    
    # Ensure directory exists
    if not ensure_directory_exists(lock_dir, "lock directory"):
        print(f"[ERROR] Cannot create lock directory: {lock_dir}")
        return False
    
    # Try to create a test lock file to verify we can write
    try:
        test_lock_path = os.path.join(lock_dir, ".lock_test")
        with open(test_lock_path, "w") as f:
            f.write("test")
        os.remove(test_lock_path)
        print(f"[INIT] ✓ Lock directory is writable")
        return True
    except Exception as e:
        print(f"[ERROR] Cannot write to lock directory {lock_dir}: {e}")
        return False


# ============================================================================
# SETUP LOGGING AND LOCK FILE
# ============================================================================

print("\n" + "="*80)
print("[START] Report Scheduler Initialization")
print("="*80)

# Initialize logging
if not initialize_logging():
    print("[WARN] Logging failed, continuing anyway...")

# Ensure lock file directory is ready
if not ensure_lock_file_ready():
    print("[ERROR] Lock file directory not ready!")
    sys.exit(1)

logging.info("=================================================")
logging.info("MASTER SCHEDULER STARTED")
logging.info("=================================================")
logging.info(f"Lock file: {LOCK_FILE}")
logging.info(f"Log file: {LOG_FILE}")


# ============================================================================
# ACQUIRE LOCK
# ============================================================================

try:
    print(f"[INIT] Attempting to create/acquire lock file: {LOCK_FILE}")
    lock_file = open(LOCK_FILE, "w")
    print(f"[INIT] ✓ Lock file opened")
    
except IOError as e:
    print(f"[ERROR] Cannot open lock file: {e}")
    logging.error(f"Cannot open lock file {LOCK_FILE}: {e}")
    sys.exit(1)

try:
    print(f"[INIT] Acquiring exclusive lock...")
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print(f"[INIT] ✓ Lock acquired successfully")
    logging.info("Lock acquired successfully")
    
except IOError:
    print(f"[WARN] Another Scheduler Instance Already Running")
    logging.warning("Another Scheduler Instance Already Running")
    sys.exit(0)


# ============================================================================
# MAIN SCHEDULER CODE
# ============================================================================

def get_connection():
    """Establish and return a Vertica connection."""
    return vertica_python.connect(**VERTICA_CONFIG)


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
    print(f"[INIT] ✓ Connected to Vertica")

except Exception as e:
    print(f"[ERROR] Vertica Connection Failed: {str(e)}")
    logging.error(f"Vertica Connection Failed: {str(e)}")
    sys.exit(1)

# Reset stale running jobs (jobs that have been running for > 2 hours)
try:
    RESET_QUERY = """
    UPDATE medicalcommon.dailyreport_scheduler_config
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
FROM medicalcommon.dailyreport_scheduler_config
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
        UPDATE medicalcommon.dailyreport_scheduler_config
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
            UPDATE medicalcommon.dailyreport_scheduler_config
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
                UPDATE medicalcommon.dailyreport_scheduler_config
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
                UPDATE medicalcommon.dailyreport_scheduler_config
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

print(f"\n[MAIN] === JOB EXECUTION ===")
print(f"[MAIN] Found {len(jobs)} jobs to process")
print(f"[MAIN] Max parallel jobs: {MAX_WORKERS}\n")

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
    print("[MAIN] No runnable jobs found")


# CLEANUP AND SHUTDOWN

print(f"\n[SHUTDOWN] === CLEANUP ===")

try:
    master_cursor.close()
    master_connection.close()
    print(f"[SHUTDOWN] ✓ Database connections closed")

except Exception as e:
    logging.error(f"Error closing master connection: {str(e)}")
    print(f"[SHUTDOWN] ✗ Error closing connections: {e}")

# Release lock
try:
    fcntl.flock(lock_file, fcntl.LOCK_UN)
    lock_file.close()
    print(f"[SHUTDOWN] ✓ Lock released")
    logging.info("Lock released")
except Exception as e:
    logging.error(f"Error releasing lock: {str(e)}")
    print(f"[SHUTDOWN] ✗ Error releasing lock: {e}")

logging.info("MASTER SCHEDULER COMPLETED SUCCESSFULLY")
logging.info("=================================================")

print(f"\n[DONE] Scheduler completed successfully!")
print("="*80 + "\n")
