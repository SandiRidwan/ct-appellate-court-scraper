# phase_combined.py v3
# - Fix: SQLite write lock (thread-safe)
# - Fix: chunked submission agar output langsung muncul
# - Workers fetch parallel, tapi DB write sequential via queue

from curl_cffi import requests
from bs4 import BeautifulSoup
import sqlite3, time, random, re, logging, queue, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_PATH    = "scraper.db"
BASE_URL   = "https://appellateinquiry.jud.ct.gov"
DETAIL_URL = BASE_URL + "/CaseDetail.aspx?CRN={crn}&Type=Counsel"
CRN_START  = 1
CRN_END    = 96470
WORKERS    = 5      # Ubah ke 8 kalau mau lebih cepat (max aman)
DELAY_MIN  = 1.0
DELAY_MAX  = 2.5
CHUNK_SIZE = 100    # Proses 100 CRN sekaligus
REPORT_N   = 100
LOG_FILE   = "logs/combined.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── RESUME ───────────────────────────────────────────────────────────────────
def get_resume_crn(conn):
    # Jika ada pending CRNs, mulai dari yang terendah
    row_pending = conn.execute(
        "SELECT MIN(CAST(crn AS INTEGER)) FROM cases "
        "WHERE scrape_status='pending'"
    ).fetchone()
    if row_pending and row_pending[0]:
        return row_pending[0] - 1  # start = resume + 1

    # Tidak ada pending — resume dari max done/sealed seperti biasa
    row = conn.execute(
        "SELECT MAX(CAST(crn AS INTEGER)) FROM cases "
        "WHERE scrape_status IN ('done','sealed')"
    ).fetchone()
    return row[0] or 0

# ── PARSERS ───────────────────────────────────────────────────────────────────
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
            if k and v:
                res[k] = (v, l)
            elif k:
                full = txt(row)
                if ":" in full:
                    p = full.split(":",1)
                    if p[0].strip() and p[1].strip():
                        res[p[0].strip()] = (p[1].strip(), first_link(row))
        elif len(cells) == 1:
            ct = txt(cells[0]); l = first_link(cells[0])
            if ":" in ct:
                p = ct.split(":",1)
                k,v = p[0].strip(), p[1].strip()
                if k and (v or l): res[k] = (v, l)
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
    el  = soup.find("table",{"id":"tblCaseBanner"}) or soup
    raw = el.get_text(separator=" ")
    m   = re.search(r"\b(AC\s*\d+|SC\s*\d+)\b", raw)
    ac  = re.sub(r"\s+"," ",m.group(0)).strip() if m else ""
    sm  = re.search(r"Status[:\s\xa0]+([^\n\r]+?)(?:\s{2,}|Appeal Case|$)", raw)
    st  = sm.group(1).strip().rstrip(".") if sm else ""
    title = ""
    if ac:
        ap=raw.find(ac); sp=raw.lower().find("status")
        if ap>=0 and sp>ap:
            title=re.sub(r"\s+"," ",raw[ap+len(ac):sp]).strip()[:400]
    # Strip &nbsp literal dan unicode non-breaking space dari status dan title
    st    = st.replace("&nbsp;","").replace("&nbsp","").replace("\xa0","").strip()
    title = title.replace("&nbsp;","").replace("&nbsp","").replace("\xa0","").strip()
    return {"ac_number":ac,"title":title,"status":st[:100]}

def parse_appeal(soup):
    # Data ada di span dengan ID spesifik — bukan format label/value 2-cell
    def sp(id_): return txt(soup.find(id=id_))
    return {
        "date_filed":             sp("lblDateFiled"),
        "response_due_date":      sp("lblResponse2Docket"),
        "appeal_by":              sp("lblAppealBy"),
        "disposition_method":     sp("lblDispMethod"),
        "argued_date":            sp("lblArgSub"),
        "disposition_date":       sp("lblDispDt"),
        "submitted_briefs_date":  sp("lblSubmitDt"),
        "cite":                   sp("lblRescript"),
        "panel":                  sp("lblPanel"),
        "petitions_certification":sp("lblPetition"),
    }

def parse_trial(soup):
    # Data ada di span ID dan nested table dlTCDockets
    def sp(id_): return txt(soup.find(id=id_))

    # TC Docket Number ada di dlTCDockets table sebagai link text
    tc_docket = ""
    dl = soup.find("table", {"id": "dlTCDockets"})
    if dl:
        links = dl.find_all("a")
        tc_docket = ", ".join(a.get_text(strip=True) for a in links if a.get_text(strip=True))

    return {
        "tc_docket_number": tc_docket,
        "judgment_for":     sp("lblJudgementFor"),
        "court":            sp("lblCourt"),
        "trial_judge":      sp("lblTrialJudge"),
        "judgment_date":    sp("lblJudgementdate"),
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
    # Kolom: Activity(0) | Number(1) | Date filed(2) | Initiated By(3) | Description(4) | Action(5) | Action Date(6) | Notice Date(7)
    result=[]
    grid=soup.find("table",{"id":"gvActivities"})
    if not grid: return result
    rows=grid.find_all("tr")
    if not rows: return result
    # Skip header row (has <th> tags)
    start=1 if any(c.name=="th" for c in rows[0].find_all(["th","td"])) else 0
    for row in rows[start:]:
        cells=row.find_all("td")
        if not cells: continue
        # Activity: cell[0] via lblActivity span
        lbl  = row.find(id=re.compile(r"lblActivity$"))
        act  = txt(lbl) if lbl else txt(cells[0]) if cells else ""
        # Date filed: cell[2]
        date = txt(cells[2]).strip() if len(cells) > 2 else ""
        # Description: cell[4] via lblDescription span
        lbl_desc = row.find(id=re.compile(r"lblDescription$"))
        desc = txt(lbl_desc) if lbl_desc else (txt(cells[4]) if len(cells) > 4 else "")
        # Initiated By: cell[3]
        initiated = txt(cells[3]) if len(cells) > 3 else ""
        # Link dari seluruh row
        link = first_link(row)
        if act:
            result.append({
                "activity_date": date,
                "activity":      act,
                "description":   desc,
                "initiated_by":  initiated,
                "link_url":      link,
            })
    return result

# ── FETCH (runs in worker thread) ─────────────────────────────────────────────
def fetch_crn(crn):
    """Fetch dan parse satu CRN. Tidak ada DB write di sini."""
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    session = requests.Session(impersonate="chrome120")
    url = DETAIL_URL.format(crn=crn)

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=25)
            if resp.status_code == 403:
                log.warning(f"CRN {crn}: 403, sleeping 60s...")
                time.sleep(random.uniform(45, 90))
                continue
            if resp.status_code == 429:
                log.warning(f"CRN {crn}: 429 rate limit, sleeping 180s...")
                time.sleep(180)
                continue
            if resp.status_code != 200:
                return crn, None, f"http_{resp.status_code}"
            if "not available at this time" in resp.text.lower():
                return crn, None, "sealed"

            soup = BeautifulSoup(resp.text, "lxml")
            ci   = parse_case_info(soup)
            if not ci["ac_number"]:
                return crn, None, "no_ac"

            return crn, {
                "crn":       str(crn),
                "case_info": ci,
                "appeal":    parse_appeal(soup),
                "trial":     parse_trial(soup),
                "cross":     txt(soup.find("table",{"id":"tblCrossAmendedSec"})),
                "parties":   parse_parties(soup),
                "transcripts": parse_grid(soup,"tblTranscriptSec","gvTranscripts"),
                "prelim":      parse_grid(soup,"tblPrelimPapersSec","gvPrelimPapers"),
                "briefs":      parse_grid(soup,"tblBriefsSec","gvBriefs"),
                "activities":  parse_activities(soup),
            }, "ok"

        except Exception as e:
            log.debug(f"CRN {crn} attempt {attempt+1}: {e}")
            time.sleep(5*(attempt+1))

    return crn, None, "max_retries"

# ── DB WRITE (runs in main thread only — thread safe) ─────────────────────────
def save_all(conn, data):
    crn    = data["crn"]
    ci     = data["case_info"]
    docket = ci["ac_number"] or f"CRN_{crn}"
    now    = datetime.now().isoformat()

    conn.execute("""INSERT OR IGNORE INTO cases
        (crn,docket_no,case_title,status_col,scrape_status,scraped_at)
        VALUES (?,?,?,?,'done',?)""",
        (crn,docket,ci["title"],ci["status"],now))
    conn.execute("UPDATE cases SET scrape_status='done',scraped_at=? WHERE crn=?",(now,crn))

    conn.execute("""INSERT OR REPLACE INTO case_information
        (crn,docket_no,ac_number,title,status) VALUES (?,?,?,?,?)""",
        (crn,docket,ci["ac_number"],ci["title"],ci["status"]))

    ai=data["appeal"]
    conn.execute("""INSERT OR REPLACE INTO appeal_case_info
        (crn,docket_no,date_filed,response_due_date,appeal_by,disposition_method,
         argued_date,disposition_date,submitted_briefs_date,cite,panel,petitions_certification)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (crn,docket,ai["date_filed"],ai["response_due_date"],ai["appeal_by"],
         ai["disposition_method"],ai["argued_date"],ai["disposition_date"],
         ai["submitted_briefs_date"],ai["cite"],ai["panel"],ai["petitions_certification"]))

    tc=data["trial"]
    conn.execute("""INSERT OR REPLACE INTO trial_court_info
        (crn,docket_no,tc_docket_number,judgment_for,court,trial_judge,judgment_date,raw_text)
        VALUES (?,?,?,?,?,?,?,?)""",
        (crn,docket,tc["tc_docket_number"],tc["judgment_for"],tc["court"],
         tc["trial_judge"],tc["judgment_date"],tc["raw_text"]))

    conn.execute("INSERT OR REPLACE INTO cross_appeal (crn,docket_no,raw_text) VALUES (?,?,?)",
        (crn,docket,data["cross"]))

    # Party — DELETE dulu baru INSERT (sudah di main thread, aman)
    conn.execute("DELETE FROM party_attorney WHERE crn=?", (crn,))
    for p in data["parties"]:
        conn.execute("""INSERT INTO party_attorney
            (crn,docket_no,party_name,party_class,juris_number,juris_name,attorney_info)
            VALUES (?,?,?,?,?,?,?)""",
            (crn,docket,p["party_name"],p["party_class"],
             p["juris_number"],p["juris_name"],p["attorney_info"]))

    def sg(tbl, rows):
        conn.execute(f"DELETE FROM {tbl} WHERE crn=?", (crn,))
        for row in rows:
            link=row.pop("__link","")
            v=list(row.values())[:5]
            while len(v)<5: v.append("")
            conn.execute(f"""INSERT INTO {tbl}
                (crn,docket_no,col1,col2,col3,col4,col5,link_url)
                VALUES (?,?,?,?,?,?,?,?)""",
                (crn,docket,v[0],v[1],v[2],v[3],v[4],link))

    sg("transcripts_exhibits", data["transcripts"])
    sg("preliminary_papers",   data["prelim"])
    sg("briefs_record",        data["briefs"])

    conn.execute("DELETE FROM case_activity WHERE crn=?", (crn,))
    for a in data["activities"]:
        conn.execute("""INSERT INTO case_activity
            (crn,docket_no,activity_date,activity,link_url)
            VALUES (?,?,?,?,?)""",
            (crn, docket,
             a.get("activity_date",""),
             # Gabungkan activity + description + initiated_by jadi satu field kaya
             " | ".join(filter(None, [
                 a.get("activity",""),
                 a.get("description",""),
                 ("By: " + a["initiated_by"]) if a.get("initiated_by","").strip() else ""
             ])),
             a.get("link_url","")))

    conn.commit()

def save_sealed(conn, crn):
    conn.execute("INSERT OR IGNORE INTO cases (crn,scrape_status) VALUES (?,'sealed')",(crn,))
    conn.execute("UPDATE cases SET scrape_status='sealed' WHERE crn=?",(crn,))
    conn.commit()

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    # DB connection di main thread saja
    conn   = sqlite3.connect(DB_PATH)

    # Cek apakah ada pending CRNs di DB (mode re-scrape)
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM cases WHERE scrape_status='pending'"
    ).fetchone()[0]

    if pending_count > 0:
        # MODE RE-SCRAPE: ambil semua pending CRN dari DB
        log.info("=" * 60)
        log.info(f"RE-SCRAPE MODE — {pending_count:,} pending CRNs in DB")
        log.info(f"Workers: {WORKERS} | ETA: {pending_count*1.7/WORKERS/3600:.1f}h")
        log.info("Ctrl+C anytime — auto-resume")
        log.info("=" * 60)
        crn_list = [str(r[0]) for r in conn.execute(
            "SELECT crn FROM cases WHERE scrape_status='pending' "
            "ORDER BY CAST(crn AS INTEGER)"
        ).fetchall()]
        total = len(crn_list)
    else:
        # MODE FRESH: iterasi CRN sequential
        resume = get_resume_crn(conn)
        start  = max(CRN_START, resume + 1)
        total  = CRN_END - start + 1
        log.info("=" * 60)
        log.info(f"COMBINED SCRAPER v3 — CRN {start:,} to {CRN_END:,}")
        log.info(f"Range: {total:,} | Workers: {WORKERS} | "
                 f"ETA: {total*1.7/WORKERS/3600:.1f}h")
        log.info("Ctrl+C anytime — auto-resume dari CRN terakhir")
        log.info("=" * 60)
        crn_list = list(range(start, CRN_END+1))

    valid=0; sealed=0; errors=0; processed=0

    try:
        for chunk_start in range(0, len(crn_list), CHUNK_SIZE):
            chunk = crn_list[chunk_start: chunk_start+CHUNK_SIZE]

            # Workers hanya FETCH — tidak ada DB write di thread
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures = {pool.submit(fetch_crn, crn): crn for crn in chunk}

                for future in as_completed(futures):
                    crn, data, status = future.result()
                    processed += 1

                    # DB write di main thread — THREAD SAFE
                    if status == "ok" and data:
                        save_all(conn, data)
                        valid += 1
                    elif status in ("sealed", "no_ac", "no_ac_number"):
                        # no_ac = CRN ada tapi bukan case page — treat as sealed
                        save_sealed(conn, crn)
                        sealed += 1
                    elif status.startswith("http_"):
                        # HTTP error non-fatal — skip
                        save_sealed(conn, crn)
                        sealed += 1
                    else:
                        # max_retries = genuine network error
                        errors += 1
                        log.warning(f"CRN {crn}: {status}")

            # Report setiap chunk
            if processed % REPORT_N == 0:
                db_cases = conn.execute(
                    "SELECT COUNT(*) FROM case_information"
                ).fetchone()[0]
                parties = conn.execute(
                    "SELECT COUNT(*) FROM party_attorney"
                ).fetchone()[0]
                pct = processed / total * 100
                log.info(
                    f"[{pct:.1f}%] Done:{processed:,}/{total:,} | "
                    f"Valid:{valid:,} | Sealed:{sealed:,} | "
                    f"Errors:{errors} | DB_cases:{db_cases:,} | "
                    f"Parties:{parties:,}"
                )

    except KeyboardInterrupt:
        log.info("Stopped by user. Run again to auto-resume.")

    final = conn.execute("SELECT COUNT(*) FROM case_information").fetchone()[0]
    parties_total = conn.execute("SELECT COUNT(*) FROM party_attorney").fetchone()[0]
    log.info("=" * 60)
    log.info(f"DONE. Valid:{valid:,} | Sealed:{sealed:,} | Errors:{errors}")
    log.info(f"DB: {final:,} cases | {parties_total:,} party rows")
    log.info("Next: python phase3_build_excel.py")
    conn.close()

if __name__ == "__main__":
    main()
