"""Extract Xero Small Business Insights (XSBI) workbooks into one tidy, long table.

Each country workbook (e.g. NZ_detailed_results_2026_09.xlsx) holds one sheet per
metric x segment type, laid out wide: a 'Month' column followed by one column per
industry or region. This module finds the header row in each sheet, reshapes the
sheet to long format and tags every value with its country, segment and metric.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

FILE_PATTERN = re.compile(r"^(?P<country>[A-Z]{2})_detailed_results_(?P<year>\d{4})_(?P<month>\d{2})\.xlsx$")
MONTH_PATTERN = re.compile(r"^\d{2}/\d{4}$")

COUNTRY_NAMES = {
    "NZ": "New Zealand",
    "AU": "Australia",
    "UK": "United Kingdom",
    "US": "United States",
    "CA": "Canada",
}

# metric_code -> (display name, unit, higher_is_better, sort order)
METRICS = {
    "sales": ("Sales growth", "% y/y", True, 1),
    "jobs": ("Jobs growth", "% y/y", True, 2),
    "wages": ("Wages growth", "% y/y", True, 3),
    "time_to_be_paid": ("Time to be paid", "days", False, 4),
    "late_payments": ("Late payments", "days", False, 5),
    "job_creators": ("Job creators", "% of firms", True, 6),
    "job_downsizers": ("Job downsizers", "% of firms", False, 7),
}

# Column headers on the 'National data' sheet -> metric_code
NATIONAL_COLUMNS = {
    "jobs": "jobs",
    "sales": "sales",
    "wages": "wages",
    "time to be paid": "time_to_be_paid",
    "late payments": "late_payments",
    "job creators": "job_creators",
    "job downsizers": "job_downsizers",
}

# Sheet name prefix -> metric_code ('creators_downsizers' sheets hold two metrics)
SHEET_METRICS = [
    ("jobs growth", "jobs"),
    ("sales growth", "sales"),
    ("wages growth", "wages"),
    ("time to be paid", "time_to_be_paid"),
    ("late payment", "late_payments"),
    ("job creators", "creators_downsizers"),
]

# Sheet name suffix -> segment type. States and provinces are treated as regions.
SHEET_SEGMENTS = {
    "industry": "Industry",
    "region": "Region",
    "state": "Region",
    "province": "Region",
}

SEGMENT_COLUMN = re.compile(r"^job (creators|downsizers):\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class Workbook:
    path: Path
    country_code: str
    release: str  # 'YYYY-MM' of the latest month in the release


def find_workbooks(folder: Path) -> list[Workbook]:
    """Find XSBI country workbooks in a folder, keeping the latest release per country."""
    latest: dict[str, Workbook] = {}
    for path in sorted(folder.glob("*.xlsx")):
        m = FILE_PATTERN.match(path.name)
        if not m:
            log.debug("Skipping %s (not an XSBI detailed results file)", path.name)
            continue
        wb = Workbook(path, m["country"], f"{m['year']}-{m['month']}")
        if wb.country_code not in COUNTRY_NAMES:
            log.warning("Unknown country code %s in %s, skipping", wb.country_code, path.name)
            continue
        current = latest.get(wb.country_code)
        if current and current.release >= wb.release:
            log.warning("Ignoring older release %s for %s", path.name, wb.country_code)
            continue
        if current:
            log.warning("Ignoring older release %s for %s", current.path.name, wb.country_code)
        latest[wb.country_code] = wb
    return [latest[c] for c in COUNTRY_NAMES if c in latest]


def tidy_name(raw: str) -> str:
    """Turn 'MANAWATU-WHANGANUI' into 'Manawatu-Whanganui'; leave mixed-case names alone.

    Text in brackets, such as '(NB, NS, PEI)', is kept as written.
    """
    name = " ".join(str(raw).split())
    if not name.isupper():
        return name

    def title_word(word: str) -> str:
        if word in {"OF", "AND", "THE"}:
            return word.lower()
        return "-".join(part[:1].upper() + part[1:].lower() for part in word.split("-"))

    pieces = re.split(r"(\(.*?\))", name)
    out = []
    for piece in pieces:
        if piece.startswith("("):
            out.append(piece)
        else:
            out.append(" ".join(title_word(w) if w != "&" else w for w in piece.split(" ")))
    result = "".join(out)
    return result[:1].upper() + result[1:]


def _classify_sheet(sheet_name: str) -> tuple[str, str] | None:
    """Return (metric_code, segment_type) for a sheet, or None if it isn't a data sheet."""
    name = sheet_name.strip().lower()
    if name == "national data":
        return ("national", "National")
    metric = next((code for prefix, code in SHEET_METRICS if name.startswith(prefix)), None)
    segment = next((seg for suffix, seg in SHEET_SEGMENTS.items() if name.endswith(f"by {suffix}")), None)
    if metric and segment:
        return (metric, segment)
    return None


def _read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    """Read a sheet, find its 'Month' header row and return the data rows with clean headers."""
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)
    header_rows = raw.index[raw.iloc[:, 0].astype(str).str.strip().eq("Month")]
    if len(header_rows) == 0:
        raise ValueError(f"{path.name} / {sheet_name}: no 'Month' header row found")
    header_idx = header_rows[0]
    headers = [str(h).strip() if pd.notna(h) else "" for h in raw.iloc[header_idx]]

    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = headers
    data = data[data["Month"].astype(str).str.strip().str.match(MONTH_PATTERN)]
    keep = ["Month"] + [h for h in headers[1:] if h]  # drop blank spacer columns
    return data[keep]


def _to_long(wide: pd.DataFrame) -> pd.DataFrame:
    long = wide.melt(id_vars="Month", var_name="column", value_name="value")
    long["month"] = pd.to_datetime(long["Month"].str.strip(), format="%m/%Y")
    return long.drop(columns="Month")


def extract_workbook(wb: Workbook) -> pd.DataFrame:
    """Extract every data sheet in one country workbook into a long table."""
    frames = []
    for sheet_name in pd.ExcelFile(wb.path).sheet_names:
        kind = _classify_sheet(sheet_name)
        if kind is None:
            if sheet_name.strip().lower() != "contents":
                log.warning("%s: unrecognised sheet '%s', skipping", wb.path.name, sheet_name)
            continue
        metric, segment_type = kind
        long = _to_long(_read_sheet(wb.path, sheet_name))

        if metric == "national":
            unknown = set(long["column"].str.lower()) - set(NATIONAL_COLUMNS)
            if unknown:
                raise ValueError(f"{wb.path.name} / {sheet_name}: unknown national columns {sorted(unknown)}")
            long["metric_code"] = long["column"].str.lower().map(NATIONAL_COLUMNS)
            long["segment_name"] = "National"
        elif metric == "creators_downsizers":
            parts = long["column"].str.extract(SEGMENT_COLUMN)
            if parts.isna().any().any():
                bad = sorted(long.loc[parts[0].isna(), "column"].unique())
                raise ValueError(f"{wb.path.name} / {sheet_name}: unexpected columns {bad}")
            long["metric_code"] = "job_" + parts[0].str.lower()
            long["segment_name"] = parts[1].map(tidy_name)
        else:
            long["metric_code"] = metric
            long["segment_name"] = long["column"].map(tidy_name)

        long["segment_type"] = segment_type
        long["sheet"] = sheet_name
        frames.append(long)

    out = pd.concat(frames, ignore_index=True)
    out["country_code"] = wb.country_code
    out["release"] = wb.release
    out["source_file"] = wb.path.name

    # Blank cells are dropped; anything else that isn't a number is kept as NaN for validation to report.
    out["raw_value"] = out["value"]
    out = out[out["raw_value"].notna() & out["raw_value"].astype(str).str.strip().ne("")]
    out["value"] = pd.to_numeric(out["raw_value"], errors="coerce")

    cols = ["country_code", "release", "source_file", "sheet", "segment_type", "segment_name",
            "metric_code", "month", "value", "raw_value"]
    return out[cols].reset_index(drop=True)


def extract_folder(folder: Path) -> pd.DataFrame:
    workbooks = find_workbooks(folder)
    if not workbooks:
        raise FileNotFoundError(f"No XSBI workbooks (e.g. NZ_detailed_results_2026_09.xlsx) found in {folder}")
    frames = []
    for wb in workbooks:
        df = extract_workbook(wb)
        log.info("Extracted %-38s %6d values, release %s", wb.path.name, len(df), wb.release)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)

