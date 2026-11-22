"""Numbers and units as printed in filings. Shared by the engine checks and the evaluation.

- `number_patterns(value)`: find a value as printed ("1,788", "(1,788)", "1.8 billion").
- `normalise(value, unit)`: a value in its base unit, with a family (usd / pct / count).
"""

from __future__ import annotations

import re

_SHORT_SCALES = ((1e9, "billion"), (1e6, "million"))
SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
SCALE_RE = re.compile(r"\b(thousands?|millions?|billions?|trillions?|k|mn|m|bn|b)\b")
SCALE_ALIASES = {"k": "thousand", "mn": "million", "m": "million", "bn": "billion", "b": "billion"}


def num_forms(x: float) -> set[str]:
    """How a number can be printed: 1788 -> {"1,788", "1788"}; 15.48 -> {"15.48"}."""
    x = abs(x)
    if float(x).is_integer():
        n = int(x)
        return {f"{n:,}", str(n)} | ({f"{n}.0"} if n < 1000 else set())
    text = f"{x:.6f}".rstrip("0").rstrip(".")
    whole, _, frac = text.partition(".")
    return {text, f"{int(whole):,}.{frac}"}


def number_patterns(value: float) -> list[re.Pattern[str]]:
    """Patterns that find `value` as printed in a filing.

    The plain forms ("1,788", "15.48") must not be part of a longer number. Large values also
    match the short forms ("850 million", "3 billion"). A negative value matches its absolute
    value, because tables print a decrease as "(1,234)"."""
    edge_l, edge_r = r"(?<![\d.,])", r"(?![\d]|[.,]\d)"
    forms = num_forms(value)
    out = [re.compile(edge_l + re.escape(f) + edge_r) for f in sorted(forms)]
    for scale, word in _SHORT_SCALES:
        if abs(value) >= scale:
            for f in sorted(num_forms(abs(value) / scale)):
                out.append(re.compile(edge_l + re.escape(f) + r"\s*" + word, re.IGNORECASE))
    return out


def has_number(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def unit_scale(unit: str | None) -> float:
    """The scale word in a unit: "USD million" -> 1e6; "USD" or "%" -> 1."""
    m = SCALE_RE.search((unit or "").lower())
    if not m:
        return 1.0
    word = m.group(1).rstrip("s")
    return SCALES[SCALE_ALIASES.get(word, word)]


def unit_family(unit: str | None) -> str:
    """pct (percent, basis points), usd, or count (shares, stores, units)."""
    u = (unit or "").lower()
    if "%" in u or "percent" in u or "basis point" in u or "bps" in u:
        return "pct"
    return "usd" if ("usd" in u or "$" in u or "dollar" in u) else "count"


def normalise(value: float, unit: str | None) -> tuple[str, float]:
    """Return (family, value in the base unit). Basis points become percent."""
    u = (unit or "").lower()
    if "basis point" in u or "bps" in u:
        return "pct", value / 100
    family = unit_family(unit)
    return family, value if family == "pct" else value * unit_scale(unit)
