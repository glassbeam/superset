import time
import pytz
import smtplib
import json
import os
from datetime import datetime, timedelta
import vertica_python
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# =======================
# Load config.json
# =======================
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# =======================
# Constants
# =======================
FORCE_RUN_TZ = None  # Force run only for this timezone (set None to disable)
MAX_RETRIES = 3

# =======================
# Fetch configs per source
# =======================
def fetch_timezone_config(source: str):
    if source == "ce":
        query = """
            SELECT timezone,
                   zone,
                   report_time as run_time_utc,
                   report_time,
                   report_run_time,
                   local_time,
                   current_time - interval '1 minute' as curr_time
            FROM (
                SELECT timezone,
                       run_time_utc as report_time,
                       local_time,
                       zone,
                       1 as report_run_time
                FROM canon_common.ce_details_test1
            ) aa
            WHERE report_time::time >= current_time - interval '5 minute'
              AND report_time::time <= current_time + interval '5 minute'
        """
    elif source == "zss":
        query = """
            SELECT DISTINCT  report_time AS run_time_utc, report_time,1 AS report_run_time,local_time
FROM (
    SELECT run_time_utc_szone AS report_time,local_time_szone AS local_time FROM canon_common.zss_details_prod_test
    UNION ALL
    SELECT   run_time_utc AS report_time, local_time_pzone AS local_time FROM canon_common.zss_details_prod_test
) t
            WHERE report_time::time >= current_time - interval '5 minute'
              AND report_time::time <= current_time + interval '5 minute'
        """
    else:
        raise ValueError("Unknown source type")

    configs = []
    try:
        with vertica_python.connect(**config["vertica"]) as connection:
            cur = connection.cursor('dict')
            cur.execute(query)
            for row in cur.fetchall():
                configs.append(dict(row))
    except Exception as e:
        print(f"⚠️ Failed to fetch timezone config for {source}: {e}")
    return configs

# =======================
# Email Utility
# =======================
def send_failure_email(target_table, run_time_utc, error_details):
    sender = config["email"]["sender"]
    recipients = config["email"]["to"]
    cc = config["email"].get("cc", [])
    bcc = config["email"].get("bcc", [])
    smtp_server = config["email"]["smtp_server"]
    smtp_port = config["email"]["smtp_port"]
    subject_prefix = config["email"].get("subject", "[ALERT] Daily Report Job Failed")

    subject = f'Alert!!! {subject_prefix} for "{target_table}"'
    body = f"""
The Canon daily report extract for table {target_table} with run_time_utc {run_time_utc} has failed after {MAX_RETRIES} attempts.

Error details:
{error_details}
"""

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    all_recipients = recipients + cc + bcc

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.sendmail(sender, all_recipients, msg.as_string())
        print(f"📧 Failure email sent for {target_table} at {run_time_utc} to {', '.join(all_recipients)}")
    except Exception as e:
        print(f"❌ Could not send email: {e}")


# =======================
# Logging Job Runs
# =======================
def log_job_run( run_time, extract_start_time, extract_end_time,
                start_time_utc, end_time_utc,start_date_timezone, end_date_timezone, local_time,
                is_failed, error_details, attempt_count, target_table,report_date):
    try:
        with vertica_python.connect(**config["vertica"]) as connection:
            cur = connection.cursor()
            cur.execute("""
                INSERT INTO canon_extracts.daily_report_extract_logs
                ( run_time_utc, extract_start_time, extract_end_time,
                 start_time_utc, end_time_utc,start_date_timezone, end_date_timezone, local_time,
                 is_failed, error_details, attempt_count, target_table,report_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                run_time,
                extract_start_time,
                extract_end_time,
                start_time_utc,
                end_time_utc,
                start_date_timezone, 
                end_date_timezone,
                local_time,
                is_failed,
                error_details,
                attempt_count,
                target_table,
                report_date
            ))
            connection.commit()
            print(f"📝 Log inserted successfully for target table {target_table} at run_time_utc {run_time} to canon_extracts.daily_report_extract_logs table")
    except Exception as e:
        print(f"⚠️ Failed to insert log: {e}")


# =======================
# Safe Job Wrapper
# =======================
def safe_buildDailyReportData(start_date, end_date, run_time,
                              start_time_utc, end_time_utc, start_date_timezone, end_date_timezone, local_time,
                              target_table, report_date):
    attempt = 0
    error_details = None
    success = False
    extract_start_time = datetime.utcnow()

    while attempt < MAX_RETRIES:
        try:
            buildDailyReportData(start_date, end_date,
                             start_date_timezone, end_date_timezone,
                             target_table)
            success = True
            break
        except Exception as e:
            attempt += 1
            error_details = str(e)
            print(f"❌ Attempt {attempt} failed for target table : {target_table} and run_time_utc : {run_time}: {error_details}")
            time.sleep(60)

    extract_end_time = datetime.utcnow()

    if not success:
        send_failure_email(target_table, run_time, error_details)

    # Truncate error_details to 2000 characters to avoid Vertica insert error
    error_details_trunc = (error_details[:1900] + '...') if error_details and len(error_details) > 2000 else error_details

    log_job_run(
        run_time=run_time,
        extract_start_time=extract_start_time,
        extract_end_time=extract_end_time,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        start_date_timezone=start_date_timezone,
        end_date_timezone=end_date_timezone,
        local_time=local_time,
        is_failed=not success,
        error_details=error_details_trunc,
        attempt_count=attempt if not success else 1,
        target_table=target_table,
        report_date=report_date
    )

    return success


# =======================
# Date Range Calculator
# =======================
def get_date_range_for_timezone(cfg, force_run: bool = False):
    run_time_utc = cfg["run_time_utc"]   # from ce_details/zss
    local_time = cfg["local_time"]       # from ce_details/zss

    # --- UTC part ---
    run_h, run_m, run_s = run_time_utc.hour, run_time_utc.minute, run_time_utc.second
    today = datetime.utcnow().date()
    run_dt_utc = datetime(today.year, today.month, today.day, run_h, run_m, run_s)

    end_date_utc = run_dt_utc - timedelta(minutes=30)

    weekday_sql = (datetime.utcnow().isoweekday() % 7) + 1  # Vertica style
    if weekday_sql == 2:  # Monday
        start_date_utc = run_dt_utc - timedelta(hours=72, minutes=30)
        daterange = 72
    else:
        start_date_utc = run_dt_utc - timedelta(hours=24, minutes=30)
        daterange = 24

    run_report = 0 if weekday_sql in (1, 7) else 1

    # --- Local time part (from column, not UTC) ---
    local_h, local_m, local_s = local_time.hour, local_time.minute, local_time.second
    run_dt_local = datetime(today.year, today.month, today.day, local_h, local_m, local_s)

    end_date_local = run_dt_local - timedelta(minutes=30)
    if weekday_sql == 2:
        start_date_local = run_dt_local - timedelta(hours=72, minutes=30)
    else:
        start_date_local = run_dt_local - timedelta(hours=24, minutes=30)

    return {
        "daterange": daterange,
        "runReport": run_report,
        "current_date": datetime.utcnow().strftime("%d, %B"),
        "report_date": start_date_utc.strftime("%d %B"),
        "start_date": start_date_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": end_date_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "start_date_timezone": start_date_local.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date_timezone": end_date_local.strftime("%Y-%m-%d %H:%M:%S"),
    }


# =======================
# Main Report Job
# =======================
def buildDailyReportData(start_date: str, end_date: str,
                         start_date_timezone: str, end_date_timezone: str,
                         target_table: str):
    with vertica_python.connect(**config["vertica"]) as connection:
        cur = connection.cursor()
        print("***********************************")
        print(f"Inside build daily reports for {target_table}...")
        cur.execute(f"TRUNCATE TABLE canon_extracts.{target_table}_temp;")
        print(f"Truncated canon_extracts.{target_table}_temp table sucessfully.....")

        cur.execute(f"""
            INSERT INTO canon_extracts.{target_table}_temp
            SELECT sysid1,
       LISTAGG(value 
               USING PARAMETERS max_length=65000, on_overflow='TRUNCATE') || '<hr>' AS value,sysid1 || alert_level as sorting,
               COALESCE(TO_CHAR(NULLIF('{start_date_timezone}', '')::timestamp, 'YYYY-MM-DD HH24:MI:SS'), '') AS start_date_timezone,
COALESCE(TO_CHAR(NULLIF('{end_date_timezone}', '')::timestamp, 'YYYY-MM-DD HH24:MI:SS'), '') AS end_date_timezone
  from(
SELECT sysid1,alert_level,
       LISTAGG(alert_html 
               USING PARAMETERS max_length=65000, on_overflow='TRUNCATE') AS value
FROM (
  SELECT 
  sysid1,
  alert_level,
  '<div style="font-weight: bold; color: ' || 
      CASE WHEN alert_level = 3 THEN 'red' ELSE 'goldenrod' END || 
      '; font-size: 17px;"> Alert Level ' || alert_level || '</div>'
  ||
  '<div style="font-family: Arial, sans-serif; font-size: 15px; line-height: 1.5; margin-bottom: 10px;">'
  || '<b>' || COALESCE(alert_source,'') || '</b>: ' || COALESCE(alert_comments,'') || '<br>'
  || '<b>Alert Source File:</b><br>' ||
        COALESCE(REPLACE(replace(alert_source_file1,'\\',''), ',', '<br>'),'')
        || CASE WHEN alert_source_file1 IS NOT NULL AND alert_source_file1 <> '' THEN '<br>' ELSE '' END
  || '<b>Occurred Time:</b><br>' ||
        CASE 
           WHEN occurred_count > 10 
           THEN to_char(max_occured_time ,'mm/dd/yyyy HH:mi:ss') || '<br>'|| '...' || (occurred_count-2) || ' other occurrences' || '<br>'|| to_char(min_occured_time ,'mm/dd/yyyy HH:mi:ss')
           ELSE REPLACE(occured_time,',','<br>')
        END
        || CASE WHEN occured_time IS NOT NULL OR occurred_count > 0 THEN '<br>' ELSE '' END
  || '<b>Comment File:</b><br>' ||
        COALESCE(comment_file,'') ||
        CASE WHEN comment_file IS NOT NULL AND comment_file <> '' THEN '<br>' ELSE '' END
  || '<b>Maintenance File:</b><br>' ||
        COALESCE(maintenancefile,'') ||
        CASE WHEN maintenancefile IS NOT NULL AND maintenancefile <> '' THEN '<br>' ELSE '' END
  ||  COALESCE(fixs_ka_for_css_url,'') ||
        CASE WHEN fixs_ka_for_css_url IS NOT NULL AND fixs_ka_for_css_url <> '' THEN '<br>' ELSE '' END
  || COALESCE(fixs_ka_for_nss_url,'') ||
        CASE WHEN fixs_ka_for_nss_url IS NOT NULL AND fixs_ka_for_nss_url <> '' THEN '<br>' ELSE '' END
  || '</div>' AS alert_html
  FROM (
  --inner qyery 3 start
    SELECT 
       sysid1,
       alert_level,
       alert_source,
       alert_comments,
       LISTAGG(CASE WHEN rn_alert_source_file1 = 1 THEN alert_source_file1 END USING PARAMETERS max_length = 50000, on_overflow = 'TRUNCATE') AS alert_source_file1,
       LISTAGG(CASE WHEN rn_occurred_time=1 THEN occured_time END USING PARAMETERS max_length = 50000, on_overflow = 'TRUNCATE') AS occured_time,
       LISTAGG(CASE WHEN rn_maint = 1 THEN maintenancefile_link END USING PARAMETERS max_length = 50000, on_overflow = 'TRUNCATE') AS maintenancefile,
       LISTAGG(CASE WHEN rn_comm  = 1 THEN comment_file_link END USING PARAMETERS max_length = 50000, on_overflow = 'TRUNCATE') AS comment_file,
       COUNT(occured_time)  AS occurred_count,
       MIN(evt_ts)    AS min_occured_time,
       MAX(evt_ts)    AS max_occured_time,
       LISTAGG(CASE 
            WHEN fixs_ka_for_css_url IS NOT NULL and fixs_ka_for_css_url<> '' and rn_fixs_ka_for_css_url  = 1 THEN   '<a href="' || fixs_ka_for_css_url || '" target="_blank">FIXS Article for CE and ZSS</a>' 
            ELSE NULL 
        END USING PARAMETERS max_length = 5000, on_overflow = 'TRUNCATE') as fixs_ka_for_css_url,        
      LISTAGG(CASE 
            WHEN fixs_ka_for_nss_url IS NOT NULL and fixs_ka_for_nss_url<> '' and rn_fixs_ka_for_nss_url  = 1 THEN   '<a href="' || fixs_ka_for_nss_url || '" target="_blank">FIXS Article for NSS</a>' 
            ELSE NULL 
        END  USING PARAMETERS max_length = 5000, on_overflow = 'TRUNCATE') as fixs_ka_for_nss_url    
       FROM (
      SELECT
        a.*,
        CASE 
          WHEN comment_file IS NOT NULL AND comment_file <> '' THEN
            '<a href="https://intranet.cmsu.com/sites/service/digitalsvc/CommentFiles/File.html?name=' 
            || comment_file || '" target="_blank">' || comment_file || '</a>'
          ELSE ''
        END AS comment_file_link,
        CASE 
          WHEN maintenancefile IS NOT NULL AND maintenancefile <> '' THEN
            '<a href="https://intranet.cmsu.com/sites/service/digitalsvc/CommentFiles/File.html?name=' 
            || maintenancefile || '" target="_blank">' || maintenancefile || '</a>'
          ELSE ''
        END AS maintenancefile_link,
        ROW_NUMBER() OVER (
          PARTITION BY sysid1, alert_level, alert_source, alert_comments, comment_file
          ORDER BY evt_ts
        ) AS rn_comm,
        ROW_NUMBER() OVER (
          PARTITION BY sysid1, alert_level, alert_source, alert_comments, maintenancefile
          ORDER BY evt_ts
        ) AS rn_maint,
        ROW_NUMBER() OVER (
          PARTITION BY sysid1, alert_level, alert_source, alert_comments, alert_source_file1
          ORDER BY evt_ts
        ) AS rn_alert_source_file1,
           ROW_NUMBER() OVER (
          PARTITION BY sysid1, alert_level, alert_source, alert_comments, fixs_ka_for_css_url
          ORDER BY evt_ts
        ) AS rn_fixs_ka_for_css_url,
        ROW_NUMBER() OVER (
          PARTITION BY sysid1, alert_level, alert_source, alert_comments, fixs_ka_for_nss_url
          ORDER BY evt_ts
        ) AS rn_fixs_ka_for_nss_url,
        ROW_NUMBER() OVER (
          PARTITION BY sysid1, alert_level, alert_source, alert_comments, occured_time
          ORDER BY evt_ts
        ) AS rn_occurred_time
          FROM (select * from 
(
---------------------------CT----------------
select distinct sysid1,alert_level,nvl(replace(alert_comments,'"',''),'') as alert_comments,
substr(alertsourcefile,instr(alertsourcefile,'\\',1,3)+1) as alert_source_file1,
nvl(alert_source,'') as alert_source,comment_file,evt_ts,to_char(evt_ts ,'mm/dd/yyyy HH:mi:ss') as occured_time,null as fixs_ka_for_nss_url,null as fixs_ka_for_css_url ,maintenancefile from canon_canon_prod_bc2r.event_tbl_alert_history alert,
(select distinct bundle_id,obs_ts from canon_canon_prod_bc2r.bundle where filetype ilike 'AlertHistory%' and obs_ts >= '{start_date}'::timestamp
and obs_ts <  '{end_date}'::timestamp and modality='CT'
)bundle
where alert.bundle_id = bundle.bundle_id
and evt_date_str :: timestamp >= current_timestamp - interval '7 days'  
and obs_ts >= '{start_date}'::timestamp
and obs_ts <  '{end_date}'::timestamp
and alert_level in (3,2)
and alertid :: varchar  not in (select distinct alert_id from canon_common.excludeAlert where modality = 'CT')
union all
--------------------------MR----------------
select distinct sysid1,alert_level,nvl(replace(alert_comments,'"',''),'') as alert_comments,
substr(alertsourcefile,instr(alertsourcefile,'\\',1,3)+1) as alert_source_file1,
nvl(alert_source,'') as alert_source,comment_file,evt_ts,to_char(evt_ts ,'mm/dd/yyyy HH:mi:ss') as occured_time,url_cloud as "FIXS KA Cloud URL",url_potal as "FIXS KA Portal URL",maintenancefile from canon_canon_prod_bc2r.event_tbl_alert_history_mr alert,
(select distinct bundle_id,obs_ts from canon_canon_prod_bc2r.bundle where filetype ilike 'AlertHistory%' 
and obs_ts >= '{start_date}'::timestamp
and obs_ts <  '{end_date}'::timestamp and modality='MR'
)bundle
where alert.bundle_id = bundle.bundle_id
and evt_date_str :: timestamp >= current_timestamp - interval '7 days'  
and obs_ts >= '{start_date}'::timestamp
and obs_ts <  '{end_date}'::timestamp
and alert_level in (3,2)
and alertid :: varchar  not in (select distinct alert_id from canon_common.excludeAlert where modality = 'MR')
union all
---------------------------VL----------------
select distinct sysid1,alert_level,nvl(replace(alert_comments,'"',''),'') as alert_comments,
substr(alertsourcefile,instr(alertsourcefile,'\\',1,3)+1) as alert_source_file1,
nvl(alert_source,'') as alert_source,comment_file,evt_ts,to_char(evt_ts ,'mm/dd/yyyy HH:mi:ss') as occured_time,substr(url_nss,1,instr(url_nss,'?'))||URI_PERCENT_ENCODE(substr(url_nss,instr(url_nss,'?')+1)) as fixs_ka_for_nss_url,
substr(url_ce,1,instr(url_ce,'?'))||URI_PERCENT_ENCODE(substr(url_ce,instr(url_ce,'?')+1)) as fixs_ka_for_css_url,maintenancefile  from canon_canon_prod_bc2r.event_tbl_alert_history_vl alert,
(select distinct bundle_id,obs_ts from canon_canon_prod_bc2r.bundle where filetype ilike 'AlertHistory%' and obs_ts >= '{start_date}'::timestamp
and obs_ts <  '{end_date}'::timestamp and modality='VL'
)bundle
where alert.bundle_id = bundle.bundle_id
and evt_date_str :: timestamp >= current_timestamp - interval '7 days'  
and obs_ts >= '{start_date}'::timestamp
and obs_ts <  '{end_date}'::timestamp
and alert_level in (3,2)
and alertid :: varchar  not in (select distinct alert_id from canon_common.excludeAlert where modality = 'VL')
)aa
order by alert_source,alert_comments,evt_ts desc) a
     order by alert_level desc,evt_ts desc,occured_time desc
      --inner query 2 end    
    ) aa_dedup
    GROUP BY sysid1, alert_level, alert_source, alert_comments
      --inner query 3 end  
      ) main 
order by alert_level desc
--
) main1
GROUP BY sysid1,alert_level
order by alert_level desc )qq
group by sysid1,sorting;
        """)
        print(f"Inserted into {target_table}_temp")

        cur.execute(f"TRUNCATE TABLE canon_extracts.{target_table};")
        cur.execute(f"""
            INSERT INTO canon_extracts.{target_table}
            SELECT * FROM canon_extracts.{target_table}_temp;
        """)
        connection.commit()
        print(f"Inserted into canon_extracts.{target_table}_temp table sucessfully.....")

# =======================
# Scheduler Loop (updated)
# =======================
def scheduler_loop():
    print("📅 Scheduler started...")
    last_run = {}  # key = (run_time_utc, target_table)

    sources = [
        {"source": "ce", "target_table": "daily_report_data_ce"},
        {"source": "zss", "target_table": "daily_report_data_zss"},
    ]

    while True:
        utc_now = datetime.utcnow().replace(second=0, microsecond=0)
        print("\n⏰ Current UTC time:", utc_now)

        for src in sources:
            source = src["source"]
            target_table = src["target_table"]

            # Fetch run_time_utc configs from CE/ZSS tables
            configs = fetch_timezone_config(source)
            print(f"🔍 {source}: {len(configs)} run_time_utc entries ready")

            for cfg in configs:
                run_time = cfg["run_time_utc"]

                # Skip if already triggered successfully
                if last_run.get((run_time, target_table)):
                    print(f"⏳ Already triggered {target_table} for run_time_utc {run_time}")
                    continue

                print(f"✅ Triggering canon_extracts.{target_table} report for run_time_utc {run_time}")
                run_time_info = get_date_range_for_timezone(cfg)
                print(f"""
                        *******************************
                        Report dates for target table: {target_table}
                        run_time_utc: {run_time}
                        start_date_utc: {run_time_info['start_date']}
                        end_date_utc: {run_time_info['end_date']}
                        start_date_timezone: {run_time_info['start_date_timezone']}
                        end_date_timezone: {run_time_info['end_date_timezone']}
                        report_date: {run_time_info['report_date']}
                        *******************************
                    """)

                try:
                    safe_buildDailyReportData(
                        start_date=run_time_info["start_date"],
                        end_date=run_time_info["end_date"],
                        run_time=run_time,
                        start_time_utc=run_time_info["start_date"],
                        end_time_utc=run_time_info["end_date"],
                        start_date_timezone=run_time_info["start_date_timezone"],
                        end_date_timezone=run_time_info["end_date_timezone"],
                        local_time=cfg["local_time"],
                        target_table=target_table,
                        report_date=run_time_info["report_date"]
                    )
                    # Only mark as triggered if no exception
                    last_run[(run_time, target_table)] = True
                    print(f"✅ Successfully triggered {target_table} for run_time_utc {run_time}")

                except Exception as e:
                    print(f"❌ Failed to build {target_table} for run_time_utc {run_time}: {e}")
                    send_failure_email(e, target_table, run_time)

        print("🛌 Sleeping for 60 seconds...\n")
        time.sleep(60)



# =======================
# Main
# =======================
if __name__ == "__main__":
    scheduler_loop()
