# audit_sections.py
# Audit struktur HTML tblAppealCaseSec, tblTrialCourtInfoSec, gvActivities
# untuk fix parser Tab 2, 4, dan 9
# Jalankan: python audit_sections.py

from curl_cffi import requests
from bs4 import BeautifulSoup
import sqlite3, re

DB_PATH  = "scraper.db"
BASE_URL = "https://appellateinquiry.jud.ct.gov"

def main():
    # Ambil beberapa CRN valid dari DB
    conn = sqlite3.connect(DB_PATH)
    crns = [r[0] for r in conn.execute("""
        SELECT crn FROM cases
        WHERE scrape_status='done'
        ORDER BY CAST(crn AS INTEGER)
        LIMIT 5
    """).fetchall()]
    conn.close()

    if not crns:
        crns = ["1", "2", "3", "72391", "72392"]

    session = requests.Session(impersonate="chrome120")

    for crn in crns[:3]:
        url  = f"{BASE_URL}/CaseDetail.aspx?CRN={crn}&Type=Counsel"
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            print(f"CRN {crn}: HTTP {resp.status_code}")
            continue

        if "not available" in resp.text.lower():
            print(f"CRN {crn}: sealed")
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        print(f"\n{'='*60}")
        print(f"CRN {crn}")
        print(f"{'='*60}")

        # ── Tab 2: tblAppealCaseSec ──────────────────────────────
        print("\n[tblAppealCaseSec RAW HTML]")
        tbl = soup.find("table", {"id": "tblAppealCaseSec"})
        if tbl:
            print(str(tbl)[:2000])
        else:
            print("NOT FOUND")

        # ── Tab 4: tblTrialCourtInfoSec ──────────────────────────
        print("\n[tblTrialCourtInfoSec RAW HTML]")
        tbl4 = soup.find("table", {"id": "tblTrialCourtInfoSec"})
        if tbl4:
            print(str(tbl4)[:2000])
        else:
            print("NOT FOUND")

        # ── Tab 9: gvActivities (3 rows) ────────────────────────
        print("\n[gvActivities — first 3 rows RAW]")
        act = soup.find("table", {"id": "gvActivities"})
        if act:
            for row in act.find_all("tr")[:4]:
                print(str(row)[:500])
                print("---")
        else:
            print("NOT FOUND")

        import time
        time.sleep(2)

if __name__ == "__main__":
    main()
