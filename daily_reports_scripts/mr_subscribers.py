import vertica_python
import subprocess
import json
import logging
import smtplib
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from credential_manager import get_vertica_config


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
            server.starttls()
            server.sendmail(email_config["sender"], [email_config["error_to"]], msg.as_string())
        logging.info("Failure email sent successfully.")
    except Exception as e:
        logging.error("Error sending failure email: %s", e)


def load_config(config_file):
    """Load configuration from JSON file."""
    with open(config_file) as f:
        return json.load(f)


def extract_emails(row):
    """Extract and deduplicate emails from row data."""
    emails = set()
    for col in ["email_to", "email_cc", "email_bcc"]:
        raw = row.get(col)
        if raw:
            for e in raw.replace(";", ",").split(","):
                e = e.strip()
                if e:
                    emails.add(e)
    return sorted(emails)


def run_subscriber_extraction(config_file, log_filename, cust_name):
    """
    Main function to extract subscribers and trigger endcustomer reports.
    
    Args:
        config_file: Path to config.json
        log_filename: Path to log file
        cust_name: Customer name to process
    """
    setup_logging(log_filename)

    try:
        config = load_config(config_file)
        email_config = config["email"]

        # Load Vertica credentials from secure path
        conn_info = get_vertica_config(config)

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
               extracts_schema
        FROM medicalcommon.email_subscribers
        WHERE report_type = 'Daily MR Report' 
          AND cust_name = '{cust_name}';
        """

        try:
            with vertica_python.connect(**conn_info) as connection:
                cur = connection.cursor()
                cur.execute(query_subscribers)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                
                logging.info(f"Found {len(results)} subscriber records for customer: {cust_name}")
        except Exception as db_err:
            logging.error("Database connection/query error: %s", db_err)
            send_failure_email(email_config, f"Database connection/query failed:\n{db_err}")
            return  # stop execution if Vertica fails

        for row in results:
            emails = extract_emails(row)
            extracts_schema = row.get("extracts_schema", "")
            email_subject = row.get("email_subject", "")
            report_type = row.get("report_type", "")
            mps = row.get("mps", "")
            bc2r_schema = mps.replace("/", "_") + "_bc2r"

            logging.info(
                "Fetched emails for report %s, MPS %s, cust_name %s: %s",
                report_type, mps, cust_name, ", ".join(emails)
            )

            for email in emails:
                try:
                    logging.info(
                        "Calling mr_endcustomer.py for mps:%s, email:%s, schema:%s, subject:%s, cust:%s",
                        mps, email, extracts_schema, email_subject, cust_name
                    )
                    
                    # Get the directory where this script is located
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    endcustomer_script = os.path.join(script_dir, "mr_endcustomer.py")
                    
                    subprocess.run(
                        ["python3", endcustomer_script, email, bc2r_schema, extracts_schema, email_subject, cust_name],
                        check=True
                    )
                    logging.info(f"Successfully processed report for {email}")
                except subprocess.CalledProcessError as e:
                    logging.error("Error running mr_endcustomer.py for (%s, %s): %s", cust_name, email, e)
                    send_failure_email(email_config, f"mr_endcustomer.py failed for {cust_name}, {email}\n{e}")
                except FileNotFoundError as e:
                    logging.error("mr_endcustomer.py script not found: %s", e)
                    send_failure_email(email_config, f"mr_endcustomer.py not found in {script_dir}\n{e}")

    except FileNotFoundError as e:
        logging.error("Configuration or credential file not found: %s", e)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        logging.error("Configuration error: %s", e)
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.error("Main error: %s", e)
        try:
            config = load_config(config_file)
            send_failure_email(config["email"], str(e))
        except:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 mr_subscribers.py <cust_name>")
        sys.exit(1)

    cust_name = sys.argv[1]
    config_file = "config.json"
    log_filename = "EmailSubscribers.log"
    
    run_subscriber_extraction(config_file, log_filename, cust_name)