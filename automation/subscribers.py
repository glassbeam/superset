
#subscibers email
import vertica_python
import subprocess
import json

with open("config.json") as f:
    config = json.load(f)


conn_info = {
    "host": config["vertica"]["host"],
    "port": config["vertica"]["port"],
    "user": config["vertica"]["user"],
    "password": config["vertica"]["password"],
    "database": config["vertica"]["database"],
    "autocommit": True
}

schema = config["vertica"]["schema_subscribers"]
reportname = config["vertica"]["report_type"]
mps = config["vertica"]["mps"]

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
       cust_name
FROM {schema}.email_subscribers
WHERE report_type = '{reportname}' 
  AND mps = '{mps}';
"""


def extract_emails(row):
    emails = set()
    for col in ["email_to", "email_cc", "email_bcc"]:
        raw = row.get(col)
        if raw:
            for e in raw.replace(";", ",").split(","):
                e = e.strip()
                if e:
                    emails.add(e)
    print(emails)
    return sorted(emails)

with vertica_python.connect(**conn_info) as connection:
    cur = connection.cursor()
    cur.execute(query_subscribers)
    columns = [desc[0] for desc in cur.description]

    results = [dict(zip(columns, row)) for row in cur.fetchall()]

    for row in results:
        emails = extract_emails(row)
        for email in emails:
            # Call File 2 for each email
            subprocess.run(["python3", "endcustomer.py", email])


