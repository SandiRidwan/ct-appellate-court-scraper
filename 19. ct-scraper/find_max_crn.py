# find_max_crn.py
# Binary search untuk temukan CRN tertinggi yang valid di site
# Jalankan DULU sebelum phase_combined.py
# Runtime: ~2-3 menit
#
# Jalankan: python find_max_crn.py

from curl_cffi import requests
from bs4 import BeautifulSoup
import time, re

BASE_URL   = "https://appellateinquiry.jud.ct.gov"
DETAIL_URL = BASE_URL + "/CaseDetail.aspx?CRN={crn}&Type=Counsel"

def check(session, crn):
    """
    Return:
      'valid'  — CRN ada dan punya data
      'sealed' — CRN ada tapi not available
      'empty'  — CRN tidak ada sama sekali (404-like atau blank)
    """
    try:
        resp = session.get(DETAIL_URL.format(crn=crn), timeout=20)
        if resp.status_code != 200:
            return "empty"
        text = resp.text.lower()
        if "not available at this time" in text:
            return "sealed"
        soup = BeautifulSoup(resp.text, "lxml")
        raw  = soup.get_text()
        if re.search(r"\b(AC\s*\d+|SC\s*\d+)\b", raw):
            return "valid"
        # Halaman ada tapi tidak ada AC/SC number = bukan case page
        if len(raw.strip()) < 500:
            return "empty"
        return "sealed"
    except:
        return "empty"

def main():
    session = requests.Session(impersonate="chrome120")

    print("=" * 60)
    print("FIND MAX CRN — Binary Search")
    print("=" * 60)

    # ── STEP 1: Cari upper bound dulu ─────────────────────────────
    # Mulai dari 100K, naik 2x sampai ketemu empty
    print("\nStep 1: Finding upper bound...")
    probe = 100_000
    while True:
        status = check(session, probe)
        print(f"  CRN {probe:,} → {status}")
        time.sleep(1)
        if status == "empty":
            upper = probe
            lower = probe // 2
            break
        probe *= 2
        if probe > 10_000_000:
            print("CRN sangat tinggi! Set manual upper = 5,000,000")
            upper = 5_000_000
            lower = probe // 2
            break

    print(f"\nUpper bound: {upper:,} | Lower bound: {lower:,}")

    # ── STEP 2: Binary search antara lower dan upper ───────────────
    print("\nStep 2: Binary search...")
    best_valid = lower

    while upper - lower > 100:
        mid    = (lower + upper) // 2
        status = check(session, mid)
        print(f"  CRN {mid:,} → {status}")
        time.sleep(1.2)

        if status in ("valid", "sealed"):
            # Ada sesuatu di sini, cari lebih tinggi
            lower      = mid
            if status == "valid":
                best_valid = mid
        else:
            # Kosong, turunkan upper
            upper = mid

    # ── STEP 3: Linear scan dari best_valid ke upper ───────────────
    print(f"\nStep 3: Linear scan {lower:,} to {upper:,}...")
    last_valid = lower
    for crn in range(lower, min(upper + 1, lower + 500)):
        status = check(session, crn)
        if status in ("valid", "sealed"):
            last_valid = crn
        if crn % 50 == 0:
            print(f"  Scanned to CRN {crn:,}, last valid: {last_valid:,}")
        time.sleep(0.8)

    print("\n" + "=" * 60)
    print(f"HASIL:")
    print(f"  Max CRN dengan data  : {last_valid:,}")
    print(f"  Recommended CRN_END  : {int(last_valid * 1.2):,}  (20% buffer)")
    print(f"\nUpdate CRN_END di phase_combined.py:")
    print(f"  CRN_END = {int(last_valid * 1.2):,}")
    print("=" * 60)

if __name__ == "__main__":
    main()
