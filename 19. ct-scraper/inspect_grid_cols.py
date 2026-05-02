# inspect_grid_cols.py
# Lihat isi col1-col5 dari tab 6/7/8 untuk tentukan nama kolom yang benar
# Jalankan: python inspect_grid_cols.py

import sqlite3

DB_PATH = "scraper.db"
conn    = sqlite3.connect(DB_PATH)

for tbl, label in [
    ("transcripts_exhibits", "TAB 6 — Transcripts & Exhibits"),
    ("preliminary_papers",   "TAB 7 — Preliminary Papers"),
    ("briefs_record",        "TAB 8 — Briefs & Prepared Record"),
]:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    rows = conn.execute(f"""
        SELECT col1, col2, col3, col4, col5, link_url
        FROM {tbl}
        WHERE col1 != '' OR col2 != ''
        LIMIT 8
    """).fetchall()

    print(f"  {'COL1':<35} {'COL2':<15} {'COL3':<15} {'COL4':<20} {'COL5':<15} LINK")
    print(f"  {'-'*35} {'-'*15} {'-'*15} {'-'*20} {'-'*15} ----")
    for row in rows:
        c1,c2,c3,c4,c5,lnk = row
        print(f"  {str(c1)[:35]:<35} {str(c2)[:15]:<15} {str(c3)[:15]:<15} {str(c4)[:20]:<20} {str(c5)[:15]:<15} {'Y' if lnk else ''}")

    # Count non-empty per kolom
    print(f"\n  Non-empty counts:")
    for i in range(1, 6):
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl} WHERE col{i} != ''").fetchone()[0]
        total = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        pct = cnt/total*100 if total else 0
        print(f"    col{i}: {cnt:,}/{total:,} ({pct:.0f}% filled)")

conn.close()
