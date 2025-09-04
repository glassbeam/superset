import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage


# 📨 Email Configuration
sender_email = "donotreply@glassbeam.com"
receiver_email = "mahima.panigatti@glassbeam.com"
receiver_emails = [
    "mahima.panigatti@glassbeam.com"
]
subject = "📊 Daily Superset Dashboard"
password = ""  # Optional if your SMTP doesn't need auth

with open("clean_dashboard.html", "r", encoding="utf-8") as f:
    html_content = f.read()

# Suppose you have an image called "logo.png" to embed
with open("canon_logo.png", "rb") as img_file:
    img_data = img_file.read()

# 🏗️ Create Email Object
msg = MIMEMultipart("related")  # Use 'related' to combine HTML + images
msg["Subject"] = subject
msg["From"] = sender_email
msg["To"] = ", ".join(receiver_emails)

# Attach HTML (use <img src="cid:logo_image"> where you want the image)
html_with_img = html_content.replace(
    "###INLINE_IMAGE###",  # placeholder in your HTML
    '<img src="cid:logo_image" alt="Dashboard Logo">'
)
msg.attach(MIMEText(html_with_img, "html"))

# Attach image inline
image = MIMEImage(img_data)
image.add_header("Content-ID", "logo_image")  # CID used in HTML
msg.attach(image)

# 🚀 Send Email
with smtplib.SMTP("smtp-server.ec2-east1.glassbeam.com", 587) as server:
    server.send_message(msg, from_addr=sender_email, to_addrs=receiver_emails)

print("✅ HTML email with inline image sent successfully.")
