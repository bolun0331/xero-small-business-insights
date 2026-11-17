"""Data quality checks. Errors stop the pipeline; warnings are reported and the run continues."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .extract import METRICS

log = logging.getLogger(__name__)

# Hard limits (outside = error) and soft limits (outside = warning) by unit.
# Known source quirks, found by these checks on the Sep 2026 release:
#  - Growth below -100% appears (UK accommodation jobs, Apr-May 2020: about -115% and -134%),
#    so Xero's growth measure is not a simple ratio of levels. Kept, but flagged.
#  - Late payment days are seasonally adjusted and can dip slightly below zero. Kept, but flagged.
LIMITS = {
    "% y/y": {"hard": (-500, 1000), "soft": (-60, 80)},
    "days": {"hard": (-30, 365), "soft": (0, 90)},
    "% of firms": {"hard": (0, 100), "soft": (0, 100)},
}

EXPECTED_NATIONAL_METRICS = {
    "NZ": set(METRICS),
    "AU": set(METRICS),
    "UK": set(METRICS),
    "US": {"sales", "time_to_be_paid", "late_payments"},
    "CA": {"sales", "time_to_be_paid", "late_payments"},
}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors

    def log(self) -> None:
        for w in self.warnings:
            log.warning("CHECK  %s", w)
        for e in self.errors:
            log.error("CHECK  %s", e)
        log.info("Validation: %d error(s), %d warning(s)", len(self.errors), len(self.warnings))


def validate_extract(long: pd.DataFrame) -> Report:
    r = Report()

    # 1. Every value must be numeric
    bad = long[long["value"].isna()]
    if len(bad):
        sample = bad[["source_file", "sheet", "month", "raw_value"]].head(5).to_dict("records")
        r.error(f"{len(bad)} non-numeric value(s), e.g. {sample}")

    # 2. One value per country x segment x metric x month
    grain = ["country_code", "segment_type", "segment_name", "metric_code", "month"]
    dupes = long[long.duplicated(grain, keep=False)]
    if len(dupes):
        r.error(f"{len(dupes)} duplicate rows at the fact grain, e.g. {dupes[grain].head(3).to_dict('records')}")

    # 3. Values within plausible ranges for their unit
    units = long["metric_code"].map({k: v[1] for k, v in METRICS.items()})
    for unit, lim in LIMITS.items():
        vals = long.loc[units.eq(unit), ["source_file", "sheet", "segment_name", "month", "value"]]
        lo, hi = lim["hard"]
        hard = vals[(vals["value"] < lo) | (vals["value"] > hi)]
        if len(hard):
            r.error(f"{len(hard)} '{unit}' value(s) outside [{lo}, {hi}], e.g. {hard.head(3).to_dict('records')}")
        lo, hi = lim["soft"]
        soft = vals[((vals["value"] < lo) | (vals["value"] > hi)) & ~vals.index.isin(hard.index)]
        if len(soft):
            worst = soft.loc[soft["value"].abs().idxmax()]
            r.warn(f"{len(soft)} '{unit}' value(s) outside the usual range [{lo}, {hi}] "
                   f"(most extreme: {worst['value']} for {worst['segment_name']} in {worst['sheet']}, "
                   f"{worst['month']:%m/%Y}). Usually real volatility in small segments; check before quoting.")

    # 4. No gaps in monthly series
    series = long.groupby(["country_code", "segment_type", "segment_name", "metric_code"])["month"]
    gaps = []
    for key, months in series:
        expected = pd.date_range(months.min(), months.max(), freq="MS")
        missing = expected.difference(pd.DatetimeIndex(months))
        if len(missing):
            gaps.append(f"{'/'.join(key)}: {len(missing)} missing month(s)")
    if gaps:
        r.warn(f"{len(gaps)} series with gaps, e.g. {gaps[:3]}")

    # 5. Each workbook's last month matches the release in its file name
    for (country, release), grp in long.groupby(["country_code", "release"]):
        last = grp["month"].max().strftime("%Y-%m")
        if last != release:
            r.warn(f"{country}: file name says release {release} but the latest month is {last}")

    # 6. Expected national metrics are present
    national = long[long["segment_type"].eq("National")]
    for country, expected in EXPECTED_NATIONAL_METRICS.items():
        if country not in set(long["country_code"]):
            continue
        found = set(national.loc[national["country_code"].eq(country), "metric_code"])
        if found != expected:
            r.warn(f"{country}: national metrics differ from expected "
                   f"(missing {sorted(expected - found)}, extra {sorted(found - expected)})")

    return r


def validate_model(model: dict[str, pd.DataFrame], extract_rows: int) -> Report:
    r = Report()
    fact = model["FactMetric"]

    if len(fact) != extract_rows:
        r.error(f"Fact has {len(fact)} rows but the extract had {extract_rows}")

    for col, dim, key in [("CountryKey", "DimCountry", "CountryKey"), ("SegmentKey", "DimSegment", "SegmentKey"),
                          ("MetricKey", "DimMetric", "MetricKey"), ("DateKey", "DimDate", "DateKey")]:
        orphans = (~fact[col].isin(model[dim][key])) | fact[col].isna()
        if orphans.any():
            r.error(f"{int(orphans.sum())} fact rows have a {col} not found in {dim}")

    for name, df in model.items():
        if name.startswith("Dim"):
            key = df.columns[0]
            if df[key].duplicated().any():
                r.error(f"{name}.{key} is not unique")

    return r

