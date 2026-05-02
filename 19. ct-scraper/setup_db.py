# setup_db.py — Jalankan SEKALI di awal
# pip install curl_cffi beautifulsoup4 lxml openpyxl pandas
import sqlite3, os

DB_PATH = "scraper.db"
os.makedirs("data/final", exist_ok=True)
os.makedirs("logs", exist_ok=True)

conn = sqlite3.connect(DB_PATH)

conn.execute("""CREATE TABLE IF NOT EXISTS cases (
    crn TEXT PRIMARY KEY,
    docket_no TEXT, case_title TEXT, attorney_name TEXT,
    tc_docket TEXT, filed_date TEXT, status_col TEXT,
    scrape_status TEXT DEFAULT 'pending', scraped_at TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS case_information (
    crn TEXT PRIMARY KEY, docket_no TEXT,
    ac_number TEXT, title TEXT, status TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS appeal_case_info (
    crn TEXT PRIMARY KEY, docket_no TEXT,
    date_filed TEXT, response_due_date TEXT, appeal_by TEXT,
    disposition_method TEXT, argued_date TEXT, disposition_date TEXT,
    submitted_briefs_date TEXT, cite TEXT, panel TEXT,
    petitions_certification TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS cross_appeal (
    crn TEXT PRIMARY KEY, docket_no TEXT,
    field1 TEXT, field2 TEXT, field3 TEXT, field4 TEXT, field5 TEXT,
    raw_text TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS trial_court_info (
    crn TEXT PRIMARY KEY, docket_no TEXT,
    tc_docket_number TEXT, judgment_for TEXT, court TEXT,
    trial_judge TEXT, judgment_date TEXT,
    f1 TEXT, f2 TEXT, f3 TEXT, f4 TEXT, f5 TEXT,
    raw_text TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS party_attorney (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crn TEXT, docket_no TEXT,
    party_name TEXT, party_class TEXT,
    juris_number TEXT, juris_name TEXT,
    attorney_info TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS transcripts_exhibits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crn TEXT, docket_no TEXT,
    col1 TEXT, col2 TEXT, col3 TEXT, col4 TEXT, col5 TEXT,
    link_url TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS preliminary_papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crn TEXT, docket_no TEXT,
    col1 TEXT, col2 TEXT, col3 TEXT, col4 TEXT, col5 TEXT,
    link_url TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS briefs_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crn TEXT, docket_no TEXT,
    col1 TEXT, col2 TEXT, col3 TEXT, col4 TEXT, col5 TEXT,
    link_url TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS case_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crn TEXT, docket_no TEXT,
    activity_date TEXT, activity TEXT, link_url TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crn TEXT, error_type TEXT, error_msg TEXT, timestamp TEXT)""")

conn.commit()
conn.close()
print("✅ scraper.db created")
print("✅ folders: data/final/, logs/")
