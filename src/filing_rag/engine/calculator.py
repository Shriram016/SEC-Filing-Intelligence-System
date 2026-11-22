"""Calculator (engine.md §3.3, Q107, ADR-0003): code does all arithmetic.

Inputs are checked claims or earlier results, each a value with a unit. Amounts are converted
to a common scale before add / subtract; a ratio or a change is scale-free. Inputs of different
families (USD vs % vs count) are refused, and so is a division by zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from filing_rag.numbers import unit_family, unit_scale


class CalcError(ValueError):
    pass


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str | None


@dataclass(frozen=True)
class CalcResult:
    value: float
    unit: str | None
    formula: str  # e.g. "88,945 - 8,796", for the answer and the logs


def fmt_number(x: float) -> str:
    """1234.5 -> "1,234.5"; 88945.0 -> "88,945"; at most 2 decimals."""
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def _same_family(inputs: Sequence[Quantity]) -> str:
    families = {unit_family(q.unit) for q in inputs}
    if len(families) != 1:
        raise CalcError(f"inputs of different kinds: {sorted(families)}")
    return families.pop()


def _amounts(inputs: Sequence[Quantity]) -> tuple[list[float], str | None]:
    """Values in the scale of the first input (for add / subtract), and that unit."""
    family = _same_family(inputs)
    if family == "pct":
        return [q.value for q in inputs], inputs[0].unit
    base = unit_scale(inputs[0].unit)
    return [q.value * unit_scale(q.unit) / base for q in inputs], inputs[0].unit


def calculate(op: str, inputs: Sequence[Quantity]) -> CalcResult:
    if not inputs:
        raise CalcError("no inputs")
    # a negative input in parentheses: "88,945 + (-8,796)", not "88,945 + -8,796"
    shown = [fmt_number(q.value) if q.value >= 0 else f"({fmt_number(q.value)})" for q in inputs]
    if op == "add":
        if len(inputs) < 2:
            raise CalcError("add needs 2 or more inputs")
        vals, unit = _amounts(inputs)
        return CalcResult(sum(vals), unit, " + ".join(shown))
    if len(inputs) != 2:
        raise CalcError(f"{op} needs exactly 2 inputs")
    a, b = inputs
    if op == "subtract":
        vals, unit = _amounts(inputs)
        return CalcResult(vals[0] - vals[1], unit, f"{shown[0]} - {shown[1]}")
    family = _same_family(inputs)
    av, bv = (a.value, b.value) if family == "pct" else (
        a.value * unit_scale(a.unit), b.value * unit_scale(b.unit))  # fmt: skip
    if op == "pct_change":
        if av == 0:
            raise CalcError("change from zero")
        return CalcResult((bv - av) / abs(av) * 100, "%", f"({shown[1]} - {shown[0]}) / {shown[0]}")
    if bv == 0:
        raise CalcError("division by zero")
    if op == "divide":
        return CalcResult(av / bv, None, f"{shown[0]} / {shown[1]}")
    if op == "ratio_pct":
        return CalcResult(av / bv * 100, "%", f"{shown[0]} / {shown[1]} x 100")
    raise CalcError(f"unknown op: {op}")
