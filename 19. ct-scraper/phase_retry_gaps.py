# phase_retry_gaps.py
# Re-scrape CRN yang ter-skip (gaps dan errors)
# Jalankan SETELAH fix_missing.py
# Jalankan: python phase_retry_gaps.py

from curl_cffi import requests
from bs4 import BeautifulSoup
import sqlite3, time, random, re, logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH    = "scraper.db"
BASE_URL   = "https://appellateinquiry.jud.ct.gov"
DETAIL_URL = BASE_URL + "/CaseDetail.aspx?CRN={crn}&Type=Counsel"
WORKERS    = 5
DELAY_MIN  = 1.0
DELAY_MAX  = 2.5
CHUNK_SIZE = 100
LOG_FILE   = "logs/retry_gaps.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Import semua fungsi dari phase_combined
# (copy parsers yang sama)
def txt(el):
    if not el: return ""
    return " ".join(el.get_text(separator=" ").split())

def abslink(href):
    if not href: return ""
    return href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")

def first_link(el):
    if not el: return ""
    a = el if el.name == "a" else el.find("a")
    return abslink(a.get("href","")) if a else ""

def parse_kv(tbl):
    res = {}
    if not tbl: return res
    for row in tbl.find_all("tr"):
        cells = row.find_all(["td","th"])
        if len(cells) >= 2:
            k = txt(cells[0]).rstrip(":").strip()
            v = txt(cells[1]); l = first_link(cells[1])
            if k and v: res[k] = (v, l)
            elif k:
                full = txt(row)
                if ":" in full:
                    p = full.split(":",1)
                    if p[0].strip() and p[1].strip():
                        res[p[0].strip()] = (p[1].strip(), first_link(row))
        elif len(cells) == 1:
            ct = txt(cells[0]); l = first_link(cells[0])
            if ":" in ct:
                p = ct.split(":",1); k,v = p[0].strip(),p[1].strip()
                if k and (v or l): res[k] = (v,l)
    return res

def parse_grid(soup, sec_id, grid_id):
    grid = soup.find("table",{"id":grid_id})
    if not grid:
        sec = soup.find("table",{"id":sec_id})
        if sec: grid = sec.find("table")
    if not grid: return []
    rows = grid.find_all("tr")
    if not rows: return []
    hdrs = [txt(th) or f"Col{i}" for i,th in enumerate(rows[0].find_all(["th","td"]))]
    result = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells: continue
        rd = {}; link = ""
        for i,c in enumerate(cells):
            rd[hdrs[i] if i<len(hdrs) else f"Col{i}"] = txt(c)
            if not link: link = first_link(c)
        rd["__link"] = link
        result.append(rd)
    return result

def parse_case_info(soup):
    el = soup.find("table",{"id":"tblCaseBanner"}) or soup
    raw = el.get_text(separator=" ")
    m = re.search(r"\b(AC\s*\d+|SC\s*\d+)\b", raw)
    ac = re.sub(r"\s+"," ",m.group(0)).strip() if m else ""
    sm = re.search(r"Status[:\s\xa0]+([^\n\r]+?)(?:\s{2,}|Appeal Case|$)", raw)
    st = sm.group(1).strip().rstrip(".") if sm else ""
    title = ""
    if ac:
        ap=raw.find(ac); sp=raw.lower().find("status")
        if ap>=0 and sp>ap:
            title=re.sub(r"\s+"," ",raw[ap+len(ac):sp]).strip()[:400]
    return {"ac_number":ac,"title":title,"status":st[:100]}

def parse_appeal(soup):
    kv=parse_kv(soup.find("table",{"id":"tblAppealCaseSec"}))
    return {
        "date_filed":             kv.get("Date Filed",("",""))[0],
        "response_due_date":      kv.get("Response to Docket Due Date",("",""))[0],
        "appeal_by":              kv.get("Appeal By",("",""))[0],
        "disposition_method":     kv.get("Disposition Method",("",""))[0],
        "argued_date":            kv.get("Argued Date",("",""))[0],
        "disposition_date":       kv.get("Disposition Date",("",""))[0],
        "submitted_briefs_date":  kv.get("Submitted on Briefs Date",("",""))[0],
        "cite":                   kv.get("Cite",("",""))[0],
        "panel":                  kv.get("Panel",("",""))[0],
        "petitions_certification":kv.get("Petition(s) For Certification",("",""))[0],
    }

def parse_trial(soup):
    kv=parse_kv(soup.find("table",{"id":"tblTrialCourtInfoSec"}))
    return {
        "tc_docket_number": kv.get("Docket Number",("",""))[0],
        "judgment_for":     kv.get("Judgment For",("",""))[0],
        "court":            kv.get("Court",("",""))[0],
        "trial_judge":      kv.get("Trial Judge(s)",("",""))[0],
        "judgment_date":    kv.get("Judgment Date",("",""))[0],
        "raw_text":         txt(soup.find("table",{"id":"tblTrialCourtInfoSec"})),
    }

def parse_parties(soup):
    parties=[]
    grid=soup.find("table",{"id":"gvPartyCounsel"})
    if not grid: return parties
    for row in grid.find_all("tr",recursive=False):
        pn=txt(row.find(id=re.compile(r"lblPartyName$")))
        pc=txt(row.find(id=re.compile(r"lblAppealPartyClass$")))
        if not pn and not pc: continue
        cts=row.find_all("table",id=re.compile(r"dlCounsel$"))
        if not cts:
            parties.append({"party_name":pn,"party_class":pc,
                "juris_number":"Self-Represented","juris_name":"","attorney_info":""})
            continue
        for ct in cts:
            jn=re.sub(r"^(?:Juris(?:\s*Number)?[:\s]*)","",
                txt(ct.find(id=re.compile(r"tdJurisNumber$"))),flags=re.I).strip()
            jname=re.sub(r"^(?:Name[:\s]*)","",
                txt(ct.find(id=re.compile(r"tdJurisName$"))),flags=re.I).strip()
            ji=ct.find("table",id=re.compile(r"tblJurisInfo$"))
            ai=txt(ji) if ji else txt(ct)
            parties.append({"party_name":pn,"party_class":pc,
                "juris_number":jn,"juris_name":jname,"attorney_info":ai[:500]})
    return parties

def parse_activities(soup):
    result=[]
    grid=soup.find("table",{"id":"gvActivities"})
    if not grid: return result
    rows=grid.find_all("tr")
    if not rows: return result
    start=1 if any(c.name=="th" for c in rows[0].find_all(["th","td"])) else 0
    for row in rows[start:]:
        cells=row.find_all("td")
        if not cells: continue
        lbl=row.find(id=re.compile(r"lblActivity$"))
        link=first_link(row)
        if len(cells)>=2:
            c0=txt(cells[0])
            if re.match(r"\d{1,2}/\d{1,2}/\d{4}",c0):
                date=c0; act=txt(lbl) if lbl else txt(cells[1])
            else:
                date=""; act=txt(lbl) if lbl else txt(cells[0])
        else:
            c0=txt(cells[0])
            dm=re.match(r"(\d{1,2}/\d{1,2}/\d{4})\s*(.*)",c0,re.DOTALL)
            date=dm.group(1) if dm else ""
            act=dm.group(2).strip() if dm else (txt(lbl) if lbl else c0)
        if act:
            result.append({"activity_date":date,"activity":act,"link_url":link})
    return result

def fetch_crn(crn):
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    session = requests.Session(impersonate="chrome120")
    url = DETAIL_URL.format(crn=crn)
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=25)
            if resp.status_code == 403:
                time.sleep(random.uniform(45,90)); continue
            if resp.status_code == 429:
                time.sleep(180); continue
            if resp.status_code != 200:
                return crn, None, f"http_{resp.status_code}"
            if "not available at this time" in resp.text.lower():
                return crn, None, "sealed"
            soup = BeautifulSoup(resp.text, "lxml")
            ci = parse_case_info(soup)
            if not ci["ac_number"]:
                return crn, None, "no_ac"
            return crn, {
                "crn": str(crn), "case_info": ci,
                "appeal": parse_appeal(soup),
                "trial":  parse_trial(soup),
                "cross":  txt(soup.find("table",{"id":"tblCrossAmendedSec"})),
                "parties":     parse_parties(soup),
                "transcripts": parse_grid(soup,"tblTranscriptSec","gvTranscripts"),
                "prelim":      parse_grid(soup,"tblPrelimPapersSec","gvPrelimPapers"),
                "briefs":      parse_grid(soup,"tblBriefsSec","gvBriefs"),
                "activities":  parse_activities(soup),
            }, "ok"
        except Exception as e:
            time.sleep(5*(attempt+1))
    return crn, None, "max_retries"

def save_all(conn, data):
    crn=data["crn"]; ci=data["case_info"]
    docket=ci["ac_number"] or f"CRN_{crn}"
    now=datetime.now().isoformat()
    conn.execute("INSERT OR IGNORE INTO cases (crn,docket_no,case_title,status_col,scrape_status,scraped_at) VALUES (?,?,?,?,'done',?)",
        (crn,docket,ci["title"],ci["status"],now))
    conn.execute("UPDATE cases SET scrape_status='done',scraped_at=? WHERE crn=?",(now,crn))
    conn.execute("INSERT OR REPLACE INTO case_information (crn,docket_no,ac_number,title,status) VALUES (?,?,?,?,?)",
        (crn,docket,ci["ac_number"],ci["title"],ci["status"]))
    ai=data["appeal"]
    conn.execute("INSERT OR REPLACE INTO appeal_case_info (crn,docket_no,date_filed,response_due_date,appeal_by,disposition_method,argued_date,disposition_date,submitted_briefs_date,cite,panel,petitions_certification) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (crn,docket,ai["date_filed"],ai["response_due_date"],ai["appeal_by"],ai["disposition_method"],ai["argued_date"],ai["disposition_date"],ai["submitted_briefs_date"],ai["cite"],ai["panel"],ai["petitions_certification"]))
    tc=data["trial"]
    conn.execute("INSERT OR REPLACE INTO trial_court_info (crn,docket_no,tc_docket_number,judgment_for,court,trial_judge,judgment_date,raw_text) VALUES (?,?,?,?,?,?,?,?)",
        (crn,docket,tc["tc_docket_number"],tc["judgment_for"],tc["court"],tc["trial_judge"],tc["judgment_date"],tc["raw_text"]))
    conn.execute("INSERT OR REPLACE INTO cross_appeal (crn,docket_no,raw_text) VALUES (?,?,?)",(crn,docket,data["cross"]))
    conn.execute("DELETE FROM party_attorney WHERE crn=?",(crn,))
    for p in data["parties"]:
        conn.execute("INSERT INTO party_attorney (crn,docket_no,party_name,party_class,juris_number,juris_name,attorney_info) VALUES (?,?,?,?,?,?,?)",
            (crn,docket,p["party_name"],p["party_class"],p["juris_number"],p["juris_name"],p["attorney_info"]))
    def sg(tbl,rows):
        conn.execute(f"DELETE FROM {tbl} WHERE crn=?",(crn,))
        for row in rows:
            link=row.pop("__link",""); v=list(row.values())[:5]
            while len(v)<5: v.append("")
            conn.execute(f"INSERT INTO {tbl} (crn,docket_no,col1,col2,col3,col4,col5,link_url) VALUES (?,?,?,?,?,?,?,?)",
                (crn,docket,v[0],v[1],v[2],v[3],v[4],link))
    sg("transcripts_exhibits",data["transcripts"])
    sg("preliminary_papers",data["prelim"])
    sg("briefs_record",data["briefs"])
    conn.execute("DELETE FROM case_activity WHERE crn=?",(crn,))
    for a in data["activities"]:
        conn.execute("INSERT INTO case_activity (crn,docket_no,activity_date,activity,link_url) VALUES (?,?,?,?,?)",
            (crn,docket,a["activity_date"],a["activity"],a["link_url"]))
    conn.commit()

def save_sealed(conn, crn):
    conn.execute("INSERT OR IGNORE INTO cases (crn,scrape_status) VALUES (?,'sealed')",(crn,))
    conn.execute("UPDATE cases SET scrape_status='sealed' WHERE crn=?",(crn,))
    conn.commit()

def main():
    conn = sqlite3.connect(DB_PATH)

    pending = conn.execute(
        "SELECT COUNT(*) FROM cases WHERE scrape_status='pending'"
    ).fetchone()[0]

    if pending == 0:
        print("No pending CRNs. Run fix_missing.py first.")
        conn.close()
        return

    log.info("=" * 60)
    log.info(f"RETRY GAPS — {pending:,} pending CRNs to process")
    log.info(f"Workers: {WORKERS} | ETA: {pending*1.7/WORKERS/3600:.1f}h")
    log.info("=" * 60)

    crn_list = [r[0] for r in conn.execute(
        "SELECT crn FROM cases WHERE scrape_status='pending' ORDER BY CAST(crn AS INTEGER)"
    ).fetchall()]

    valid=0; sealed=0; errors=0; processed=0

    try:
        for chunk_start in range(0, len(crn_list), CHUNK_SIZE):
            chunk = crn_list[chunk_start: chunk_start+CHUNK_SIZE]

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures = {pool.submit(fetch_crn, crn): crn for crn in chunk}
                for future in as_completed(futures):
                    crn, data, status = future.result()
                    processed += 1

                    if status == "ok" and data:
                        save_all(conn, data)
                        valid += 1
                    elif status in ("sealed","no_ac","no_ac_number") or status.startswith("http_"):
                        save_sealed(conn, crn)
                        sealed += 1
                    else:
                        errors += 1

            if processed % 200 == 0:
                db_cases = conn.execute("SELECT COUNT(*) FROM case_information").fetchone()[0]
                parties  = conn.execute("SELECT COUNT(*) FROM party_attorney").fetchone()[0]
                pct = processed / pending * 100
                log.info(f"[{pct:.1f}%] {processed:,}/{pending:,} | Valid:{valid:,} | "
                         f"Sealed:{sealed:,} | DB:{db_cases:,} | Parties:{parties:,}")

    except KeyboardInterrupt:
        log.info("Stopped. Run again to resume.")

    final = conn.execute("SELECT COUNT(*) FROM case_information").fetchone()[0]
    parties_total = conn.execute("SELECT COUNT(*) FROM party_attorney").fetchone()[0]
    log.info("=" * 60)
    log.info(f"RETRY DONE. Valid:{valid:,} | Sealed:{sealed:,} | Errors:{errors}")
    log.info(f"Total DB: {final:,} cases | {parties_total:,} party rows")
    conn.close()

if __name__ == "__main__":
    main()
