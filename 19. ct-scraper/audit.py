# audit.py — Full Audit Script untuk Connecticut Appellate Court
# Menggunakan curl_cffi untuk bypass TLS fingerprint rejection
#
# Install dulu:
#   pip install curl_cffi beautifulsoup4 lxml
#
# Jalankan:
#   python audit.py
#
# Paste hasilnya ke Claude untuk analisa lanjut.

from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import json
import sys
import time

# ── CONFIG ───────────────────────────────────────────────────────────────────
BASE_URL    = "https://appellateinquiry.jud.ct.gov"
SEARCH_URL  = f"{BASE_URL}/SearchResults.aspx?CallingPage=Counsel&JN=&CoN=&C=&CS=All&SD=&ED="
DETAIL_URL  = f"{BASE_URL}/CaseDetail.aspx?CRN=72391&Type=Counsel"
DETAIL_URL2 = f"{BASE_URL}/CaseDetail.aspx?CRN=72392&Type=Counsel"
DETAIL_URL3 = f"{BASE_URL}/CaseDetail.aspx?CRN=50000&Type=Counsel"

IMPERSONATE = "chrome120"  # Opsi lain: chrome110, chrome107, safari15_5

# ── HELPER ───────────────────────────────────────────────────────────────────
def sep(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def ok(msg):  print(f"  ✅ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def err(msg):  print(f"  ❌ {msg}")
def info(msg): print(f"  ℹ️  {msg}")

# ── TEST 1: KONEKSI DASAR ─────────────────────────────────────────────────────
def test_1_connection():
    sep("TEST 1 — Koneksi dasar curl_cffi (Chrome TLS impersonation)")

    try:
        session = requests.Session(impersonate=IMPERSONATE)
        resp = session.get(BASE_URL + "/default.aspx", timeout=20)

        info(f"Status code   : {resp.status_code}")
        info(f"Content-Type  : {resp.headers.get('content-type', 'N/A')}")
        info(f"Response size : {len(resp.content):,} bytes")
        info(f"Final URL     : {resp.url}")

        # Cek response headers untuk clue anti-bot
        interesting_headers = ["server", "x-powered-by", "x-aspnet-version",
                                "set-cookie", "cf-ray", "x-cache", "x-frame-options"]
        print("\n  Response headers yang relevan:")
        for h in interesting_headers:
            v = resp.headers.get(h)
            if v:
                info(f"  {h}: {v[:120]}")

        if resp.status_code == 200:
            ok("Koneksi berhasil! curl_cffi bypass TLS fingerprint.")
            return session, resp
        else:
            err(f"Status {resp.status_code} — lihat body di bawah")
            print(resp.text[:500])
            return session, None

    except Exception as e:
        err(f"Exception: {e}")
        err("curl_cffi gagal. Coba: pip install --upgrade curl_cffi")
        return None, None

# ── TEST 2: SEARCH RESULTS PAGE ───────────────────────────────────────────────
def test_2_search_results(session):
    sep("TEST 2 — SearchResults.aspx (halaman daftar 224K cases)")

    try:
        resp = session.get(SEARCH_URL, timeout=30)
        info(f"Status code   : {resp.status_code}")
        info(f"Response size : {len(resp.content):,} bytes")

        if resp.status_code != 200:
            err(f"Gagal: {resp.status_code}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # ── Cek VIEWSTATE ──
        print("\n  ASP.NET Hidden Fields:")
        for field in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
                      "__EVENTTARGET", "__EVENTARGUMENT"]:
            el = soup.find("input", {"name": field})
            if el:
                val = el.get("value", "")
                ok(f"{field}: FOUND ({len(val)} chars)")
            else:
                warn(f"{field}: NOT FOUND")

        # ── Cek tabel hasil ──
        print("\n  Tabel di halaman:")
        tables = soup.find_all("table")
        info(f"Total tables: {len(tables)}")
        for i, tbl in enumerate(tables):
            rows = tbl.find_all("tr")
            tbl_id = tbl.get("id", "no-id")
            tbl_cls = tbl.get("class", [])
            if len(rows) > 3:  # Tabel yang punya banyak row = tabel data
                print(f"\n  Table[{i}] id='{tbl_id}' class={tbl_cls}")
                info(f"  Rows: {len(rows)}")
                # Print header row
                header = rows[0]
                headers = [th.get_text(strip=True) for th in header.find_all(["th","td"])]
                info(f"  Headers: {headers}")
                # Print sample data row
                if len(rows) > 1:
                    sample = rows[1]
                    cells = [td.get_text(strip=True)[:40] for td in sample.find_all("td")]
                    info(f"  Sample row: {cells}")
                    # Cek apakah ada link di row ini
                    links = sample.find_all("a")
                    for lnk in links:
                        info(f"  Link: href='{lnk.get('href','')}' text='{lnk.get_text(strip=True)[:40]}'")

        # ── Cek pagination ──
        print("\n  Pagination:")
        # Cari semua link yang mungkin pagination
        all_links = soup.find_all("a")
        pager_links = []
        for a in all_links:
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if text.isdigit() or text in ["Next", ">", "»", "...", "Last"]:
                pager_links.append({"text": text, "href": href[:100]})
        
        if pager_links:
            ok(f"Pagination ditemukan: {len(pager_links)} links")
            for p in pager_links[:10]:
                info(f"  '{p['text']}' → {p['href']}")
        else:
            warn("Tidak ada pagination link ditemukan")
            warn("Kemungkinan: semua data di 1 halaman, atau pagination pakai JS event")

        # ── Cek total record count ──
        print("\n  Total records:")
        text = soup.get_text()
        counts = re.findall(r'(\d[\d,]+)\s*(?:record|case|result)', text, re.IGNORECASE)
        if counts:
            ok(f"Record count mentions: {counts}")
        else:
            warn("Tidak ada mention jumlah record eksplisit")

        # ── Cek apakah ada doPostBack ──
        print("\n  ASP.NET doPostBack events:")
        postbacks = re.findall(r"__doPostBack\('([^']+)','([^']+)'\)", resp.text)
        if postbacks:
            ok(f"doPostBack found: {len(postbacks)} events")
            for pb in postbacks[:10]:
                info(f"  target='{pb[0]}' arg='{pb[1]}'")
        else:
            warn("Tidak ada doPostBack — pagination mungkin pakai cara lain")

        # ── Cek GridView ID ──
        print("\n  GridView / data grid IDs:")
        gridviews = re.findall(r'id="([^"]*(?:Grid|grid|List|list|Result|result|gv|GV)[^"]*)"', resp.text)
        if gridviews:
            ok(f"GridView-like IDs: {gridviews}")
        else:
            warn("Tidak ada GridView ID ditemukan")

        # ── Sample raw HTML (200 chars) dari area tabel ──
        print("\n  Sample HTML (area tabel):")
        table_html = str(tables[2])[:600] if len(tables) > 2 else resp.text[:600]
        print(f"  {table_html[:600]}")

        return soup

    except Exception as e:
        err(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return None

# ── TEST 3: CASE DETAIL PAGE ──────────────────────────────────────────────────
def test_3_case_detail(session):
    sep("TEST 3 — CaseDetail.aspx (halaman detail 1 case)")

    results = {}
    for label, url in [("CRN 72391", DETAIL_URL),
                        ("CRN 72392", DETAIL_URL2),
                        ("CRN 50000 (older)", DETAIL_URL3)]:
        print(f"\n  Testing {label}: {url}")
        try:
            resp = session.get(url, timeout=30)
            info(f"  Status: {resp.status_code} | Size: {len(resp.content):,} bytes")

            if resp.status_code != 200:
                err(f"  Failed: {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            text = soup.get_text()

            # Cek keberadaan 8 section yang diminta klien
            sections_to_find = [
                "Case Information",
                "Appeal Case Information",
                "Cross Appeal",
                "Amended Appeal",
                "Trial Court",
                "Party",
                "Attorney",
                "Transcript",
                "Exhibit",
                "Preliminary",
                "Brief",
                "Prepared Record",
                "Activity",
            ]
            print(f"\n  Section check untuk {label}:")
            for sec in sections_to_find:
                found = sec.lower() in text.lower()
                if found:
                    ok(f"  '{sec}': FOUND")
                else:
                    info(f"  '{sec}': not found")

            # Cek semua tabel di halaman ini
            print(f"\n  Tabel di {label}:")
            tables = soup.find_all("table")
            info(f"  Total tables: {len(tables)}")
            for i, tbl in enumerate(tables):
                rows = tbl.find_all("tr")
                tbl_id = tbl.get("id", "no-id")
                if rows:
                    info(f"  Table[{i}] id='{tbl_id}': {len(rows)} rows")

            # Cari semua ID unik di halaman
            print(f"\n  Element IDs yang menarik di {label}:")
            all_ids = re.findall(r'id="(ctl[^"]+|[^"]*(?:Party|party|Atty|atty|Brief|brief|Activity|activity|Transcript|transcript|Panel|panel|Grid|grid)[^"]*)"', resp.text)
            if all_ids:
                for id_val in list(set(all_ids))[:20]:
                    info(f"  id='{id_val}'")
            else:
                warn("  Tidak ada ID relevan ditemukan")

            # Cek links di halaman (dokumen links)
            print(f"\n  Document links di {label}:")
            all_links = soup.find_all("a", href=True)
            doc_links = [a for a in all_links if "DocumentDisplayer" in a.get("href","") or ".pdf" in a.get("href","").lower()]
            if doc_links:
                ok(f"  Document links: {len(doc_links)}")
                for lnk in doc_links[:3]:
                    info(f"  '{lnk.get_text(strip=True)[:40]}' → {lnk['href'][:80]}")
            else:
                warn("  Tidak ada document links ditemukan")

            # Print 800 chars dari body text untuk lihat struktur data
            print(f"\n  Sample text content dari {label}:")
            clean_text = " ".join(text.split())[:800]
            print(f"  {clean_text}")

            results[label] = {"status": resp.status_code, "size": len(resp.content)}
            time.sleep(1.5)

        except Exception as e:
            err(f"  Exception: {e}")

    return results

# ── TEST 4: PAGINATION DEEP DIVE ──────────────────────────────────────────────
def test_4_pagination(session, search_soup):
    sep("TEST 4 — Pagination deep dive")

    if not search_soup:
        warn("Skip — search_soup tidak tersedia")
        return

    # Coba navigasi ke halaman 2 via POST dengan VIEWSTATE
    print("\n  Mencoba POST ke halaman 2...")

    # Extract semua hidden fields
    hidden_fields = {}
    for inp in search_soup.find_all("input", type="hidden"):
        name = inp.get("name","")
        val  = inp.get("value","")
        if name:
            hidden_fields[name] = val
            info(f"  Hidden field: {name} ({len(val)} chars)")

    # Cari target untuk doPostBack pagination
    # ASP.NET GridView pagination biasanya: __doPostBack('GridView1','Page$2')
    postback_targets = re.findall(r"__doPostBack\('([^']+)','Page\$(\d+)'\)", str(search_soup))
    if postback_targets:
        ok(f"Pagination doPostBack targets: {postback_targets[:5]}")
        target_id  = postback_targets[0][0]
        page_num   = postback_targets[0][1]
    else:
        warn("Tidak ada Page$ doPostBack ditemukan")
        warn("Coba cari pattern lain...")
        # Fallback: cari semua doPostBack
        all_pb = re.findall(r"__doPostBack\('([^']+)','([^']+)'\)", str(search_soup))
        info(f"Semua doPostBack: {all_pb[:10]}")
        target_id = "GridView1"  # default guess
        page_num  = "2"

    # Coba POST
    post_data = {
        **hidden_fields,
        "__EVENTTARGET":   target_id,
        "__EVENTARGUMENT": f"Page${page_num}",
        "__SCROLLPOSITIONX": "0",
        "__SCROLLPOSITIONY": "0",
    }

    info(f"\n  Posting dengan __EVENTTARGET='{target_id}', __EVENTARGUMENT='Page${page_num}'")

    try:
        resp2 = session.post(SEARCH_URL, data=post_data, timeout=30)
        info(f"  POST Status: {resp2.status_code}")
        info(f"  POST Response size: {len(resp2.content):,} bytes")

        if resp2.status_code == 200:
            soup2 = BeautifulSoup(resp2.text, "lxml")
            text2 = soup2.get_text()

            # Cek apakah halaman berubah
            if resp2.text == str(search_soup):
                err("Response IDENTIK dengan halaman 1 — POST tidak berhasil navigasi")
            else:
                ok("Response BERBEDA dari halaman 1 — kemungkinan berhasil!")

                # Cek data baru
                tables2 = soup2.find_all("table")
                for tbl in tables2:
                    rows = tbl.find_all("tr")
                    if len(rows) > 3:
                        info(f"Table dengan {len(rows)} rows")
                        if len(rows) > 1:
                            sample = rows[1]
                            cells = [td.get_text(strip=True)[:30] for td in sample.find_all("td")]
                            info(f"Sample row page 2: {cells}")
                        break

    except Exception as e:
        err(f"  POST Exception: {e}")

# ── TEST 5: CEK APAKAH ADA HIDDEN API ────────────────────────────────────────
def test_5_hidden_api(session):
    sep("TEST 5 — Cek kemungkinan hidden API endpoint")

    # Beberapa endpoint yang umum di ASP.NET site
    candidates = [
        f"{BASE_URL}/CaseDetail.aspx?CRN=72391&Type=Counsel&format=json",
        f"{BASE_URL}/api/cases",
        f"{BASE_URL}/api/search",
        f"{BASE_URL}/SearchResults.aspx?CallingPage=Counsel&CS=All&format=json",
        f"{BASE_URL}/CaseDetailHandler.ashx?CRN=72391",
        f"{BASE_URL}/GetCases.ashx",
    ]

    for url in candidates:
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200 and "json" in resp.headers.get("content-type",""):
                ok(f"JSON API found: {url}")
                print(resp.text[:300])
            elif resp.status_code == 200:
                info(f"200 OK (non-JSON): {url} — {len(resp.content)} bytes")
            else:
                info(f"{resp.status_code}: {url}")
        except:
            pass

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "█" * 60)
    print("  CONNECTICUT APPELLATE COURT — FULL AUDIT")
    print("  curl_cffi Chrome TLS Impersonation")
    print("█" * 60)

    # Test 1: Koneksi
    session, resp_home = test_1_connection()
    if not session:
        print("\n❌ FATAL: Tidak bisa buat session. Install curl_cffi dulu.")
        print("   pip install curl_cffi")
        sys.exit(1)

    time.sleep(1)

    # Test 2: Search Results
    search_soup = test_2_search_results(session)
    time.sleep(1.5)

    # Test 3: Case Detail
    test_3_case_detail(session)
    time.sleep(1)

    # Test 4: Pagination
    test_4_pagination(session, search_soup)
    time.sleep(1)

    # Test 5: Hidden API
    test_5_hidden_api(session)

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    sep("RINGKASAN AUDIT")
    print("""
  Paste SELURUH output ini ke Claude untuk mendapatkan:
  1. Analisa teknis lengkap
  2. Update script Phase 1 & 2 yang disesuaikan
  3. Selector HTML yang tepat untuk setiap section

  Yang paling penting dari output ini:
  - Status code TEST 2 (SearchResults)
  - Status code TEST 3 (CaseDetail)  
  - Apakah pagination ditemukan (TEST 4)
  - List element IDs dari CaseDetail (untuk update parser)
    """)

if __name__ == "__main__":
    main()