"""
CT Subscribers Script - Reads credentials from AWS Secrets Manager
Uses secret paths defined in config.json (no hardcoded values)
"""

import vertica_python
import subprocess
import json
import logging
import smtplib
import sys
import boto3
from botocore.exceptions import ClientError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def setup_logging(log_filename):
    logging.basicConfig(
        filename=log_filename,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


def send_failure_email(email_config, error_message):
    """Send failure notification email using config file values."""
    subject = "Email Subscriber Script Failure Alert!!"
    body = f"An error occurred:\n\n{error_message}"

    msg = MIMEMultipart()
    msg["From"] = email_config["sender"]
    msg["To"] = email_config["error_to"]
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"]) as server:
            server.sendmail(email_config["sender"], [email_config["error_to"]], msg.as_string())
        logging.info("Failure email sent successfully.")
    except Exception as e:
        logging.error("Error sending failure email: %s", e)


def load_config(config_file):
    """Load configuration from JSON file."""
    with open(config_file) as f:
        return json.load(f)


def get_credentials_from_aws(secret_name, region="us-east-1"):
    """Fetch credentials from AWS Secrets Manager."""
    try:
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        creds = json.loads(response["SecretString"])
        logging.info(f"Successfully fetched credentials from AWS Secrets Manager: {secret_name}")
        return creds
    except ClientError as e:
        logging.error(f"Unable to retrieve secret {secret_name}: {e}")
        raise
    except Exception as e:
        logging.error(f"Error fetching credentials from AWS: {e}")
        raise


def extract_emails(row):
    """Extract unique emails from row."""
    emails = []
    seen = set()
    for col in ["email_to", "email_cc", "email_bcc"]:
        raw = row.get(col)
        if raw:
            for e in raw.replace(";", ",").split(","):
                e = e.strip()
                if e and e not in seen:
                    seen.add(e)
                    emails.append(e)
    return emails 


def run_subscriber_extraction(config_file, log_filename, cust_name):
    """Main function to extract subscribers and run endcustomer script."""
    setup_logging(log_filename)

    try:
        config = load_config(config_file)
        db_config = config["vertica"]
        email_config = config["email"]

        # Read from config.json (not hardcoded)
        db_host = db_config["ums_host"]
        db_port = db_config["port"]  # ← Port from config, not AWS
        vertica_secret_name = db_config.get("credentials_path")
        report_type = db_config.get("ct_report_type")  # ← Report type from config
        
        if not vertica_secret_name:
            raise ValueError("Missing 'credentials_path' in config['vertica']")
        if not report_type:
            raise ValueError("Missing 'ct_report_type' in config['vertica']")
        
        logging.info(f"Fetching Vertica credentials from AWS: {vertica_secret_name}")
        logging.info(f"Report type: {report_type}")
        
        # Fetch Vertica credentials from AWS Secrets Manager
        vertica_creds = get_credentials_from_aws(
            secret_name=vertica_secret_name,
            region="us-east-1"
        )

        # Build connection info - Port from config, credentials from AWS
        conn_info = {
            "host": db_host,
            "port": db_port,
            "user": vertica_creds.get("username"),
            "password": vertica_creds.get("password"),
            "database": vertica_creds.get("database", "glassbeam"),
            "autocommit": True,
            "tlsmode": "disable"
        }

        # Query uses report_type from config
        query_subscribers = f"""
        SELECT report_type,
               email_subject,
               email_from,
               email_to,
               email_bcc,
               email_cc,
               email_errorto,
               report_definitionfile,
               SchedulerTaskName,
               mps,
               extracts_schema,
               dashboard_url
        FROM medicalcommon.email_subscribers
        WHERE report_type = '{report_type}'
          AND cust_name = '{cust_name}';
        """

        try:
            with vertica_python.connect(**conn_info) as connection:
                cur = connection.cursor()
                cur.execute(query_subscribers)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as db_err:
            logging.error("Database connection/query error: %s", db_err)
            send_failure_email(email_config, f"Database connection/query failed:\n{db_err}")
            return

        for row in results:
            emails = extract_emails(row)
            extracts_schema = row.get("extracts_schema", "")
            email_subject = row.get("email_subject", "")
            report_type_db = row.get("report_type", "")
            mps = row.get("mps", "")
            bc2r_schema = mps.replace("/", "_") + "_bc2r"
            dashboard_url = row.get("dashboard_url", "")

            logging.info(
                "Fetched emails for report %s, MPS %s, cust_name %s: %s",
                report_type_db, mps, cust_name, ", ".join(emails)
            )

            for email in emails:
                try:
                    logging.info(
                        "Calling ct_endcustomer.py for mps:%s, email:%s, schema:%s, subject:%s, cust:%s",
                        mps, email, extracts_schema, email_subject, cust_name
                    )
                    subprocess.run(
                        ["python3", "/ebs/scrips/daily_reports/ct_endcustomer.py", 
                         email, bc2r_schema, extracts_schema, email_subject, cust_name, dashboard_url],
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    logging.error("Error running ct_endcustomer.py for (%s, %s): %s", cust_name, email, e)
                    send_failure_email(email_config, f"ct_endcustomer.py failed for {cust_name}, {email}\n{e}")

    except Exception as e:
        logging.error("Main error: %s", e)
        try:
            config = load_config(config_file)
            send_failure_email(config["email"], str(e))
        except:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ct_subscribers.py <cust_name>")
        sys.exit(1)

    cust_name = sys.argv[1]
    config_file = "/ebs/scrips/daily_reports/config.json"
    log_filename = "/ebs/scrips/daily_reports/EmailSubscribers.log"
    run_subscriber_extraction(config_file, log_filename, cust_name)
