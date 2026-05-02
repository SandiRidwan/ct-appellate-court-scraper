# monitor.py — Monitor progress phase_combined.py secara real-time
# Buka terminal KEDUA dan jalankan: python monitor.py
# Tekan Ctrl+C untuk stop monitor (tidak stop scraper)

import sqlite3, time

DB_PATH = "scraper.db"
TARGET  = 96470  # Total CRN range (dari find_max_crn.py)

def main():
    print(f"Monitoring phase_combined.py ... (Ctrl+C to stop)")
    print(f"CRN range target: {TARGET:,}\n")

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)

            # Jumlah unique cases yang berhasil di-scrape
            cases = conn.execute(
                "SELECT COUNT(*) FROM case_information"
            ).fetchone()[0]

            # CRN yang sudah diproses (done + sealed)
            done_crns = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE scrape_status IN ('done','sealed')"
            ).fetchone()[0]

            sealed = conn.execute(
                "SELECT COUNT(*) FROM cases WHERE scrape_status='sealed'"
            ).fetchone()[0]

            errors = conn.execute(
                "SELECT COUNT(*) FROM errors WHERE error_type != 'checkpoint'"
            ).fetchone()[0]

            # CRN tertinggi yang sudah diproses
            max_crn = conn.execute(
                "SELECT MAX(CAST(crn AS INTEGER)) FROM cases"
            ).fetchone()[0] or 0

            # Row counts di tiap tabel
            parties = conn.execute("SELECT COUNT(*) FROM party_attorney").fetchone()[0]
            acts    = conn.execute("SELECT COUNT(*) FROM case_activity").fetchone()[0]
            briefs  = conn.execute("SELECT COUNT(*) FROM briefs_record").fetchone()[0]

            conn.close()

            # Progress berdasarkan CRN yang sudah diproses vs total range
            pct   = min(done_crns / TARGET * 100, 100) if TARGET else 0
            remaining_crns = TARGET - done_crns
            eta_h = remaining_crns * 1.3 / 5 / 3600  # asumsi 5 workers

            bar_len = 40
            filled  = int(bar_len * pct / 100)
            bar     = "X" * filled + "." * (bar_len - filled)

            print(
                f"\r[{bar}] {pct:5.1f}%  "
                f"CRNdone:{done_crns:,}/{TARGET:,}  "
                f"ValidCases:{cases:,}  "
                f"Sealed:{sealed:,}  "
                f"MaxCRN:{max_crn:,}  "
                f"Parties:{parties:,}  "
                f"Acts:{acts:,}  "
                f"Briefs:{briefs:,}  "
                f"Errors:{errors}  "
                f"ETA:{eta_h:.1f}h   ",
                end="", flush=True
            )

        except Exception as e:
            print(f"\rDB error: {e}   ", end="", flush=True)

        time.sleep(15)

if __name__ == "__main__":
    main()
