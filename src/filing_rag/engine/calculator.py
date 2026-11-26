"""Calculator (engine.md §3.3, Q107, ADR-0003): code does all arithmetic.

Inputs are checked claims or earlier results, each a value with a unit, or fixed numbers
(Q113: `const=True`, no unit; the caller checks which constants are allowed). Amounts are
converted to a common scale before add / subtract; a ratio or a change is scale-free. Inputs of
different families (USD vs % vs count) are refused, and so is a division by zero.

Q113 units: `multiply` takes at most one input with a unit and keeps it; `divide` by a fixed
number keeps the unit of the first input; amount / amount is a plain ratio (no unit).
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
    const: bool = False  # a fixed number (Q113), not a filing value


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


OPS = ("add", "subtract", "multiply", "divide", "ratio_pct", "pct_change")
MANY_INPUTS = ("add", "multiply")  # 2 or more; every other op takes exactly 2


def _has_unit(q: Quantity) -> bool:
    return not q.const and q.unit is not None


def calculate(op: str, inputs: Sequence[Quantity]) -> CalcResult:
    if op not in OPS:
        raise CalcError(f"unknown op: {op}")
    if not inputs:
        raise CalcError("no inputs")
    if all(q.const for q in inputs):
        raise CalcError("every input is a fixed number; at least one must be a filing value")
    # a negative input in parentheses: "88,945 + (-8,796)", not "88,945 + -8,796"
    shown = [fmt_number(q.value) if q.value >= 0 else f"({fmt_number(q.value)})" for q in inputs]
    if op in MANY_INPUTS and len(inputs) < 2:
        raise CalcError(f"{op} needs 2 or more inputs")
    if op == "add":
        vals, unit = _amounts(inputs)
        return CalcResult(sum(vals), unit, " + ".join(shown))
    if op == "multiply":
        with_unit = [q for q in inputs if _has_unit(q)]
        if len(with_unit) > 1:
            raise CalcError("multiply takes at most one input with a unit")
        product = 1.0
        for q in inputs:
            product *= q.value
        unit = with_unit[0].unit if with_unit else None
        return CalcResult(product, unit, " x ".join(shown))
    if len(inputs) != 2:
        raise CalcError(f"{op} needs exactly 2 inputs")
    a, b = inputs
    if op == "divide" and (a.const or b.const):
        if b.value == 0:
            raise CalcError("division by zero")
        unit = a.unit if b.const else None  # amount / 3 keeps the amount's unit
        return CalcResult(a.value / b.value, unit, f"{shown[0]} / {shown[1]}")
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
