"""
test_edgar_index.py
-------------------
Exploration script — finds the primary 10-K document from EDGAR
and downloads it for one company/year before we update downloader.py.

Test case: Apple 2020 10-K
  CIK       : 320193
  Accession  : 0000320193-20-000096
  Nodashes   : 000032019320000096
"""

import os
import requests
from html.parser import HTMLParser

HEADERS = {
    "User-Agent": "SEC Filing Intelligence System shri2061ram@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

CIK          = "320193"
ACCESSION    = "0000320193-20-000096"
ACC_NODASHES = ACCESSION.replace("-", "")
SAVE_PATH    = "AAPL_2020_test.htm"


# ---------------------------------------------------------------------------
# Step 1 — Fetch the directory listing HTML
# ---------------------------------------------------------------------------

class LinkParser(HTMLParser):
    """Collects every href value from <a> tags."""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self.links.append(val)


def fetch_directory_links(cik: str, acc_nodashes: str) -> list[str]:
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodashes}/"
    print(f"\n{'='*60}")
    print(f"STEP 1 — Fetching directory listing")
    print(f"URL : {url}")
    print(f"{'='*60}")

    r = requests.get(url, headers=HEADERS, timeout=30)
    print(f"Status : {r.status_code}")

    parser = LinkParser()
    parser.feed(r.text)

    print(f"Total links found : {len(parser.links)}")
    for link in parser.links:
        print(f"  {link}")

    return parser.links


# ---------------------------------------------------------------------------
# Step 2 — Identify the primary 10-K document URL
#
# From our test we saw the primary doc is linked via the iXBRL viewer:
#   /ix?doc=/Archives/edgar/data/320193/.../aapl-20200926.htm
#
# Strip the "/ix?doc=" prefix to get the actual document path.
# Fallback: any link inside the filing directory ending in .htm
#           that is NOT an exhibit (doesn't contain "exhibit" in name).
# ---------------------------------------------------------------------------

def find_primary_doc(links: list[str], cik: str, acc_nodashes: str) -> str | None:
    filing_path = f"/Archives/edgar/data/{cik}/{acc_nodashes}/"

    print(f"\n{'='*60}")
    print(f"STEP 2 — Finding primary 10-K document")
    print(f"{'='*60}")

    # Pass 1 — iXBRL viewer link  (/ix?doc=...)
    print(f"\nPass 1: Looking for iXBRL viewer link (/ix?doc=) ...")
    for link in links:
        if link.startswith("/ix?doc=") and acc_nodashes in link and link.endswith(".htm"):
            actual_path = link.replace("/ix?doc=", "")
            full_url    = "https://www.sec.gov" + actual_path
            print(f"  [FOUND via iXBRL] {full_url}")
            return full_url

    # Pass 2 — Direct .htm link inside the filing directory, excluding exhibits
    print(f"  No iXBRL link found.")
    print(f"\nPass 2: Looking for direct .htm inside filing directory (no exhibits) ...")
    for link in links:
        if filing_path in link and link.endswith(".htm") and "exhibit" not in link.lower():
            full_url = "https://www.sec.gov" + link
            print(f"  [FOUND direct htm] {full_url}")
            return full_url

    # Pass 3 — Any .htm inside the filing directory
    print(f"  No non-exhibit htm found.")
    print(f"\nPass 3: Any .htm inside filing directory ...")
    for link in links:
        if filing_path in link and link.endswith(".htm"):
            full_url = "https://www.sec.gov" + link
            print(f"  [FOUND fallback htm] {full_url}")
            return full_url

    print(f"  [NOT FOUND] No suitable document found in any pass.")
    return None


# ---------------------------------------------------------------------------
# Step 3 — Download the document and save to disk
# ---------------------------------------------------------------------------

def download_doc(url: str, save_path: str) -> bool:
    print(f"\n{'='*60}")
    print(f"STEP 3 — Downloading document")
    print(f"URL       : {url}")
    print(f"Save path : {save_path}")
    print(f"{'='*60}")

    r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
    print(f"Status : {r.status_code}")

    if r.status_code != 200:
        print(f"[FAIL] Bad status code — aborting")
        return False

    bytes_written = 0
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
            bytes_written += len(chunk)

    size_kb = bytes_written / 1024
    print(f"[OK] Downloaded {size_kb:.1f} KB → {save_path}")
    return True


# ---------------------------------------------------------------------------
# Step 4 — Verify file contents are the correct 10-K
# Strip HTML tags, extract plain text, check for key markers
# ---------------------------------------------------------------------------

class TextExtractor(HTMLParser):
    """Strips all HTML/XML tags and collects visible text."""
    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip  = False

    def handle_starttag(self, tag, attrs):
        # Skip script and style blocks entirely
        if tag in ("script", "style", "ix:header", "ix:hidden"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "ix:header", "ix:hidden"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.chunks.append(text)

    def get_text(self) -> str:
        return " ".join(self.chunks)


def verify_content(save_path: str) -> None:
    print(f"\n{'='*60}")
    print(f"STEP 4 — Verifying file content")
    print(f"{'='*60}")

    if not os.path.exists(save_path):
        print(f"[FAIL] File does not exist: {save_path}")
        return

    size_kb = os.path.getsize(save_path) / 1024
    print(f"File size : {size_kb:.1f} KB")

    with open(save_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_html = f.read()

    # Extract plain text
    extractor = TextExtractor()
    extractor.feed(raw_html)
    plain_text = extractor.get_text()

    print(f"Plain text extracted : {len(plain_text):,} characters")

    # --- Key term checks ---
    checks = {
        "Company name 'Apple'"        : "apple"                   in plain_text.lower(),
        "Form type '10-K'"            : "10-k"                    in plain_text.lower(),
        "Year '2020'"                 : "2020"                    in plain_text,
        "Fiscal year reference"       : "fiscal 2020"             in plain_text.lower()
                                        or "september 2020"       in plain_text.lower()
                                        or "september 26, 2020"   in plain_text.lower(),
        "Revenue / Net sales"         : "net sales"               in plain_text.lower()
                                        or "total net sales"      in plain_text.lower(),
        "Risk factors section"        : "risk factors"            in plain_text.lower(),
        "MD&A section"                : "management" + "'s"       in plain_text.lower()
                                        or "results of operations" in plain_text.lower(),
        "iPhone mentioned"            : "iphone"                  in plain_text.lower(),
    }

    print(f"\n--- Content verification checks ---")
    all_passed = True
    for label, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status}  {label}")
        if not result:
            all_passed = False

    # --- Show a readable text sample ---
    print(f"\n--- Plain text sample (chars 2000–3000) ---")
    print(f"{'─'*50}")
    print(plain_text[2000:3000])
    print(f"{'─'*50}")

    # --- Search for revenue number ---
    import re
    revenue_matches = re.findall(r'(?i)(net sales|total revenue)[^\d]{0,30}(\$?[\d,]+)', plain_text)
    print(f"\n--- Revenue figures found ---")
    if revenue_matches:
        for match in revenue_matches[:5]:
            print(f"  '{match[0]}' → {match[1]}")
    else:
        print(f"  None found in quick scan")

    print(f"\n{'='*60}")
    if all_passed:
        print(f"✅  ALL CHECKS PASSED — correct Apple 2020 10-K confirmed")
    else:
        print(f"⚠️   SOME CHECKS FAILED — inspect the file manually")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Test filing : Apple 2020 10-K")
    print(f"CIK         : {CIK}")
    print(f"Accession   : {ACCESSION}")
    print(f"Nodashes    : {ACC_NODASHES}")
    print(f"Save path   : {SAVE_PATH}")

    # Step 1 — get all links from directory listing
    links = fetch_directory_links(CIK, ACC_NODASHES)

    # Step 2 — identify primary document URL
    doc_url = find_primary_doc(links, CIK, ACC_NODASHES)

    if not doc_url:
        print(f"\n[ABORT] Could not find primary document. Nothing to download.")
    else:
        # Step 3 — download it
        ok = download_doc(doc_url, SAVE_PATH)

        # Step 4 — verify the file looks right
        if ok:
            verify_content(SAVE_PATH)
