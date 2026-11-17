"""Build the star schema (dimension and fact tables) from the long extract."""

from __future__ import annotations

import pandas as pd

from .extract import COUNTRY_NAMES, METRICS

SEGMENT_TYPE_ORDER = {"National": 0, "Industry": 1, "Region": 2}
COUNTRY_ORDER = {code: i for i, code in enumerate(COUNTRY_NAMES, start=1)}


def build_dim_country(long: pd.DataFrame) -> pd.DataFrame:
    codes = sorted(long["country_code"].unique(), key=COUNTRY_ORDER.get)
    return pd.DataFrame({
        "CountryKey": [COUNTRY_ORDER[c] for c in codes],
        "CountryCode": codes,
        "CountryName": [COUNTRY_NAMES[c] for c in codes],
    })


def build_dim_metric() -> pd.DataFrame:
    rows = [
        {"MetricKey": order, "MetricCode": code, "MetricName": name, "Unit": unit,
         "HigherIsBetter": int(higher), "SortOrder": order}
        for code, (name, unit, higher, order) in METRICS.items()
    ]
    return pd.DataFrame(rows).sort_values("MetricKey").reset_index(drop=True)


def build_dim_segment(long: pd.DataFrame, dim_country: pd.DataFrame) -> pd.DataFrame:
    seg = long[["country_code", "segment_type", "segment_name"]].drop_duplicates()
    seg = seg.assign(
        _c=seg["country_code"].map(COUNTRY_ORDER),
        _t=seg["segment_type"].map(SEGMENT_TYPE_ORDER),
    ).sort_values(["_c", "_t", "segment_name"]).reset_index(drop=True)
    seg["SegmentKey"] = seg.index + 1
    seg["SortOrder"] = seg.groupby(["country_code", "segment_type"]).cumcount() + 1
    seg = seg.merge(dim_country[["CountryKey", "CountryCode"]], left_on="country_code", right_on="CountryCode")
    return seg.rename(columns={"segment_type": "SegmentType", "segment_name": "SegmentName"})[
        ["SegmentKey", "CountryKey", "CountryCode", "SegmentType", "SegmentName", "SortOrder"]
    ]


def build_dim_date(long: pd.DataFrame) -> pd.DataFrame:
    months = pd.date_range(long["month"].min(), long["month"].max(), freq="MS")
    return pd.DataFrame({
        "DateKey": months.strftime("%Y%m%d").astype(int),
        "Date": months.date,
        "Year": months.year,
        "Quarter": months.quarter,
        "QuarterLabel": "Q" + months.quarter.astype(str) + " " + months.year.astype(str),
        "MonthNumber": months.month,
        "MonthName": months.strftime("%b"),
        "YearMonth": months.strftime("%b %Y"),
        "YearMonthSort": months.year * 100 + months.month,
    })


def build_fact(long: pd.DataFrame, dim_segment: pd.DataFrame, dim_metric: pd.DataFrame) -> pd.DataFrame:
    fact = long.merge(
        dim_segment[["SegmentKey", "CountryKey", "CountryCode", "SegmentType", "SegmentName"]],
        left_on=["country_code", "segment_type", "segment_name"],
        right_on=["CountryCode", "SegmentType", "SegmentName"],
        how="left",
    ).merge(dim_metric[["MetricKey", "MetricCode"]], left_on="metric_code", right_on="MetricCode", how="left")
    fact["DateKey"] = fact["month"].dt.strftime("%Y%m%d").astype(int)
    fact = fact.rename(columns={"value": "Value"})
    cols = ["DateKey", "CountryKey", "SegmentKey", "MetricKey", "Value"]
    return fact[cols].sort_values(["CountryKey", "SegmentKey", "MetricKey", "DateKey"]).reset_index(drop=True)


def build_model(long: pd.DataFrame) -> dict[str, pd.DataFrame]:
    dim_country = build_dim_country(long)
    dim_metric = build_dim_metric()
    dim_segment = build_dim_segment(long, dim_country)
    return {
        "DimCountry": dim_country,
        "DimSegment": dim_segment,
        "DimMetric": dim_metric,
        "DimDate": build_dim_date(long),
        "FactMetric": build_fact(long, dim_segment, dim_metric),
    }

