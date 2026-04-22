"""
downloader.py
-------------
Downloads 10-K filings (HTM format) from SEC EDGAR for 5 companies x 5 years.

Flow per filing:
  1. Hit EDGAR Submissions API   -> find accession number by (CIK + reportDate year)
  2. Hit filing directory listing -> find primary .htm document URL
  3. Download HTM                 -> save to data/raw/{TICKER}_{YEAR}.htm

Retries: 3 attempts per HTTP call. 2-second delay between all requests.
Skips filings where no HTM document is found (logs clearly).

Note: All 5 companies (Apple, Microsoft, Amazon, Google, Meta) file their
10-Ks as iXBRL HTML documents on EDGAR — no PDF versions exist.
"""

import os
import time
import requests
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAW_DATA_DIR = os.path.join("data", "raw")

COMPANIES = {
    "Apple":     {"ticker": "AAPL",  "cik": "320193"},
    "Microsoft": {"ticker": "MSFT",  "cik": "789019"},
    "Amazon":    {"ticker": "AMZN",  "cik": "1018724"},
    "Google":    {"ticker": "GOOGL", "cik": "1652044"},
    "Meta":      {"ticker": "META",  "cik": "1326801"},
}

YEARS = [2020, 2021, 2022, 2023, 2024]

MAX_RETRIES = 3
DELAY       = 2   # seconds between every HTTP request

# SEC requires a descriptive User-Agent with contact info
HEADERS = {
    "User-Agent": "SEC Filing Intelligence System shri2061ram@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str) -> requests.Response | None:
    """
    GET request with retry logic.
    Waits DELAY seconds before each attempt.
    Returns the Response on success, None if all retries fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"    --> GET (attempt {attempt}/{MAX_RETRIES}): {url}")
        time.sleep(DELAY)
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            print(f"    <-- HTTP {response.status_code} OK")
            return response
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                print(f"    [RETRY {attempt}/{MAX_RETRIES}] {e}")
            else:
                print(f"    [FAILED] All {MAX_RETRIES} attempts exhausted for:\n    {url}\n    Error: {e}")
    return None


# ---------------------------------------------------------------------------
# Step 1 — Find accession number
# ---------------------------------------------------------------------------

def _search_filings_block(block: dict, year: int) -> tuple[str | None, str | None]:
    """
    Searches a single filings block (recent or a paginated older block)
    for a 10-K whose reportDate starts with the target year.

    Returns (accession_number, primary_document) tuple.
    `primary_document` is the filename EDGAR marks as the primary 10-K doc
    (e.g. 'aapl-20200926.htm'). Reading this field directly avoids guessing
    which .htm in the directory is the real 10-K body.
    """
    forms         = block.get("form", [])
    report_dates  = block.get("reportDate", [])
    accessions    = block.get("accessionNumber", [])
    primary_docs  = block.get("primaryDocument", [])

    print(f"    Scanning block: {len(forms)} total filings, looking for 10-K with reportDate {year}-xx-xx")

    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        report_date  = report_dates[i]   # e.g. "2023-09-30"
        primary_doc  = primary_docs[i] if i < len(primary_docs) else ""
        print(f"    Found 10-K — reportDate: {report_date}, accession: {accessions[i]}, primaryDoc: {primary_doc}")
        if report_date and report_date.startswith(str(year)):
            print(f"    [MATCH] reportDate {report_date} matches target year {year}")
            return accessions[i], primary_doc

    print(f"    No matching 10-K found in this block for year {year}")
    return None, None


def get_accession_and_primary_doc(cik: str, year: int) -> tuple[str | None, str | None]:
    """
    Calls EDGAR Submissions API and finds the 10-K whose reportDate year
    matches the target year.

    Searches the 'recent' block first. If not found, follows pagination
    links in 'filings.files' to fetch older filing batches.

    Returns (accession_number, primary_document) — e.g.
        ('0000320193-20-000096', 'aapl-20200926.htm')
    Either or both may be None if not found.
    """
    padded_cik = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    print(f"  Fetching EDGAR submissions for CIK {cik} ...")
    response = _get(url)
    if response is None:
        return None, None

    data     = response.json()
    filings  = data.get("filings", {})

    # --- Search recent block first ---
    print(f"  Searching 'recent' filings block ...")
    recent = filings.get("recent", {})
    accession, primary_doc = _search_filings_block(recent, year)
    if accession:
        return accession, primary_doc

    # --- Search older paginated blocks ---
    older_files = filings.get("files", [])
    print(f"  Not found in 'recent'. Found {len(older_files)} older paginated block(s) to check ...")
    for idx, file_info in enumerate(older_files, start=1):
        file_name = file_info.get("name", "")
        if not file_name:
            continue
        print(f"  Checking older block {idx}/{len(older_files)}: {file_name}")
        older_url = f"https://data.sec.gov/submissions/{file_name}"
        older_response = _get(older_url)
        if older_response is None:
            continue
        older_block = older_response.json()
        accession, primary_doc = _search_filings_block(older_block, year)
        if accession:
            return accession, primary_doc

    print(f"  [NOT FOUND] No 10-K found for year {year} across all blocks")
    return None, None


# ---------------------------------------------------------------------------
# Step 2 — Find primary HTM document inside the filing package
# ---------------------------------------------------------------------------

class _LinkParser(HTMLParser):
    """Collects every href value from <a> tags in a directory listing."""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self.links.append(val)


def get_doc_url(cik: str, accession: str, primary_doc: str | None = None) -> str | None:
    """
    Returns the full URL of the primary 10-K document.

    Preferred path:
      If `primary_doc` is provided (from EDGAR Submissions API's
      `primaryDocument` field), build the URL directly — no guessing.
      This is the authoritative source and avoids picking up exhibits.

    Fallback path (only if primary_doc is missing):
      Scrape the filing directory listing HTML with a 3-pass heuristic:
        1. iXBRL viewer link (/ix?doc=...)
        2. Direct .htm in filing dir, no 'exhibit' in filename
        3. Any .htm in the filing directory — last resort

    Returns full download URL or None if nothing found.
    """
    accession_nodashes = accession.replace("-", "")
    dir_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodashes}/"
    )
    filing_path = f"/Archives/edgar/data/{cik}/{accession_nodashes}/"

    # --- Preferred: use primaryDocument from Submissions API ---
    if primary_doc:
        full_url = f"https://www.sec.gov{filing_path}{primary_doc}"
        print(f"  [PRIMARY DOC] Using EDGAR primaryDocument field: {primary_doc}")
        print(f"  [URL] {full_url}")
        return full_url

    # --- Fallback: scrape directory listing ---
    print(f"  [FALLBACK] No primaryDocument — scraping directory listing")
    print(f"  Fetching filing directory: {dir_url}")
    response = _get(dir_url)
    if response is None:
        return None

    parser = _LinkParser()
    parser.feed(response.text)
    links = parser.links
    print(f"  Directory loaded — {len(links)} links found")

    # Pass 1 — iXBRL viewer link  (/ix?doc=...)
    print(f"  Pass 1: iXBRL viewer link (/ix?doc=) ...")
    for link in links:
        if link.startswith("/ix?doc=") and accession_nodashes in link and link.endswith(".htm"):
            actual_path = link.replace("/ix?doc=", "")
            full_url    = "https://www.sec.gov" + actual_path
            print(f"  [FOUND — Pass 1] {full_url}")
            return full_url

    # Pass 2 — Direct .htm inside filing dir, no 'exhibit' in name
    print(f"  Pass 2: direct .htm (no exhibits) ...")
    for link in links:
        if filing_path in link and link.endswith(".htm") and "exhibit" not in link.lower():
            full_url = "https://www.sec.gov" + link
            print(f"  [FOUND — Pass 2] {full_url}")
            return full_url

    # Pass 3 — Any .htm inside filing directory
    print(f"  Pass 3: any .htm in directory ...")
    for link in links:
        if filing_path in link and link.endswith(".htm"):
            full_url = "https://www.sec.gov" + link
            print(f"  [FOUND — Pass 3] {full_url}")
            return full_url

    print(f"  [NO DOC] No .htm document found in filing directory")
    return None


# ---------------------------------------------------------------------------
# Step 3 — Download the HTM document
# ---------------------------------------------------------------------------

def download_doc(doc_url: str, save_path: str) -> bool:
    """
    Downloads HTM document from url and saves to save_path.
    Uses streaming to handle large files.
    Returns True on success, False if all retries fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Download attempt {attempt}/{MAX_RETRIES} ...")
        time.sleep(DELAY)
        try:
            response = requests.get(
                doc_url, headers=HEADERS, timeout=60, stream=True
            )
            response.raise_for_status()
            print(f"  HTTP {response.status_code} — streaming to disk ...")
            bytes_written = 0
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    bytes_written += len(chunk)
            print(f"  Download complete — {bytes_written / (1024*1024):.2f} MB written")
            return True
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                print(f"    [RETRY {attempt}/{MAX_RETRIES}] Download error: {e}")
            else:
                print(f"    [FAILED] Could not download after {MAX_RETRIES} attempts: {e}")
    return False


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def download_all() -> None:
    """
    Loops over all 25 company-year combinations and downloads each 10-K HTM.
    Skips files that already exist on disk.
    """
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    total   = len(COMPANIES) * len(YEARS)
    success = 0
    skipped = 0
    no_doc  = 0
    failed  = 0

    current = 0
    for company, info in COMPANIES.items():
        ticker = info["ticker"]
        cik    = info["cik"]

        for year in YEARS:
            current   += 1
            save_path  = os.path.join(RAW_DATA_DIR, f"{ticker}_{year}.htm")
            print(f"\n{'='*55}")
            print(f"  [{current}/{total}]  {company} ({ticker}) — {year}")
            print(f"{'='*55}")

            # Already downloaded — skip
            if os.path.exists(save_path):
                print(f"  [SKIP] File already exists: {save_path}")
                skipped += 1
                continue

            # Step 1 — accession number + primary document filename
            print(f"  Searching EDGAR submissions ...")
            accession, primary_doc = get_accession_and_primary_doc(cik, year)
            if not accession:
                print(f"  [FAIL] No 10-K accession found for {company} {year}")
                failed += 1
                continue
            print(f"  Accession   : {accession}")
            print(f"  Primary doc : {primary_doc or '(missing — will fallback to directory scrape)'}")

            # Step 2 — build primary HTM document URL
            print(f"  Resolving primary document URL ...")
            doc_url = get_doc_url(cik, accession, primary_doc)
            if not doc_url:
                print(f"  [NO DOC] No HTM document found for {company} {year} — skipping")
                no_doc += 1
                continue
            print(f"  Document URL: {doc_url}")

            # Step 3 — Download
            print(f"  Downloading ...")
            ok = download_doc(doc_url, save_path)
            if ok:
                size_mb = os.path.getsize(save_path) / (1024 * 1024)
                print(f"  [OK] Saved → {save_path}  ({size_mb:.1f} MB)")
                success += 1
            else:
                print(f"  [FAIL] FAILED: {company} {year} — could not download")
                failed += 1

    # Summary
    print(f"\n{'='*55}")
    print(f"  DOWNLOAD SUMMARY")
    print(f"{'='*55}")
    print(f"  Total    : {total}")
    print(f"  Success  : {success}")
    print(f"  Skipped  : {skipped}  (already existed)")
    print(f"  No doc   : {no_doc}  (no HTM found in EDGAR filing)")
    print(f"  Failed   : {failed}  (network / not found)")
    print(f"{'='*55}")


if __name__ == "__main__":
    print('Start download Script')
    download_all()
