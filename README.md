<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Orbitron&weight=900&size=46&duration=3000&pause=1000&color=00FFFF&center=true&vCenter=true&width=800&height=90&lines=SANDI+RIDWAN" alt="Sandi Ridwan" />

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=16&duration=2500&pause=800&color=7EB8D4&center=true&vCenter=true&width=750&lines=Data+Automation+Engineer+%7C+Web+Scraping+Specialist;Connecticut+Appellate+Court+%E2%80%94+56%2C598+Cases+Extracted;TLS+Fingerprint+Bypass+%7C+ASP.NET+VIEWSTATE+%7C+9-Tab+Excel" alt="Subtitle" />

<br/><br/>

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![curl_cffi](https://img.shields.io/badge/curl__cffi-TLS%20Bypass-00D4FF?style=for-the-badge)](https://github.com/yifeikong/curl_cffi)
[![SQLite](https://img.shields.io/badge/SQLite-Checkpoint%20DB-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![openpyxl](https://img.shields.io/badge/openpyxl-9--Tab%20Excel-217346?style=for-the-badge&logo=microsoftexcel&logoColor=white)](https://openpyxl.readthedocs.io)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

<div align="center">

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│          STATE OF CONNECTICUT — JUDICIAL BRANCH                      │
│          Supreme and Appellate Court Case Look-up                    │
│          Full Database Extraction  ·  1991 – 2026                   │
│                                                                      │
│   96,470 CRNs scanned  ──►  56,598 valid cases  ──►  41.2 MB Excel  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

</div>

---

## 📹 Demo

<div align="center">
  <a href="https://youtube.com/watch?v=kWFCRtUua8">
    <img src="thumbnail.png" width="860" alt="Watch full demo on YouTube" />
  </a>
  <br/>
  <sub><i>Click to watch — scraper run, monitor progress, Excel output walkthrough</i></sub>
</div>

<br/>

<div align="center">
  <img src="https://i.imgur.com/etc86rt.gif" width="860" />
</div>

---

## ⚡ Overview

A production-grade web scraper for the **Connecticut Judicial Branch Appellate Court** — one of the most technically complex government scraping projects, involving TLS-level bot detection, stateful ASP.NET WebForms pagination, and large-scale parallel data extraction.

<div align="center">

| Metric | Value |
|:---|---:|
| Unique cases extracted | **56,598** |
| Party / Attorney rows | **187,590** |
| Case Activity logs | **440,163** |
| Preliminary Papers | **76,081** |
| Briefs & Prepared Record | **98,979** |
| Transcripts & Exhibits | **46,647** |
| Excel output size | **41.2 MB** |
| CRN range scanned | **1 – 96,470** |
| Runtime with 5 workers | **~11 hours** |

</div>

---

## 🏛️ Why This Project Is Hard

> *"Not all government sites are equal. This one fights back at the SSL layer."*

```
Standard Python requests  →  ConnectionResetError(10054)  ✗  [SSL handshake rejected]
curl_cffi Chrome TLS       →  HTTP 200 OK                 ✓  [Invisible to WAF]
```

Connecticut Judicial Branch runs **Microsoft IIS with JA3 TLS fingerprinting** — the server identifies Python's `urllib3` from the shape of its SSL ClientHello and drops the connection before any HTTP exchange. This is more sophisticated than Cloudflare, which at least returns a 403. Here, the connection just dies.

Beyond that, the site's ASP.NET WebForms architecture requires maintaining `__VIEWSTATE` tokens across every page navigation, all data is stored in `<span id="lblXxx">` controls (not standard table cells), and the SQLite checkpoint must be thread-safe across 5 parallel workers.

---

## 🧠 Technical Challenges Solved

### 1. TLS Fingerprint Bypass

**Problem:** `ConnectionResetError(10054)` at SSL handshake — server uses JA3 fingerprinting to block Python bots before any HTTP request is made.

**Solution:** `curl_cffi` with `impersonate="chrome120"` replicates Chrome's exact TLS signature.

```python
from curl_cffi import requests

# Standard requests → ❌ ConnectionResetError(10054) at SSL layer
# curl_cffi         → ✅ HTTP 200 — server cannot distinguish from real Chrome

session = requests.Session(impersonate="chrome120")
resp = session.get("https://appellateinquiry.jud.ct.gov/CaseDetail.aspx?CRN=72391", timeout=25)
```

---

### 2. ASP.NET VIEWSTATE — Skipped Entirely

**Problem:** Search results use stateful POST-based pagination. Every page navigation requires `__VIEWSTATE` + `__EVENTVALIDATION` tokens from the previous response — and these expire.

**Solution:** Skip pagination completely. Use **binary search** to find the maximum valid CRN, then iterate CRNs directly to `CaseDetail.aspx`.

```python
# find_max_crn.py — finds max valid integer ID in ~3 minutes
# Step 1: exponential probe  →  Step 2: binary search  →  Step 3: linear scan

def find_max_crn(session):
    probe = 100_000
    while check_crn(session, probe) != "empty":
        probe *= 2                          # 100K → 200K → 400K...
    upper, lower = probe, probe // 2

    while upper - lower > 100:             # Binary search
        mid = (lower + upper) // 2
        if check_crn(session, mid) in ("valid", "sealed"):
            lower = mid
        else:
            upper = mid
    return lower                            # Result: 80,392
```

---

### 3. ASP.NET Span-ID Parser

**Problem:** All data lives in `<span id="lblDateFiled">` ASP.NET server controls — not in label/value table cells. Generic `parse_kv()` returns empty results for 100% of fields.

**Solution:** Target exact span IDs directly.

```python
def parse_appeal(soup):
    def sp(id_): return txt(soup.find(id=id_))
    return {
        "date_filed":         sp("lblDateFiled"),
        "appeal_by":          sp("lblAppealBy"),
        "disposition_method": sp("lblDispMethod"),
        "disposition_date":   sp("lblDispDt"),
        "panel":              sp("lblPanel"),
        "cite":               sp("lblRescript"),
    }

def parse_trial_court(soup):
    def sp(id_): return txt(soup.find(id=id_))
    tc_docket = ", ".join(
        a.get_text(strip=True)
        for a in (soup.find("table", {"id": "dlTCDockets"}) or []).find_all("a")
    )
    return {
        "tc_docket_number": tc_docket,
        "court":            sp("lblCourt"),
        "trial_judge":      sp("lblTrialJudge"),
        "judgment_date":    sp("lblJudgementdate"),
        "case_type":        sp("lblCaseType"),
    }
```

---

### 4. Thread-Safe Parallel Scraping

**Problem:** SQLite does not support concurrent writes from multiple threads — `database is locked` errors corrupt data.

**Solution:** **Fetch-Only Pattern** — workers fetch HTML only, the main thread handles all writes.

```
┌─────────────────────────────────────────────┐
│  curl_cffi Chrome TLS Session               │
│                                             │
│  Worker 1 (fetch)  ─┐                       │
│  Worker 2 (fetch)  ─┼──► as_completed() ──► Main Thread │
│  Worker 3 (fetch)  ─┤                  │    │  save_all(conn, data)  │
│  Worker 4 (fetch)  ─┘                  │    │  save_sealed(conn, crn)│
│  Worker 5 (fetch)  ─                   └──► └──────────────────────┘│
└─────────────────────────────────────────────┘
         No Lock needed — SQLite write is single-threaded
```

```python
for chunk in chunks(crn_list, 100):
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_crn, crn): crn for crn in chunk}
        for future in as_completed(futures):
            crn, data, status = future.result()
            if status == "ok":
                save_all(conn, data)          # Main thread only
            elif status == "sealed":
                save_sealed(conn, crn)        # Main thread only
```

---

### 5. Resumable Checkpoint System

SQLite tracks every CRN's state. Stop the scraper anytime — restart and it picks up exactly where it left off.

```
CRN status flow:

   [pending]  →  [processing]  →  [done]
                              ↘  [sealed]   ← confidential / not available
                              ↘  [failed]   ← max retries exceeded
```

Auto-resume on restart:
```python
# Re-scrape mode: reads pending CRNs from DB, not from range
pending = conn.execute("SELECT crn FROM cases WHERE scrape_status='pending'").fetchall()
# → Continues from exactly where it stopped
```

---

## 🗂️ Output Structure

**9 linked tabs** — all connected via `Docket Number` as the primary key.

| # | Tab | Key Fields | Rows |
|:-:|:----|:-----------|-----:|
| 1 | `Case Information` | AC/SC number, case title, status | 56,598 |
| 2 | `Appeal Case Info` | Filed date, appeal by, disposition, panel, cite | 56,598 |
| 3 | `Cross Appeal` | Cross appeal / amended appeal data | variable |
| 4 | `Trial Court Info` | TC docket, court, judge, case type, judgment | 56,598 |
| 5 | `Party Attorney` | **One row per juris** — attorney name, firm, role | **187,590** |
| 6 | `Transcripts Exhibits` | Party, order date, due date, filed date, pages | 46,647 |
| 7 | `Preliminary Papers` | Party, due / filed / received / sent dates | 76,081 |
| 8 | `Briefs Prepared Record` | Party, brief type, due / filed / received dates | 98,979 |
| 9 | `Case Activity` | Activity, date filed, description, initiated by | **440,163** |

> All document links are clickable hyperlinks in Excel. Tab `5_Party Attorney` contains **one row per attorney (juris number)** — a key client requirement.

---

## 🚀 Quick Start

### Install

```bash
pip install curl_cffi beautifulsoup4 lxml openpyxl pandas
```

### Run Order

```bash
# Step 1 — Initialize database
python setup_db.py

# Step 2 — Find maximum valid CRN (~3 minutes)
python find_max_crn.py

# Step 3 — Scrape all cases  [~11 hours, fully resumable]
python phase_combined.py

# Step 4 — Monitor progress in a second terminal
python monitor.py

# Step 5 — Build 9-tab Excel output
python phase3_build_excel.py

# Step 6 — Validate before delivery
python phase4_validate.py
```

### Configuration

```python
# phase_combined.py — top of file
CRN_END    = 96470   # From find_max_crn.py output
WORKERS    = 5       # 3 = safe  |  5 = recommended  |  8 = max
DELAY_MIN  = 1.0     # Seconds between requests per worker
DELAY_MAX  = 2.5
```

---

## 📁 File Structure

```
ct-appellate-court-scraper/
│
├── setup_db.py              ← Initialize SQLite schema (run once)
├── find_max_crn.py          ← Binary search for max valid CRN
├── audit.py                 ← Site structure audit tool
│
├── phase_combined.py        ← Main scraper — Phase 1 + 2 merged
├── phase3_build_excel.py    ← Export database to 9-tab Excel
├── phase4_validate.py       ← Pre-delivery QC report
├── monitor.py               ← Real-time progress display
│
├── migrate_db.py            ← Reset schema for re-scrapes
├── check_errors.py          ← Error diagnosis
├── check_coverage.py        ← Coverage vs target analysis
├── reset_and_retry.py       ← Full reset + retry
│
├── scraper.db               ← SQLite database (auto-created)
└── data/
    └── final/
        └── CT_Appellate_Cases_YYYYMMDD_HHMM.xlsx
```

---

## 📊 Live Monitor

```
[XXXXXXXXXXXXXXXXXXXXXXXXXX..............] 64.3%
CRNdone: 62,000 / 96,470   ValidCases: 36,142   Sealed: 25,858
MaxCRN:  62,000             Parties:   119,834   Acts:   264,600
Briefs:  63,471             ETA: 3.8h
```

---

## ⚠️ Notes

| Note | Detail |
|:-----|:-------|
| **Sealed cases** | ~39,872 CRNs are confidential under Connecticut law — correctly skipped and logged |
| **224K figure** | Client's "224K" = rows in SearchResults (1 case × N attorneys = N rows), not unique cases |
| **Lawful access** | This scraper accesses only public records. Respect server rate limits and `robots.txt` |
| **Re-scraping** | Run `migrate_db.py` to reset, then `phase_combined.py` auto-detects pending CRNs |

---

## 👤 Author

<div align="center">

**Sandi Ridwan**
*Data Automation Engineer & Web Scraping Specialist — Palu, Indonesia*

[![Upwork](https://img.shields.io/badge/Upwork-Hire%20Me-6FDA44?style=for-the-badge&logo=upwork&logoColor=white)](https://upwork.com)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com)

<br/>

<sub>Built with precision. Scraped with integrity.</sub>

</div>
