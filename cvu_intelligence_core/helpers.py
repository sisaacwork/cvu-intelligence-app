"""Generic helpers used across the pipeline."""

from .constants import STATUS_MAP


def get_function(record):
    """Join main_use_01..05 (tuple indices 8..12) with ' / ', title-cased.

    Returns 'Unknown' if no use codes are present.
    """
    uses = [record[i] for i in range(8, 13) if record[i] and record[i].strip()]
    if not uses:
        return "Unknown"
    return " / ".join(" ".join(w.capitalize() for w in u.split()) for u in uses)


def get_status(code):
    return STATUS_MAP.get(code, code)


def fmt(val, kind="str"):
    """Format a value for display, returning '—' for None / 0 / empty."""
    if val is None or val == "" or val == 0:
        return "—"
    if kind == "float":
        return f"{val:,.2f}"
    if kind == "int":
        return f"{val:,}"
    return str(val)
