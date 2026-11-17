"""Write the model to CSV files and (optionally) load it into SQL Server.

SQL Server loads are a full refresh: each XSBI release restates history (Xero revises
past figures), so the tables are cleared and reloaded inside one transaction.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

# Load order (dimensions first); deletes run in reverse
TABLE_ORDER = ["DimCountry", "DimMetric", "DimDate", "DimSegment", "FactMetric"]


def write_csv(model: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in model.items():
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        log.info("Wrote %-16s %6d rows -> %s", name, len(df), path)


def _pick_driver(pyodbc) -> str:
    drivers = [d for d in pyodbc.drivers() if re.match(r"ODBC Driver \d+ for SQL Server", d)]
    if not drivers:
        raise RuntimeError(
            "No 'ODBC Driver NN for SQL Server' found. Install Microsoft ODBC Driver 18 for SQL Server, "
            f"or pass --driver. Installed drivers: {pyodbc.drivers()}"
        )
    return max(drivers, key=lambda d: int(re.search(r"\d+", d).group()))


def _connection_string(server: str, database: str, driver: str, user: str | None, password: str | None) -> str:
    auth = f"UID={user};PWD={password};" if user else "Trusted_Connection=yes;"
    # TrustServerCertificate: local SQL Server installs use a self-signed certificate
    return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};{auth}Encrypt=yes;TrustServerCertificate=yes;"


def _run_script(cursor, path: Path) -> None:
    """Run a .sql file, splitting on GO lines the way SSMS does."""
    batches = re.split(r"^\s*GO\s*$", path.read_text(encoding="utf-8"), flags=re.MULTILINE | re.IGNORECASE)
    for batch in batches:
        if batch.strip():
            cursor.execute(batch)


def _rows(df: pd.DataFrame) -> list[tuple]:
    clean = df.astype(object).where(pd.notna(df), None)
    return [tuple(r) for r in clean.itertuples(index=False, name=None)]


def load_sql_server(model: dict[str, pd.DataFrame], release: str, server: str, database: str,
                    driver: str | None = None, user: str | None = None, password: str | None = None) -> None:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc is not installed. Run: pip install -r requirements.txt") from exc

    driver = driver or _pick_driver(pyodbc)
    log.info("Connecting to %s / %s with %s", server, database, driver)

    # Create the database if it doesn't exist yet
    with pyodbc.connect(_connection_string(server, "master", driver, user, password), autocommit=True) as conn:
        conn.execute(f"IF DB_ID(N'{database}') IS NULL CREATE DATABASE [{database}];")

    conn = pyodbc.connect(_connection_string(server, database, driver, user, password), autocommit=False)
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        _run_script(cur, SQL_DIR / "01_create_schema.sql")
        _run_script(cur, SQL_DIR / "02_create_views.sql")

        for table in reversed(TABLE_ORDER):
            cur.execute(f"DELETE FROM xsbi.{table};")

        for table in TABLE_ORDER:
            df = model[table]
            cols = ", ".join(f"[{c}]" for c in df.columns)
            params = ", ".join("?" for _ in df.columns)
            cur.executemany(f"INSERT INTO xsbi.{table} ({cols}) VALUES ({params});", _rows(df))
            log.info("Loaded %-16s %6d rows", table, len(df))

        cur.execute(
            "INSERT INTO xsbi.LoadLog (LoadedAt, Release, FactRows) VALUES (?, ?, ?);",
            datetime.now(), release, len(model["FactMetric"]),
        )
        conn.commit()
        log.info("SQL Server load committed")
    except Exception:
        conn.rollback()
        log.error("SQL Server load failed; rolled back, existing data unchanged")
        raise
    finally:
        conn.close()

