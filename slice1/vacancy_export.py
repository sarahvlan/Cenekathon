"""Lees de ruwe vacatures met DuckDB, koppel ze aan bedrijven en schrijf Contract 1."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd

from .contract import CONTRACT_COLUMNS, validate_contract_schema

# Kolommen die in de ruwe Parquet-bestanden moeten staan.
RAW_COLUMNS: tuple[str, ...] = ("vacancy_id", "title", "description", "company", "date_posted", "country", "city")


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _read_parquet_sql(files: Sequence[Path]) -> str:
    paths = ", ".join(_sql_str(str(f)) for f in files)
    return f"read_parquet([{paths}], union_by_name = true)"


def raw_company_counts(files: Sequence[Path]) -> pd.DataFrame:
    """Aantal vacatures per ruwe bedrijfsnaam, over alle invoerbestanden."""
    con = duckdb.connect()
    try:
        return con.sql(
            f"SELECT company, COUNT(*) AS n_vacancies FROM {_read_parquet_sql(files)} "
            "WHERE company IS NOT NULL GROUP BY company ORDER BY n_vacancies DESC"
        ).df()
    finally:
        con.close()


def export_contract(
    files: Sequence[Path],
    company_map: pd.DataFrame,
    companies: pd.DataFrame,
    output_path: Path,
    jsonl_path: Path | None = None,
) -> int:
    """Schrijf de vacatures van geselecteerde bedrijven als Contract 1 en geef het aantal rijen terug.

    Parameters
    ----------
    company_map:
        Kolommen `raw_company` (ruwe naam uit de data) en `company_key`.
    companies:
        Kolommen `company_key`, `company_name`, `employee_count` (nullable Int64),
        `company_size_tier`, `is_successful_growth_peer` (bool) en `selected` (bool).
        Alleen rijen met `selected == True` komen in de output.
    """
    for col in ("raw_company", "company_key"):
        if col not in company_map.columns:
            raise ValueError(f"company_map mist kolom {col!r}")
    needed = {"company_key", "company_name", "employee_count", "company_size_tier",
              "is_successful_growth_peer", "selected"}
    missing = needed - set(companies.columns)
    if missing:
        raise ValueError(f"companies mist kolommen: {sorted(missing)}")

    con = duckdb.connect()
    try:
        con.execute(f"CREATE VIEW raw_jobs AS SELECT * FROM {_read_parquet_sql(files)}")
        con.register("company_map_df", company_map)
        con.register("companies_df", companies)
        con.execute("CREATE TABLE company_map AS SELECT * FROM company_map_df")
        con.execute("CREATE TABLE companies AS SELECT * FROM companies_df")

        query = f"""
            SELECT
                CAST(j.vacancy_id AS VARCHAR)     AS job_id,
                c.company_name                    AS company_name,
                c.company_size_tier               AS company_size_tier,
                CAST(c.employee_count AS BIGINT)  AS employee_count,
                CAST(c.is_successful_growth_peer AS BOOLEAN) AS is_successful_growth_peer,
                CAST(j.date_posted AS DATE)       AS publication_date,
                j.title                           AS job_title,
                j.description                     AS description_text
            FROM raw_jobs j
            JOIN company_map m ON j.company = m.raw_company
            JOIN companies c   ON c.company_key = m.company_key
            WHERE c.selected
            ORDER BY publication_date, job_id
        """

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        con.execute(f"COPY ({query}) TO {_sql_str(str(output_path))} (FORMAT PARQUET)")

        described = con.execute(f"DESCRIBE SELECT * FROM read_parquet({_sql_str(str(output_path))})").fetchall()
        validate_contract_schema({row[0]: row[1] for row in described})
        if tuple(row[0] for row in described) != CONTRACT_COLUMNS:
            raise AssertionError("Onverwachte kolomvolgorde in het contract")

        row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet({_sql_str(str(output_path))})").fetchone()[0]

        if jsonl_path is not None:
            if jsonl_path.exists():
                jsonl_path.unlink()
            con.execute(f"COPY ({query}) TO {_sql_str(str(jsonl_path))} (FORMAT JSON)")
        return int(row_count)
    finally:
        con.close()
