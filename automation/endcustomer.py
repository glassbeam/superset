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

with open("config.json") as f:
    config = json.load(f)

CHROME_DRIVER_PATH = config["chrome"]["driver_path"]
DOWNLOAD_DIR = config["chrome"]["download_dir"]

SUPERSET_LOGIN_URL = config["superset"]["login_url"]
DASHBOARD_BASE_URL = config["superset"]["dashboard_base_url"]
SUPERSET_USER = config["superset"]["username"]
SUPERSET_PASSWORD = config["superset"]["password"]

EMAIL_SENDER = config["email"]["sender"]
SMTP_SERVER = config["email"]["smtp_server"]
SMTP_PORT = config["email"]["smtp_port"]
EMAIL_CC = config["email"]["cc"]
EMAIL_BCC = config["email"]["bcc"]
EMAIL_SUBJECT = config["email"]["subject"]

conn_info = {
    "host": config["vertica"]["ums_host"],
    "port": config["vertica"]["port"],
    "user": config["vertica"]["user"],
    "password": config["vertica"]["password"],
    "database": config["vertica"]["database"],
    "autocommit": True
}
EXTRACT_SCHEMA = config["vertica"]["schema_extract"]
BC2R_SCHEMA = config["vertica"]["bc2r_schema"]

# --- Get serials for email ---
def get_serials_for_email(email,extract_schema=EXTRACT_SCHEMA):
    query_serials = f"""
    SELECT DISTINCT serial_number
    FROM {extract_schema}.endcustomer_serial_mapping
    WHERE ',' || sub_group_name || ',' ILIKE (
        SELECT DISTINCT '%,' || end_customer || ',%'
        FROM ums.user
        WHERE email ILIKE '{email}'
        LIMIT 1
    );
    """
    with vertica_python.connect(**conn_info) as connection:
        cur = connection.cursor()
        cur.execute(query_serials)
        return [row[0] for row in cur.fetchall()]

def setup_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    service = Service(CHROME_DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    # --- Login ---
    driver.get(SUPERSET_LOGIN_URL)
    wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(SUPERSET_USER)
    driver.find_element(By.NAME, "password").send_keys(SUPERSET_PASSWORD)
    driver.find_element(By.TAG_NAME, "form").submit()

    # --- Handle alerts immediately ---
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print(f"[⚠️ Alert after login] {alert.text}")
        alert.accept()
    except (TimeoutException, NoAlertPresentException):
        print("[ℹ️] No alert after login")

    # --- Now safely wait for welcome page ---
    wait.until(EC.url_contains("welcome"))

    return driver, wait


def process_email(driver, wait, serial_str, email):
    """Open dashboard, download image, and send email for a given user/serials."""
    # --- Clean old downloads ---
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith(".png") or f.endswith(".jpg"):
            os.remove(os.path.join(DOWNLOAD_DIR, f))

    # --- Build dashboard URL with schema ---
    if serial_str and serial_str.strip():
       if "?" in DASHBOARD_BASE_URL:
          dashboard_url = f"{DASHBOARD_BASE_URL}&schema={EXTRACT_SCHEMA}&bc2r_schema={BC2R_SCHEMA}&sysid={serial_str}"
       else:
          dashboard_url = f"{DASHBOARD_BASE_URL}?schema={EXTRACT_SCHEMA}&bc2r_schema={BC2R_SCHEMA}&sysid={serial_str}"
    else:
       if "?" in DASHBOARD_BASE_URL:
          dashboard_url = f"{DASHBOARD_BASE_URL}&schema={EXTRACT_SCHEMA}&bc2r_schema={BC2R_SCHEMA}"
       else:
          dashboard_url = f"{DASHBOARD_BASE_URL}?schema={EXTRACT_SCHEMA}&bc2r_schema={BC2R_SCHEMA}"

    print(f"Opening dashboard for {email}: {dashboard_url}")
    driver.get(dashboard_url)

    # Handle alert after dashboard load
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print(f"[⚠️ Alert after opening dashboard] {alert.text}")
        alert.accept()
    except (TimeoutException, NoAlertPresentException):
        pass

    time.sleep(30)  # let charts render

    # --- Download as image ---
    menu_btn = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[@aria-label='Menu actions trigger']")))
    menu_btn.click()
    time.sleep(1)

    download_menu = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//span[text()='Download']/ancestor::div[@role='menuitem']")))
    download_menu.click()
    time.sleep(1)

    download_image = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//li[@role='menuitem']//span[contains(text(), 'Download as Image')]")))
    download_image.click()
    time.sleep(10)

    # --- Get latest image ---
    files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith(".png") or f.endswith(".jpg")]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)))
    downloaded_image = os.path.join(DOWNLOAD_DIR, files[-1]) if files else None

    if downloaded_image:
        print(f"✅ Dashboard image downloaded for {email}: {downloaded_image}")
        send_email_with_image(downloaded_image, email)
    else:
        print(f"❌ No image downloaded for {email}")


# --- Send email with image ---
def send_email_with_image(image_path, email_to):
   msg = MIMEMultipart("related")
   msg["Subject"] = "📊 BMI Daily CT Report"
   msg["From"] = EMAIL_SENDER
   msg["To"] = "mahima.panigatti@glassbeam.com"
   msg["Cc"] = ", ".join(EMAIL_CC)

   html = f"""
   <html>
     <body>
       <p>Hello,</p>
       <p>Dashboard report for your devices:</p>
       <img src="cid:image1" style="max-width:100%; height:auto;">
     </body>
   </html>
   """
   msg.attach(MIMEText(html, "html"))

   with open(image_path, "rb") as f:
       img = MIMEImage(f.read())
       img.add_header("Content-ID", "<image1>")
       img.add_header("Content-Disposition", "inline", filename=os.path.basename(image_path))
       msg.attach(img)

   all_recipients = [email_to] + EMAIL_CC + EMAIL_BCC
   with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
       server.send_message(msg, from_addr=EMAIL_SENDER, to_addrs="mahima.panigatti@glassbeam.com")

   print(f"✅ Email sent to {email_to}")
 
# --- MAIN ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ Please provide one or more emails as arguments")
        sys.exit(1)

    driver, wait = setup_driver()  # ✅ login once

    try:
        for email in sys.argv[1:]:
            serial_list = get_serials_for_email(email)

            if not serial_list:
                print(f"⚠️ No serials found for {email} → using base dashboard")
                serial_str = ""   # open dashboard without sysid
            else:
                serial_str = ",".join(serial_list)
                print(f"📌 Email: {email}")
                print(f"   Serial numbers: {serial_str}")

            process_email(driver, wait, serial_str, email)

    finally:
        driver.quit()

