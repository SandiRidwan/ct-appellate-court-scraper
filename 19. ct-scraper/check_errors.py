# check_errors.py — Diagnosa error yang terjadi
# Jalankan: python check_errors.py

import sqlite3
import pandas as pd

DB_PATH = "scraper.db"
conn    = sqlite3.connect(DB_PATH)

print("=" * 60)
print("ERROR DIAGNOSIS REPORT")
print("=" * 60)

# 1. Total counts
total    = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
done     = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='done'").fetchone()[0]
sealed   = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='sealed'").fetchone()[0]
errors   = conn.execute("SELECT COUNT(*) FROM errors WHERE error_type != 'checkpoint'").fetchone()[0]
cases_db = conn.execute("SELECT COUNT(*) FROM case_information").fetchone()[0]

print(f"\nCASES TABLE:")
print(f"  Total CRNs recorded : {total:,}")
print(f"  Done (valid)        : {done:,}")
print(f"  Sealed              : {sealed:,}")
print(f"  DB cases            : {cases_db:,}")
print(f"  Errors logged       : {errors:,}")

# 2. Error breakdown by type
print(f"\nERROR TYPES (top 10):")
df_types = pd.read_sql("""
    SELECT error_type, COUNT(*) as count
    FROM errors
    WHERE error_type != 'checkpoint'
    GROUP BY error_type
    ORDER BY count DESC
    LIMIT 10
""", conn)
print(df_types.to_string(index=False))

# 3. Sample error messages
print(f"\nSAMPLE ERROR MESSAGES (5 per type):")
types = conn.execute("""
    SELECT DISTINCT error_type FROM errors
    WHERE error_type != 'checkpoint'
    LIMIT 5
""").fetchall()

for (etype,) in types:
    print(f"\n  Type: {etype}")
    samples = conn.execute("""
        SELECT crn, error_msg FROM errors
        WHERE error_type = ? LIMIT 5
    """, (etype,)).fetchall()
    for crn, msg in samples:
        print(f"    CRN {crn}: {str(msg)[:100]}")

# 4. Apakah errors adalah CRN yang valid atau memang kosong?
print(f"\nCHECK: Apakah error CRNs seharusnya valid?")
print("(Ambil 5 CRN dari errors, cek apakah ada di case_information)")
err_crns = conn.execute("""
    SELECT crn FROM errors
    WHERE error_type != 'checkpoint'
    ORDER BY RANDOM() LIMIT 5
""").fetchall()

for (crn,) in err_crns:
    in_ci = conn.execute(
        "SELECT ac_number FROM case_information WHERE crn=?", (crn,)
    ).fetchone()
    print(f"  CRN {crn}: {'IN DB → '+in_ci[0] if in_ci else 'NOT IN DB'}")

# 5. CRN range yang paling banyak error
print(f"\nERROR CRN RANGE:")
range_data = conn.execute("""
    SELECT
        (CAST(crn AS INTEGER) / 1000) * 1000 AS range_start,
        COUNT(*) AS error_count
    FROM errors
    WHERE error_type != 'checkpoint'
      AND crn GLOB '[0-9]*'
    GROUP BY range_start
    ORDER BY error_count DESC
    LIMIT 10
""").fetchall()
for r_start, count in range_data:
    print(f"  CRN {r_start:,} - {r_start+999:,}: {count} errors")

# 6. Apakah scraper masih jalan?
processing = conn.execute(
    "SELECT COUNT(*) FROM cases WHERE scrape_status='processing'"
).fetchone()[0]
pending = conn.execute(
    "SELECT COUNT(*) FROM cases WHERE scrape_status='pending'"
).fetchone()[0]
print(f"\nSCRAPER STATUS:")
print(f"  Processing: {processing}")
print(f"  Pending   : {pending}")
if processing > 0:
    print("  → Scraper masih jalan")
else:
    print("  → Scraper sudah stop")

conn.close()
print("\n" + "=" * 60)
print("Paste output ini ke Claude untuk analisa dan fix")
