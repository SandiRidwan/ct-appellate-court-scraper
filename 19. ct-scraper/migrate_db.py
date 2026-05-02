# migrate_db.py — Update DB schema sebelum re-scrape
# Jalankan SEKALI: python migrate_db.py

import sqlite3

DB_PATH = "scraper.db"
conn    = sqlite3.connect(DB_PATH)

print("Migrating DB schema...")

# Reset status semua done → pending untuk re-scrape dengan parser baru
# HANYA reset, tidak hapus data — data lama tetap ada sampai di-overwrite
done = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='done'").fetchone()[0]
conn.execute("UPDATE cases SET scrape_status='pending' WHERE scrape_status='done'")
conn.commit()
print(f"  Reset {done:,} done → pending")

# Kosongkan tabel yang datanya salah
tables_to_clear = [
    "appeal_case_info",
    "trial_court_info",
    "case_activity",
    "case_information",  # karena status mengandung &nbsp
]
for tbl in tables_to_clear:
    cnt = conn.execute(f"DELETE FROM {tbl}").rowcount
    print(f"  Cleared {tbl}: {cnt:,} rows")

conn.commit()

pending = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='pending'").fetchone()[0]
print(f"\nReady: {pending:,} cases pending re-scrape")
print("Next: python phase_combined.py")
conn.close()
