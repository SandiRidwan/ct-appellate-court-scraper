# fix_missing.py
# Cek dan re-scrape CRN yang ter-skip karena error
# Juga extend range ke atas jika perlu
#
# Jalankan: python fix_missing.py

import sqlite3

DB_PATH = "scraper.db"
conn    = sqlite3.connect(DB_PATH)

print("=" * 60)
print("MISSING CASES ANALYSIS")
print("=" * 60)

# 1. Cek semua status yang ada
print("\nAll scrape_status values:")
statuses = conn.execute("""
    SELECT scrape_status, COUNT(*) as cnt
    FROM cases
    GROUP BY scrape_status
    ORDER BY cnt DESC
""").fetchall()
for s, c in statuses:
    print(f"  {s}: {c:,}")

# 2. Cek apakah ada CRN yang tidak ter-cover sama sekali
max_crn = conn.execute("SELECT MAX(CAST(crn AS INTEGER)) FROM cases").fetchone()[0] or 0
total_in_db = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
expected = max_crn  # Seharusnya ada 1 sampai max_crn

print(f"\nCRN coverage check:")
print(f"  Max CRN in DB: {max_crn:,}")
print(f"  Total records: {total_in_db:,}")
print(f"  Missing CRNs : {max_crn - total_in_db:,} (gaps in range)")

# 3. Sample 20 CRN yang tidak ada di DB (gap)
print(f"\nSample missing CRN gaps (first 20):")
all_crns = set(int(r[0]) for r in conn.execute("SELECT crn FROM cases").fetchall())
gaps = []
for crn in range(1, min(max_crn+1, 100000)):
    if crn not in all_crns:
        gaps.append(crn)
    if len(gaps) >= 20:
        break

print(f"  Total gaps found in range 1-{min(max_crn,100000):,}: checking...")
total_gaps = sum(1 for crn in range(1, max_crn+1) if crn not in all_crns)
print(f"  Total gaps: {total_gaps:,}")
print(f"  Sample gaps: {gaps[:20]}")

# 4. Reset gaps ke pending agar bisa di-retry
if total_gaps > 0:
    print(f"\nInserting {total_gaps:,} gap CRNs as 'pending' for re-scraping...")
    gap_records = [(str(crn),) for crn in range(1, max_crn+1) if crn not in all_crns]
    conn.executemany(
        "INSERT OR IGNORE INTO cases (crn, scrape_status) VALUES (?, 'pending')",
        gap_records
    )
    conn.commit()
    pending_now = conn.execute(
        "SELECT COUNT(*) FROM cases WHERE scrape_status='pending'"
    ).fetchone()[0]
    print(f"  Pending cases now: {pending_now:,}")

conn.close()
print("\nNext: python phase_retry_gaps.py")
