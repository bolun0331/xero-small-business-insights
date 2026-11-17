"""Run the XSBI pipeline: extract -> validate -> build star schema -> CSV (+ SQL Server).

Examples
--------
    python run_pipeline.py                                  # data/raw -> output/ + SQL Server (localhost, XSBI)
    python run_pipeline.py --no-sql                         # CSV only
    python run_pipeline.py --input "D:/Xero Project/XSBI - October 2026 release spreadsheet - AUNZUKCAUSSep26"
    python run_pipeline.py --server "localhost\\SQLEXPRESS" --database XSBI
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from src.extract import extract_folder
from src.load import load_sql_server, write_csv
from src.model import build_model
from src.validate import validate_extract, validate_model

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load Xero Small Business Insights data into a star schema.")
    p.add_argument("--input", type=Path, default=ROOT / "data" / "raw",
                   help="Folder with the XSBI *_detailed_results_YYYY_MM.xlsx files (default: data/raw)")
    p.add_argument("--output", type=Path, default=ROOT / "output", help="Folder for CSV output (default: output)")
    p.add_argument("--no-sql", action="store_true", help="Skip the SQL Server load")
    p.add_argument("--server", default="localhost", help="SQL Server instance (default: localhost)")
    p.add_argument("--database", default="XSBI", help="Database name, created if missing (default: XSBI)")
    p.add_argument("--driver", default=None, help="ODBC driver name (default: newest installed)")
    p.add_argument("--user", default=os.getenv("XSBI_SQL_USER"),
                   help="SQL login (default: Windows authentication). Password from XSBI_SQL_PASSWORD.")
    p.add_argument("--fail-on-warnings", action="store_true", help="Treat validation warnings as errors")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("xsbi")

    long = extract_folder(args.input)
    report = validate_extract(long)
    report.log()
    if not report.ok or (args.fail_on_warnings and report.warnings):
        log.error("Stopping: fix the issues above and rerun")
        return 1

    model = build_model(long)
    model_report = validate_model(model, extract_rows=len(long))
    model_report.log()
    if not model_report.ok:
        return 1

    write_csv(model, args.output)

    if not args.no_sql:
        release = long["release"].max()
        load_sql_server(model, release, args.server, args.database, args.driver,
                        args.user, os.getenv("XSBI_SQL_PASSWORD"))

    log.info("Done: %d values, %d segments, %d countries",
             len(model["FactMetric"]), len(model["DimSegment"]), len(model["DimCountry"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

