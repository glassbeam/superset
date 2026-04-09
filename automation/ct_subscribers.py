import vertica_python
import subprocess
import json
import logging
import smtplib
import sys
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
    with open(config_file) as f:
        return json.load(f)


def extract_emails(row):
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
    setup_logging(log_filename)

    try:
        config = load_config(config_file)
        db_config = config["vertica"]
        email_config = config["email"]

        conn_info = {
            "host": db_config["host"],
            "port": db_config["port"],
            "user": db_config["user"],
            "password": db_config["password"],
            "database": db_config["database"],
            "autocommit": True,
            "tlsmode": "disable"
        }

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
        WHERE report_type = 'Daily CT Report' 
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
                        "Calling endcustomer.py for mps:%s, email:%s, schema:%s, subject:%s, cust:%s",
                        mps, email, extracts_schema, email_subject, cust_name
                    )
                    subprocess.run(
                        ["python3", "ct_endcustomer.py", email, bc2r_schema, extracts_schema, email_subject, cust_name],
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    logging.error("Error running endcustomer.py for (%s, %s): %s", cust_name, email, e)
                    send_failure_email(email_config, f"endcustomer.py failed for {cust_name}, {email}\n{e}")

    except Exception as e:
        logging.error("Main error: %s", e)
        send_failure_email(config["email"], str(e))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 subscribers.py <cust_name>")
        sys.exit(1)

    cust_name = sys.argv[1]
    config_file = "config.json"
    log_filename = "EmailSubscribers.log"
    run_subscriber_extraction(config_file, log_filename, cust_name)


