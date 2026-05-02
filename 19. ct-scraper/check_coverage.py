# check_coverage.py — Cek coverage dan apakah perlu extend CRN range
import sqlite3, re

DB_PATH = "scraper.db"
conn    = sqlite3.connect(DB_PATH)

print("=" * 60)
print("COVERAGE REPORT")
print("=" * 60)

# 1. Summary
cases    = conn.execute("SELECT COUNT(*) FROM case_information").fetchone()[0]
parties  = conn.execute("SELECT COUNT(*) FROM party_attorney").fetchone()[0]
sealed   = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='sealed'").fetchone()[0]
done     = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='done'").fetchone()[0]
total    = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
max_crn  = conn.execute("SELECT MAX(CAST(crn AS INTEGER)) FROM cases").fetchone()[0] or 0

print(f"\n  Unique cases scraped : {cases:,}")
print(f"  Party/Attorney rows  : {parties:,}")
print(f"  Sealed/Invalid CRNs  : {sealed:,}")
print(f"  Total CRNs processed : {total:,}")
print(f"  Max CRN reached      : {max_crn:,}")

# 2. Apakah SearchResults 224K = party rows bukan unique cases?
avg_parties = parties / cases if cases else 0
est_search_rows = cases * avg_parties
print(f"\n  Avg parties per case : {avg_parties:.1f}")
print(f"  Est. SearchResult rows: {est_search_rows:,.0f}")
print(f"  Client said 224K rows : 224,000")

# 3. Tahun distribusi cases
print(f"\n  CASE DISTRIBUTION BY YEAR (from date_filed):")
year_data = conn.execute("""
    SELECT
        SUBSTR(date_filed, -4) AS year,
        COUNT(*) AS cnt
    FROM appeal_case_info
    WHERE date_filed != ''
      AND SUBSTR(date_filed, -4) GLOB '[0-9][0-9][0-9][0-9]'
    GROUP BY year
    ORDER BY year DESC
    LIMIT 15
""").fetchall()
for year, cnt in year_data:
    print(f"    {year}: {cnt:,} cases")

# 4. Cek AC number range untuk estimasi total
print(f"\n  AC NUMBER RANGE:")
ac_data = conn.execute("""
    SELECT
        MIN(CAST(REPLACE(ac_number,'AC ','') AS INTEGER)) as min_ac,
        MAX(CAST(REPLACE(ac_number,'AC ','') AS INTEGER)) as max_ac,
        COUNT(*) as total
    FROM case_information
    WHERE ac_number LIKE 'AC%'
""").fetchone()
if ac_data and ac_data[0]:
    print(f"    Min AC: {ac_data[0]:,}")
    print(f"    Max AC: {ac_data[1]:,}")
    print(f"    Total AC cases: {ac_data[2]:,}")

# SC cases
sc_data = conn.execute("""
    SELECT COUNT(*) FROM case_information WHERE ac_number LIKE 'SC%'
""").fetchone()[0]
print(f"    Total SC cases: {sc_data:,}")

# 5. Cek CRN di ujung — apakah masih ada valid case di atas 80,392?
print(f"\n  CRN DISTRIBUTION (last 5000):")
recent = conn.execute("""
    SELECT scrape_status, COUNT(*) as cnt
    FROM cases
    WHERE CAST(crn AS INTEGER) > 75000
    GROUP BY scrape_status
""").fetchall()
for status, cnt in recent:
    print(f"    CRN>75000 → {status}: {cnt:,}")

conn.close()
print("\n" + "=" * 60)
