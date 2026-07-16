import sys
import os
import time
import smtplib
import vertica_python
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoAlertPresentException
import json
import traceback
from datetime import datetime
import glob
import shutil
import logging

from credential_manager import get_vertica_config, get_superset_credentials

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOGO_PATH = os.path.join(BASE_DIR, "glassbeamLogo.png")

# Load configuration
with open(CONFIG_PATH) as f:
    config = json.load(f)

# Load Superset credentials from secure path
try:
    superset_creds = get_superset_credentials(config)
    SUPERSET_USER = superset_creds["username"]
    SUPERSET_PASSWORD = superset_creds["password"]
except Exception as e:
    logging.error(f"Failed to load Superset credentials: {e}")
    sys.exit(1)

# Chrome configuration from config file
CHROME_DRIVER_PATH = config["chrome"]["driver_path"]
DOWNLOAD_BASE_DIR = config["chrome"]["download_dir"]
LOGIN_SERVER = config["chrome"]["loginserver"]
SUPERSET_LOGIN_URL = config["superset"]["login_url"]

# Email configuration from config file
EMAIL_SENDER = config["email"]["sender"]
SMTP_SERVER = config["email"]["smtp_server"]
SMTP_PORT = config["email"]["smtp_port"]
EMAIL_CC = config["email"]["cc"]
EMAIL_BCC = config["email"]["bcc"]
EMAIL_ERROR_TO = config["email"]["error_to"]

# Load Vertica credentials from secure path
try:
    conn_info = get_vertica_config(config)
except Exception as e:
    logging.error(f"Failed to load Vertica credentials: {e}")
    sys.exit(1)

conn = None
driver = None
wait = None


def get_connection():
    """Establish and return Vertica connection."""
    return vertica_python.connect(**conn_info)


def send_error_notification(failed_email, error_message, exception=None):
    """Send error notification email ONLY to EMAIL_ERROR_TO (internal)."""
    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"[ERROR] Report Failure for {failed_email}"
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_ERROR_TO

        body = f"""
Failed to generate/send report for {failed_email}.

Error:
{error_message}

{traceback.format_exc() if exception else ""}
"""
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.send_message(msg, from_addr=EMAIL_SENDER, to_addrs=[EMAIL_ERROR_TO])
        logging.info(f"[INFO] Error notification sent to {EMAIL_ERROR_TO}")
    except Exception as notify_err:
        logging.warning(f"[WARN] Failed to notify error: {notify_err}")


def wait_for_download(path, timeout=40):
    """Wait until a PNG/JPG file appears in the download path."""
    end = time.time() + timeout
    while time.time() < end:
        files = glob.glob(os.path.join(path, "*.png")) + glob.glob(os.path.join(path, "*.jpg"))
        if files:
            return max(files, key=os.path.getmtime)
        time.sleep(1)
    raise TimeoutError("Download did not complete in time")


def get_dashboard_id(conn, report_type, system_count, extracts_schema):
    """Fetch dashboard ID based on report type and system count."""
    query = f"""
    SELECT dashboard_id
    FROM MEDICALCOMMON.DASHBOARD_MAPPING
    WHERE report_type = '{report_type}'
      AND {system_count} BETWEEN min_systems AND max_systems
      AND enabled = 1
    LIMIT 1;
    """

    try:
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchone()

        if result:
            return result[0]
        else:
            # fallback → highest range
            fallback_query = f"""
            SELECT dashboard_id
            FROM MEDICALCOMMON.DASHBOARD_MAPPING
            WHERE report_type = '{report_type}'
              AND enabled = 1
              AND min_systems <= (SELECT COUNT(*) FROM {extracts_schema}.mr_sensor_report)
              AND max_systems >= (SELECT COUNT(*) FROM {extracts_schema}.mr_sensor_report);
            """

            cur = conn.cursor()
            cur.execute(fallback_query)
            result = cur.fetchone()
            if result:
                return result[0]
            else:
                raise Exception(f"No dashboard mapping found for {report_type}")
    except Exception as e:
        logging.error(f"Error fetching dashboard ID: {e}")
        send_error_notification("system", f"Dashboard lookup failed: {e}")
        raise


def check_data_availability(schema):
    """Check if data is available in the schema."""
    try:
        query = f"""
        SELECT COUNT(*) 
        FROM {schema}.mr_sensor_report
        """
        cur = conn.cursor()
        cur.execute(query)
        return cur.fetchone()[0]
    except Exception as e:
        logging.error(f"Data availability check failed: {e}")
        send_error_notification("system", "Data availability check failed", e)
        return 0


def get_serials_for_email(conn, email, extracts_schema):
    """Fetch serial numbers associated with an email."""
    try:
        query_serials = f"""
        SELECT DISTINCT serial_number
        FROM {extracts_schema}.endcustomer_serial_mapping
        WHERE ',' || sub_group_name || ',' ILIKE (
            SELECT DISTINCT '%,' || end_customer || ',%'
            FROM ums.user
            WHERE email ILIKE '{email}'
            LIMIT 1
        );
        """
        cur = conn.cursor()
        cur.execute(query_serials)
        serials = [row[0] for row in cur.fetchall()]
        logging.info(f"Found {len(serials)} serials for {email}")
        return serials

    except Exception as e:
        logging.error(f"Serial lookup failed for {email}: {e}")
        send_error_notification(email, "Vertica query/connection failed", e)
        raise


def setup_driver(download_dir):
    """Create one Chrome driver (headless) and log in once."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    try:
        service = Service(CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 30)

        logging.info(f"[INIT] Chrome driver initialized")
        
        driver.get(SUPERSET_LOGIN_URL)
        logging.info(f"[LOGIN] Navigating to {SUPERSET_LOGIN_URL}")
        
        wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(SUPERSET_USER)
        driver.find_element(By.NAME, "password").send_keys(SUPERSET_PASSWORD)
        driver.find_element(By.TAG_NAME, "form").submit()

        try:
            WebDriverWait(driver, 3).until(EC.alert_is_present())
            alert = driver.switch_to.alert
            logging.info(f"[Alert after login] {alert.text}")
            alert.accept()
        except (TimeoutException, NoAlertPresentException):
            logging.info("No alert after login")

        wait.until(EC.url_contains("welcome"))
        logging.info("[LOGIN] Successfully logged into Superset")
        
    except Exception as e:
        logging.error(f"Superset login failed: {e}")
        send_error_notification("ALL", "Superset login failed", e)
        if driver:
            driver.quit()
        raise

    return driver, wait


def process_email(driver, wait, serial_str, email, extracts_schema, bc2r_schema, email_subject, cust_name, system_count):
    """Process email and download report dashboard image."""
    username = cust_name.strip()
    user_download_dir = os.path.join(DOWNLOAD_BASE_DIR, username)

    try:
        if os.path.exists(user_download_dir):
            shutil.rmtree(user_download_dir)
        os.makedirs(user_download_dir, exist_ok=True)
        logging.info(f"[INIT] Created folder for {username}: {user_download_dir}")

        driver.command_executor._commands["send_command"] = (
            "POST", "/session/$sessionId/chromium/send_command"
        )
        params = {
            'cmd': 'Page.setDownloadBehavior',
            'params': {'behavior': 'allow', 'downloadPath': user_download_dir}
        }
        driver.execute("send_command", params)

        dashboard_id = get_dashboard_id(conn, "Daily MR Report", system_count, extracts_schema)

        base_url = config["superset"]["mr_dashboard_base_url"]

        if serial_str:
            dashboard_url = (
                f"{base_url}/{dashboard_id}/"
                f"?schema={extracts_schema}&bc2r_schema={bc2r_schema}&sysid={serial_str}"
            )
        else:
            dashboard_url = (
                f"{base_url}/{dashboard_id}/"
                f"?schema={extracts_schema}&bc2r_schema={bc2r_schema}"
            )

        logging.info(f"[OPEN] Dashboard for {email}: {dashboard_url}")
        driver.get(dashboard_url)
        
        try:
            WebDriverWait(driver, 3).until(EC.alert_is_present())
            alert = driver.switch_to.alert
            logging.info(f"[Alert after opening dashboard] {alert.text}")
            alert.accept()
        except (TimeoutException, NoAlertPresentException):
            pass

        time.sleep(10)

        menu_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[@aria-label='Menu actions trigger']")))
        menu_btn.click()

        download_menu = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//span[text()='Download']/ancestor::div[@role='menuitem']")))
        download_menu.click()

        download_image = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//li[@role='menuitem']//span[contains(text(), 'Download as Image')]")))
        download_image.click()

        downloaded_image = wait_for_download(user_download_dir, timeout=40)

        folder_name = os.path.basename(os.path.abspath(user_download_dir))
        if folder_name.lower() != username.lower():
            logging.warning(f"[SECURITY WARNING] Folder '{folder_name}' != username '{username}' → Skipping email")
            send_error_notification(email, f"Folder mismatch for {username}")
            return

        if downloaded_image and os.path.exists(downloaded_image):
            logging.info(f"[SUCCESS] Image downloaded for {email}: {downloaded_image}")
            parts = bc2r_schema.split("_")
            mfr, prod = parts[0], parts[1]
            mps = "/".join(parts[:-1])
            send_email_with_image(downloaded_image, email, email_subject, mfr, prod, mps, cust_name)
            logging.info(f"[EMAIL SENT] Successfully sent report to {email} ({username})")
        else:
            send_error_notification(email, "Dashboard image not downloaded")

    except Exception as e:
        logging.error(f"Dashboard processing failed: {e}")
        send_error_notification(email, "Dashboard load or image download failed", e)
        logging.error(f"[ERROR] Failed to process {username}: {e}")

    finally:
        try:
            if os.path.exists(user_download_dir):
                shutil.rmtree(user_download_dir)
                logging.info(f"[CLEANUP] Deleted folder for {username}: {user_download_dir}")
        except Exception as cleanup_err:
            logging.error(f"[CLEANUP ERROR] Could not delete folder {user_download_dir}: {cleanup_err}")


def send_email_with_image(image_path, email_to, email_subject, mfr, prod, mps, cust_name):
    """Send email with attached report image."""
    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = f"{email_subject}"
        msg["From"] = EMAIL_SENDER
        msg["To"] = email_to
        msg["Cc"] = ", ".join(EMAIL_CC)
        
        report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html = f"""<html>
<body style="margin:0; padding:0;">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
<tr>
<td style="padding:20px 0;">
<img src="cid:glassbeamLogo" alt="Glassbeam Logo" width="160" height="60" 
                       style="display:block; max-width:160px; height:auto;">
</td>
</tr>
<tr>
<td align="center">
<img src="cid:image1"
                           alt="Report"
                            width="100%" 
                         style="width:100%; max-width:100%; height:auto; display:block;"> 
<a href="https://www.glassbeam.com" target="_blank">
<img src="{LOGIN_SERVER}/apps/app/img/glassbeam.png?username={email_to};mfr={mfr};prod={prod};app_name={mfr};report_name=Daily_Report_Tube_History.DailyReportCT;report_date={report_date}"
                             alt="Glassbeam Logo"
                             width="100" height="60"
                             style="display:block; max-width:100px; height:auto;">
</a>
</td>
</tr>
</table>
</body>
</html> 
        """
        msg.attach(MIMEText(html, "html"))

        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, "rb") as f:
                logo = MIMEImage(f.read())
                logo.add_header("Content-ID", "<glassbeamLogo>")
                msg.attach(logo)
        else:
            logging.warning(f"Logo file not found at {LOGO_PATH}")

        with open(image_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<image1>")
            img.add_header("Content-Disposition", "inline", filename=os.path.basename(image_path))
            msg.attach(img)

        all_recipients = [email_to] + EMAIL_CC + EMAIL_BCC
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.send_message(msg, from_addr=EMAIL_SENDER, to_addrs=all_recipients)

        logging.info(f"Email sent to {email_to}")

        # Log to database
        insert_sql = """
        INSERT INTO glassbeam.report_emails_log
        (mps, cust_name, report_type, email_subject, email_sent_to, report_date, report_name)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        """
        values = (mps, cust_name, "Daily MR Report", f" {email_subject}", ",".join(all_recipients), "Daily MR Report")

        try:
            cur = conn.cursor()
            cur.execute(insert_sql, values)
        except Exception as e:
            logging.error(f"Vertica insert failed: {e}")
            send_error_notification("system", "Vertica insert failed", e)

    except Exception as e:
        logging.error(f"Email sending failed: {e}")
        send_error_notification("system", "Email sending failed", e)
        raise


def send_zero_system_alert(user_email, schema):
    """Send alert when no systems found for user."""
    msg = f"""
No systems found for user: {user_email}

Also, no data available in:
{schema}.mr_sensor_report

Report not generated.
"""
    send_error_notification(user_email, msg)


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python3 mr_endcustomer.py <email> <bc2r_schema> <extracts_schema> <email_subject> <cust_name>")
        sys.exit(1)

    email = sys.argv[1]
    bc2r_schema = sys.argv[2]
    extracts_schema = sys.argv[3]
    email_subject = sys.argv[4]
    cust_name = sys.argv[5]

    try:
        conn = get_connection()
        driver, wait = setup_driver(DOWNLOAD_BASE_DIR)
        serial_list = get_serials_for_email(conn, email, extracts_schema)
        system_count = len(serial_list)

        serial_str = ",".join(serial_list) if serial_list else ""

        if not serial_list:
            logging.info(f"No serials found for {email} → using base dashboard")
            send_zero_system_alert(email, extracts_schema)
        else:
            process_email(
                driver, wait, serial_str, email,
                extracts_schema, bc2r_schema,
                email_subject, cust_name,
                system_count
            )

    except Exception as e:
        logging.error(f"Critical error: {e}")
        sys.exit(1)
    finally:
        try:
            if conn:
                conn.close()
            if driver:
                driver.quit()
        except Exception:
            pass