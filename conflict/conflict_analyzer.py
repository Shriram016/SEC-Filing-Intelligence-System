"""
conflict/conflict_analyzer.py

Component 15 — Cross-Year Conflict Analyzer

For a given company + section + year range:
  1. Generates all C(n,2) year pairs within the range
  2. Reads full section text for each year from _sections.json
  3. Calls analyze_pair() for every pair — one Groq LLM call per pair
  4. Returns a list of conflict results, one dict per pair

Two public functions:
  analyze_pair()      — analyzes one pair, independently testable
  analyze_conflicts() — public API called by the UI, loops over all pairs

Run from project root:
  python conflict/conflict_analyzer.py
"""

import json
import os
import re
import time
from itertools import combinations

from groq import Groq
from dotenv import load_dotenv

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CONFLICT_MODEL, PROCESSED_DATA_DIR, TARGET_SECTIONS

load_dotenv()

# ── Constants ────────────────────────────────────────────────────────────────

TICKER_MAP = {
    "Apple":     "AAPL",
    "Microsoft": "MSFT",
    "Amazon":    "AMZN",
    "Google":    "GOOGL",
    "Meta":      "META",
}

MAX_WORDS_PER_YEAR = 3500   # Groq free tier TPM limit: 12,000 tokens/min for llama-3.3-70b-versatile.
                            # Budget: 12K total − 1,024 (output) − 400 (prompt) = ~10,576 for text.
                            # 3,500 words/year × 2 years × 1.23 tokens/word ≈ 8,610 tokens. Safe margin.

INTER_CALL_DELAY = 65       # seconds to wait between pairs — lets the 12,000 TPM quota refill.


# ── Private helpers ──────────────────────────────────────────────────────────

def _load_section_text(company: str, section: str, year: int, logger=None) -> str:
    """
    Read full section text from _sections.json for a given company/section/year.
    File structure: { "ticker": ..., "year": ..., "sections": { "Item 1A": "..." } }
    """
    ticker = TICKER_MAP[company]
    path   = os.path.join(PROCESSED_DATA_DIR, f"{ticker}_{year}_sections.json")

    if logger:
        logger.info(f"CONFLICT | load_section | ENTER | company={company} section={section} year={year}")
        logger.info(f"CONFLICT | load_section | file={path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    text = data.get("sections", {}).get(section, "")
    if not text:
        raise ValueError(f"Section '{section}' not found in {path}")

    # Truncate to fit within Groq free tier token limit
    words = text.split()
    if len(words) > MAX_WORDS_PER_YEAR:
        print(f"  [TRUNCATED] {company} {year} {section}: {len(words):,} words → {MAX_WORDS_PER_YEAR:,}")
        if logger:
            logger.warning(
                f"CONFLICT | load_section | TRUNCATED | "
                f"{company} {year} {section}: {len(words):,} words → {MAX_WORDS_PER_YEAR:,}"
            )
        text = " ".join(words[:MAX_WORDS_PER_YEAR])
    else:
        print(f"  [OK] {company} {year} {section}: {len(words):,} words (no truncation needed)")
        if logger:
            logger.info(
                f"CONFLICT | load_section | OK | "
                f"{company} {year} {section}: {len(words):,} words (no truncation)"
            )

    if logger:
        logger.info(f"CONFLICT | load_section | EXIT | text_length={len(text)} chars")

    return text


# ── Core functions ───────────────────────────────────────────────────────────

def analyze_pair(
    company: str,
    section: str,
    year_a: int,
    year_b: int,
    text_a: str,
    text_b: str,
    logger=None,
) -> dict:
    """
    Analyzes one year pair for conflicts using the LLM.

    Returns:
    {
        "company":        str,
        "section":        str,
        "year_a":         int,
        "year_b":         int,
        "conflicts": [
            {
                "topic":              str,
                "year_a_claim":       str,
                "year_b_claim":       str,
                "change_description": str,
                "severity":           "high" | "medium" | "low" | "none"
            },
            ...   # up to 3
        ],
        "conflict_count": int   # 0 if all severities are "none"
    }
    """
    if logger:
        logger.info(
            f"CONFLICT | analyze_pair | ENTER | "
            f"company={company} section={section} year_a={year_a} year_b={year_b}"
        )
        logger.info(
            f"CONFLICT | analyze_pair | text_lengths | "
            f"year_a={len(text_a.split())} words year_b={len(text_b.split())} words"
        )

    client       = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    section_name = TARGET_SECTIONS.get(section, section)

    system_prompt = (
        f"You are a financial analyst reviewing SEC 10-K filings for {company}. "
        "Your job is to identify specific factual conflicts, contradictions, or material "
        "changes in disclosure language between two filing years. "
        "Be precise and evidence-based. Quote or closely paraphrase the actual filing text."
    )

    user_prompt = f"""Compare the {section_name} sections from {company}'s {year_a} and {year_b} 10-K filings.

Identify up to 3 specific conflicts, contradictions, or material changes between the two years.

For each conflict provide:
- topic: the specific subject (e.g. "Supply chain concentration risk")
- year_a_claim: what the {year_a} filing said — direct quote or close paraphrase
- year_b_claim: what the {year_b} filing said — direct quote or close paraphrase
- change_description: what materially changed and why it matters to an investor
- severity: exactly one of "high", "medium", "low", or "none"

Severity definitions:
- high   — a material risk or claim in {year_a} is directly contradicted, completely removed, or reversed in {year_b}
- medium — the same topic exists in both years but language is materially softened, strengthened, or reframed
- low    — minor wording changes only, no material difference in substance
- none   — no meaningful conflict detected

If there are no meaningful conflicts, return a single entry with severity "none" and a brief explanation in change_description.

Return ONLY valid JSON — no text before or after the JSON block:
{{
  "conflicts": [
    {{
      "topic": "...",
      "year_a_claim": "...",
      "year_b_claim": "...",
      "change_description": "...",
      "severity": "high"
    }}
  ]
}}

=== {company} {section_name} — {year_a} ===
{text_a}

=== {company} {section_name} — {year_b} ===
{text_b}"""

    if logger:
        logger.info(f"CONFLICT | analyze_pair | Groq call | model={CONFLICT_MODEL} max_tokens=1024 temperature=0")

    response = client.chat.completions.create(
        model=CONFLICT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content.strip()

    if logger:
        logger.info(f"CONFLICT | analyze_pair | Groq response | raw_length={len(raw)} chars")

    # Parse JSON — extract the JSON block even if the LLM adds surrounding text
    try:
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            parsed    = json.loads(match.group())
            conflicts = parsed.get("conflicts", [])[:3]  # cap at 3
        else:
            raise ValueError("No JSON block found in LLM response")
    except Exception as e:
        print(f"  [WARNING] JSON parse failed: {e}. Storing raw response as fallback.")
        if logger:
            logger.warning(f"CONFLICT | analyze_pair | JSON parse failed | error={e}")
        conflicts = [{
            "topic":              "Parse error — raw LLM response stored",
            "year_a_claim":       "",
            "year_b_claim":       "",
            "change_description": raw,
            "severity":           "none",
        }]

    conflict_count = sum(1 for c in conflicts if c.get("severity", "none") != "none")
    severities     = [c.get("severity", "none") for c in conflicts]

    if logger:
        logger.info(
            f"CONFLICT | analyze_pair | EXIT | "
            f"conflict_count={conflict_count} severities={severities}"
        )

    return {
        "company":        company,
        "section":        section,
        "year_a":         year_a,
        "year_b":         year_b,
        "conflicts":      conflicts,
        "conflict_count": conflict_count,
    }


def analyze_conflicts(
    company: str,
    section: str,
    start_year: int = 2020,
    end_year: int = 2024,
    verify: bool = False,
    logger=None,
) -> list:
    """
    Public API. Analyzes all C(n,2) year pairs within [start_year, end_year]
    for the given company + section.

    verify=True  — runs run_checks() after each pair (used by test script).
    verify=False — production default, no checks printed.

    Sleeps INTER_CALL_DELAY seconds between pairs to stay within Groq TPM limits.

    Returns a list of result dicts, one per pair.
    """
    years = list(range(start_year, end_year + 1))
    pairs = list(combinations(years, 2))

    print(f"\n{company} | {section} | {start_year}–{end_year}")
    print(f"Pairs to analyze: {len(pairs)}")
    print(f"Estimated time:   ~{len(pairs) * INTER_CALL_DELAY // 60 + 1} min "
          f"(rate limit: {INTER_CALL_DELAY}s between calls)")
    print("-" * 50)

    if logger:
        logger.info(
            f"CONFLICT | analyze_conflicts | ENTER | "
            f"company={company} section={section} "
            f"years={start_year}-{end_year} total_pairs={len(pairs)}"
        )

    results = []
    for i, (year_a, year_b) in enumerate(pairs):
        if i > 0:
            print(f"  [waiting {INTER_CALL_DELAY}s for TPM quota to refill...]")
            if logger:
                logger.info(
                    f"CONFLICT | analyze_conflicts | inter_call_delay | "
                    f"sleeping {INTER_CALL_DELAY}s (Groq TPM quota refill)"
                )
            time.sleep(INTER_CALL_DELAY)

        print(f"\n  Pair {i+1}/{len(pairs)}: {year_a} vs {year_b}")
        if logger:
            logger.info(f"CONFLICT | analyze_conflicts | pair {i+1}/{len(pairs)} | {year_a} vs {year_b}")

        text_a = _load_section_text(company, section, year_a, logger)
        text_b = _load_section_text(company, section, year_b, logger)
        result = analyze_pair(company, section, year_a, year_b, text_a, text_b, logger)
        print(f"  → {result['conflict_count']} conflict(s) found")

        if verify:
            run_checks(result, text_a, text_b)

        results.append(result)

    total_conflicts = sum(r["conflict_count"] for r in results)
    print(f"\n{'=' * 50}")
    print(f"SUMMARY: {total_conflicts} total conflict(s) across {len(pairs)} pairs")
    print(f"{'=' * 50}")

    if logger:
        logger.info(
            f"CONFLICT | analyze_conflicts | EXIT | "
            f"total_pairs={len(pairs)} total_conflicts={total_conflicts}"
        )

    return results


# ── Verification helpers ─────────────────────────────────────────────────────

VALID_SEVERITIES = {"high", "medium", "low", "none"}
REQUIRED_KEYS    = {"topic", "year_a_claim", "year_b_claim", "change_description", "severity"}
STOPWORDS        = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "is", "are", "was", "were", "be", "been", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "its", "their", "our", "that", "this", "which", "who", "as", "if", "not", "also",
}


def _word_overlap(claim: str, source_text: str) -> float:
    """
    What fraction of meaningful words in the claim appear in the source text.
    >0.60 → likely grounded.  <0.40 → possible hallucination, review manually.
    """
    claim_words = {
        w.lower().strip(".,;:()[]\"'")
        for w in claim.split()
        if len(w) > 3 and w.lower().strip(".,;:()[]\"'") not in STOPWORDS
    }
    if not claim_words:
        return 0.0
    source_lower = source_text.lower()
    matched = sum(1 for w in claim_words if w in source_lower)
    return matched / len(claim_words)


def run_checks(result: dict, text_a: str, text_b: str) -> bool:
    """
    Runs three checks on a result dict from analyze_pair():

    Check 1 — Structure:    all required keys present, severity values valid
    Check 2 — Conflict count: conflict_count matches actual non-'none' severities
    Check 3 — Groundedness: word overlap between LLM claims and source texts

    Returns True if all checks pass.
    """
    checks_passed = 0
    checks_total  = 0
    all_passed    = True

    year_a    = result["year_a"]
    year_b    = result["year_b"]
    conflicts = result.get("conflicts", [])

    print("\n" + "=" * 60)
    print("VERIFICATION CHECKS")
    print("=" * 60)

    # ── Check 1 — Structure ──────────────────────────────────────────────────
    print("\n[Check 1] Structure — required keys + valid severity values")
    struct_ok = True
    for i, c in enumerate(conflicts, 1):
        missing = REQUIRED_KEYS - set(c.keys())
        if missing:
            print(f"  ✗ Conflict {i}: missing keys {missing}")
            struct_ok = False
        sev = c.get("severity", "")
        if sev not in VALID_SEVERITIES:
            print(f"  ✗ Conflict {i}: invalid severity '{sev}' (must be high/medium/low/none)")
            struct_ok = False

    checks_total += 1
    if struct_ok:
        print(f"  ✓ All {len(conflicts)} conflict(s) have correct structure and valid severity labels")
        checks_passed += 1
    else:
        all_passed = False

    # ── Check 2 — Conflict count ─────────────────────────────────────────────
    print("\n[Check 2] Conflict count — conflict_count matches non-'none' severity entries")
    actual_count   = sum(1 for c in conflicts if c.get("severity", "none") != "none")
    reported_count = result.get("conflict_count", -1)
    checks_total  += 1
    if actual_count == reported_count:
        print(f"  ✓ conflict_count = {reported_count} matches {actual_count} non-'none' entry/entries")
        checks_passed += 1
    else:
        print(f"  ✗ conflict_count = {reported_count} but {actual_count} non-'none' entries found")
        all_passed = False

    # ── Check 3 — Groundedness ───────────────────────────────────────────────
    print("\n[Check 3] Groundedness — word overlap between LLM claims and source texts")
    print(f"  Threshold: >0.60 = grounded, 0.40–0.60 = review, <0.40 = likely hallucination")
    ground_ok = True
    for i, c in enumerate(conflicts, 1):
        claim_a = c.get("year_a_claim", "")
        claim_b = c.get("year_b_claim", "")
        score_a = _word_overlap(claim_a, text_a)
        score_b = _word_overlap(claim_b, text_b)
        flag_a  = "✓" if score_a >= 0.60 else ("~" if score_a >= 0.40 else "✗")
        flag_b  = "✓" if score_b >= 0.60 else ("~" if score_b >= 0.40 else "✗")
        print(f"  Conflict {i} [{c.get('severity','?').upper()}] — {c.get('topic','')}")
        print(f"    {year_a} claim overlap: {score_a:.0%}  {flag_a}")
        print(f"    {year_b} claim overlap: {score_b:.0%}  {flag_b}")
        if score_a < 0.40 or score_b < 0.40:
            ground_ok = False

    checks_total += 1
    if ground_ok:
        print(f"  ✓ All claims score ≥ 0.40 overlap with source text")
        checks_passed += 1
    else:
        print(f"  ✗ One or more claims scored <0.40 — review for hallucination")
        all_passed = False

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print(f"Checks passed: {checks_passed}/{checks_total}")
    if all_passed:
        print("STATUS: ✓ PASS")
    else:
        print("STATUS: ✗ FAIL — review flagged items above")
    print("-" * 60)

    return all_passed


# ── Single-pair test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Component 15 — Cross-Company Validation Test")
    print("Microsoft | Item 7 | 2022–2024  (3 pairs)")
    print("=" * 60)

    results = analyze_conflicts("Microsoft", "Item 7", 2022, 2024, verify=True)

    # Final printout — all conflicts across all pairs
    print("\n" + "=" * 60)
    print("FULL CONFLICT REPORT — Microsoft | Item 7 | 2022–2024")
    print("=" * 60)

    for r in results:
        print(f"\n{r['year_a']} vs {r['year_b']}  ({r['conflict_count']} conflict(s))")
        for c in r["conflicts"]:
            sev = c.get("severity", "?").upper()
            print(f"  [{sev}] {c.get('topic', '')}")
            print(f"    {r['year_a']}: {c.get('year_a_claim', '')[:120]}...")
            print(f"    {r['year_b']}: {c.get('year_b_claim', '')[:120]}...")
