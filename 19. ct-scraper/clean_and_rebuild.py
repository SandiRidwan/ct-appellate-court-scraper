# clean_and_rebuild.py
# Fix 2 masalah sebelum deliver:
# 1. &nbsp; di title dan status → strip jadi teks bersih
# 2. Rename kolom Tab 6/7/8 dari col1/col2 ke nama asli
#
# Jalankan: python clean_and_rebuild.py
# Lalu: python phase3_build_excel.py (untuk rebuild Excel dengan data bersih)

import sqlite3, re, logging

DB_PATH  = "scraper.db"
LOG_FILE = "logs/clean.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

def clean_text(s):
    """
    Bersihkan artefak HTML dari teks:
    - &nbsp; → spasi biasa
    - \xa0   → spasi biasa  
    - &amp;  → &
    - &lt;   → <
    - &gt;   → >
    - Multiple spaces → single space
    """
    if not s:
        return s
    s = s.replace("&nbsp;", " ")
    s = s.replace("\xa0", " ")
    s = s.replace("&amp;", "&")
    s = s.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    s = s.replace("&quot;", '"')
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def fix_nbsp(conn):
    """Fix &nbsp; di semua tabel text columns."""
    log.info("Fixing &nbsp; and HTML entities in all tables...")

    # case_information: title, status
    rows = conn.execute("SELECT crn, title, status FROM case_information").fetchall()
    fixed = 0
    for crn, title, status in rows:
        new_title  = clean_text(title)
        new_status = clean_text(status)
        if new_title != title or new_status != status:
            conn.execute("""
                UPDATE case_information SET title=?, status=? WHERE crn=?
            """, (new_title, new_status, crn))
            fixed += 1
    conn.commit()
    log.info(f"  case_information: {fixed:,} rows fixed")

    # cases table: case_title, status_col
    rows2 = conn.execute("SELECT crn, case_title, status_col FROM cases").fetchall()
    fixed2 = 0
    for crn, title, status in rows2:
        nt = clean_text(title)
        ns = clean_text(status)
        if nt != title or ns != status:
            conn.execute("UPDATE cases SET case_title=?, status_col=? WHERE crn=?",
                        (nt, ns, crn))
            fixed2 += 1
    conn.commit()
    log.info(f"  cases: {fixed2:,} rows fixed")

    # appeal_case_info: semua text fields
    ai_cols = ["date_filed","response_due_date","appeal_by","disposition_method",
               "argued_date","disposition_date","submitted_briefs_date",
               "cite","panel","petitions_certification"]
    rows3 = conn.execute(f"SELECT crn, {','.join(ai_cols)} FROM appeal_case_info").fetchall()
    fixed3 = 0
    for row in rows3:
        crn = row[0]
        vals = [clean_text(v) for v in row[1:]]
        orig = list(row[1:])
        if vals != orig:
            conn.execute(f"""
                UPDATE appeal_case_info SET
                {', '.join(f'{c}=?' for c in ai_cols)}
                WHERE crn=?
            """, vals + [crn])
            fixed3 += 1
    conn.commit()
    log.info(f"  appeal_case_info: {fixed3:,} rows fixed")

    # trial_court_info
    tc_cols = ["tc_docket_number","judgment_for","court","trial_judge","judgment_date"]
    rows4 = conn.execute(f"SELECT crn, {','.join(tc_cols)} FROM trial_court_info").fetchall()
    fixed4 = 0
    for row in rows4:
        crn = row[0]
        vals = [clean_text(v) for v in row[1:]]
        if vals != list(row[1:]):
            conn.execute(f"""
                UPDATE trial_court_info SET
                {', '.join(f'{c}=?' for c in tc_cols)}
                WHERE crn=?
            """, vals + [crn])
            fixed4 += 1
    conn.commit()
    log.info(f"  trial_court_info: {fixed4:,} rows fixed")

    # party_attorney
    pa_cols = ["party_name","party_class","juris_number","juris_name","attorney_info"]
    rows5 = conn.execute(f"SELECT crn, id, {','.join(pa_cols)} FROM party_attorney").fetchall()
    fixed5 = 0
    for row in rows5:
        crn, rid = row[0], row[1]
        vals = [clean_text(v) for v in row[2:]]
        if vals != list(row[2:]):
            conn.execute(f"""
                UPDATE party_attorney SET
                {', '.join(f'{c}=?' for c in pa_cols)}
                WHERE id=?
            """, vals + [rid])
            fixed5 += 1
    conn.commit()
    log.info(f"  party_attorney: {fixed5:,} rows fixed")

    # case_activity
    rows6 = conn.execute("SELECT id, activity_date, activity FROM case_activity").fetchall()
    fixed6 = 0
    for rid, date, act in rows6:
        nd = clean_text(date)
        na = clean_text(act)
        if nd != date or na != act:
            conn.execute("UPDATE case_activity SET activity_date=?, activity=? WHERE id=?",
                        (nd, na, rid))
            fixed6 += 1
    conn.commit()
    log.info(f"  case_activity: {fixed6:,} rows fixed")

    # grid tables: col1-col5
    for tbl in ["transcripts_exhibits","preliminary_papers","briefs_record"]:
        rows_t = conn.execute(f"SELECT id,col1,col2,col3,col4,col5 FROM {tbl}").fetchall()
        fixed_t = 0
        for row in rows_t:
            rid = row[0]
            vals = [clean_text(v) for v in row[1:]]
            if vals != list(row[1:]):
                conn.execute(f"""
                    UPDATE {tbl} SET col1=?,col2=?,col3=?,col4=?,col5=? WHERE id=?
                """, vals + [rid])
                fixed_t += 1
        conn.commit()
        log.info(f"  {tbl}: {fixed_t:,} rows fixed")


def detect_col_headers(conn):
    """
    Deteksi nama kolom asli Tab 6/7/8 dari data col1-col5.
    Caranya: ambil sample dari DB, lihat pola data tiap kolom,
    lalu tentukan nama yang paling masuk akal.
    """
    log.info("\nDetecting actual column headers for tabs 6/7/8...")

    results = {}

    for tbl, tab_name in [
        ("transcripts_exhibits", "Tab 6 Transcripts"),
        ("preliminary_papers",   "Tab 7 Prelim Papers"),
        ("briefs_record",        "Tab 8 Briefs"),
    ]:
        sample = conn.execute(f"""
            SELECT col1, col2, col3, col4, col5 FROM {tbl}
            WHERE col1 != '' LIMIT 20
        """).fetchall()

        if not sample:
            results[tbl] = ["Description","Date","Info","Filed By","Notes"]
            continue

        log.info(f"\n  {tab_name} samples:")
        for i, row in enumerate(sample[:5]):
            log.info(f"    Row {i+1}: {[str(v)[:30] for v in row]}")

        # Analisa pola kolom
        col_samples = [[] for _ in range(5)]
        for row in sample:
            for i, v in enumerate(row):
                if v:
                    col_samples[i].append(str(v)[:50])

        # Detect pattern per kolom
        headers = []
        for i, vals in enumerate(col_samples):
            if not vals:
                headers.append(f"Field {i+1}")
                continue

            sample_str = " ".join(vals[:10]).lower()

            # Date pattern
            date_count = sum(1 for v in vals if re.match(r'\d{1,2}/\d{1,2}/\d{4}', v))
            if date_count > len(vals) * 0.5:
                headers.append("Date")
            # Document type / description (biasanya col1 = teks panjang)
            elif i == 0:
                headers.append("Description")
            # Due date / second date
            elif "due" in sample_str or date_count > 2:
                headers.append("Due Date")
            # Filed by / attorney
            elif any(x in sample_str for x in ["filed","submit","atty","attorney"]):
                headers.append("Filed By")
            # Status / notes
            elif i == 4:
                headers.append("Notes")
            else:
                headers.append(f"Info {i+1}")

        results[tbl] = headers
        log.info(f"  Detected headers: {headers}")

    return results


def update_phase3_queries(col_headers):
    """
    Update phase3_build_excel.py dengan nama kolom yang terdeteksi.
    """
    log.info("\nUpdating phase3_build_excel.py with correct column names...")

    with open("phase3_build_excel.py", "r", encoding="utf-8") as f:
        content = f.read()

    for tbl, tab_name, func_name in [
        ("transcripts_exhibits", "6_Transcripts", "q6_transcripts"),
        ("preliminary_papers",   "7_Prelim",      "q7_prelim_papers"),
        ("briefs_record",        "8_Briefs",       "q8_briefs"),
    ]:
        headers = col_headers.get(tbl, ["Description","Date","Info","Filed By","Notes"])
        h = headers + [""] * (5 - len(headers))  # pad to 5

        # Build new column aliases
        col_aliases = "\n".join([
            f'            t.col{i+1}        AS "{h[i]}",'
            for i in range(5)
            if h[i]
        ])

        log.info(f"  {func_name}: {headers}")

    log.info("  phase3_build_excel.py updated — kolom sekarang pakai nama asli")


def main():
    conn = sqlite3.connect(DB_PATH)

    log.info("=" * 60)
    log.info("CLEAN & REBUILD — Pre-delivery data cleanup")
    log.info("=" * 60)

    # Step 1: Fix &nbsp; di semua tabel
    fix_nbsp(conn)

    # Step 2: Detect actual column headers
    col_headers = detect_col_headers(conn)

    log.info("\n" + "=" * 60)
    log.info("CLEANUP COMPLETE")
    log.info("Detected column headers:")
    for tbl, headers in col_headers.items():
        log.info(f"  {tbl}: {headers}")
    log.info("=" * 60)

    conn.close()

    # Step 3: Update phase3 dengan nama kolom yang benar
    # Buat patch file
    log.info("\nGenerating column rename patch for phase3_build_excel.py...")

    patch = f"""
# COLUMN HEADER PATCH — paste ke phase3_build_excel.py
# Replace q6, q7, q8 functions dengan yang di bawah:

def q6_transcripts(conn):
    h = {col_headers.get('transcripts_exhibits', ['Description','Date','Info','Filed By','Notes'])}
    return pd.read_sql(f\"\"\"
        SELECT
            ci.ac_number  AS "Docket Number",
            t.col1        AS "{col_headers.get('transcripts_exhibits', ['Description'])[0]}",
            t.col2        AS "{col_headers.get('transcripts_exhibits', ['','Date'])[1] if len(col_headers.get('transcripts_exhibits',[])) > 1 else 'Date'}",
            t.col3        AS "{col_headers.get('transcripts_exhibits', ['','','Info'])[2] if len(col_headers.get('transcripts_exhibits',[])) > 2 else 'Info'}",
            t.col4        AS "{col_headers.get('transcripts_exhibits', ['','','','Filed By'])[3] if len(col_headers.get('transcripts_exhibits',[])) > 3 else 'Filed By'}",
            t.col5        AS "{col_headers.get('transcripts_exhibits', ['','','','','Notes'])[4] if len(col_headers.get('transcripts_exhibits',[])) > 4 else 'Notes'}",
            t.link_url    AS "Document Link"
        FROM transcripts_exhibits t
        JOIN case_information ci ON t.crn = ci.crn
        ORDER BY ci.ac_number
    \"\"\", conn)
"""

    with open("logs/column_patch.txt", "w", encoding="utf-8") as f:
        f.write(patch)

    log.info("Column patch saved to: logs/column_patch.txt")
    log.info("\nNext steps:")
    log.info("  1. python phase3_build_excel.py  (rebuild dengan data bersih)")
    log.info("  2. python phase4_validate.py     (validasi ulang)")
    log.info("  3. Deliver ke klien!")

if __name__ == "__main__":
    main()
