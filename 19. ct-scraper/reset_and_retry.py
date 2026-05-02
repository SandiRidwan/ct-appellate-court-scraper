# reset_and_retry.py
# Reset semua case yang sudah di-scrape (status='done') kembali ke 'pending'
# agar di-scrape ulang dengan parser yang sudah difix.
#
# Jalankan SEKALI setelah update phase2_scrape_details.py
# Lalu jalankan lagi: python phase2_scrape_details.py

import sqlite3

DB_PATH = "scraper.db"
conn    = sqlite3.connect(DB_PATH)

# Hitung dulu
done   = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='done'").fetchone()[0]
total  = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]

print(f"Cases saat ini: {total:,} total, {done:,} done")
print(f"Semua {done:,} case akan di-reset ke 'pending' untuk re-scrape...")

confirm = input("Lanjut? (y/n): ").strip().lower()
if confirm != "y":
    print("Dibatalkan.")
    conn.close()
    exit()

# Hapus data lama dari semua tabel detail
tables = [
    "case_information", "appeal_case_info", "cross_appeal",
    "trial_court_info", "party_attorney", "transcripts_exhibits",
    "preliminary_papers", "briefs_record", "case_activity"
]
for tbl in tables:
    deleted = conn.execute(f"DELETE FROM {tbl}").rowcount
    print(f"  Cleared {tbl}: {deleted:,} rows")

# Reset status
conn.execute("UPDATE cases SET scrape_status='pending', scraped_at=NULL WHERE scrape_status='done'")
conn.execute("UPDATE cases SET scrape_status='pending', scraped_at=NULL WHERE scrape_status='failed'")
conn.execute("UPDATE cases SET scrape_status='pending', scraped_at=NULL WHERE scrape_status='sealed'")
conn.commit()

pending_now = conn.execute("SELECT COUNT(*) FROM cases WHERE scrape_status='pending'").fetchone()[0]
print(f"\nDone. {pending_now:,} cases reset ke 'pending'.")
print("Sekarang jalankan: python phase2_scrape_details.py")
conn.close()
