"""Contract 1 (`spine_raw_jobs`): kolommen, types en validatie.

Het contract uit spec.md bevat geen `employee_count`. Die kolom is toegevoegd op
verzoek van de opdracht. Daardoor is `company_size_tier` af te leiden in plaats van
handmatig in te vullen.
"""

from __future__ import annotations

from collections.abc import Mapping

CONTRACT_COLUMNS: tuple[str, ...] = (
    "job_id",
    "company_name",
    "company_size_tier",
    "employee_count",
    "is_successful_growth_peer",
    "publication_date",
    "job_title",
    "description_text",
)

# Types zoals DuckDB ze rapporteert voor het geschreven Parquet-bestand.
CONTRACT_TYPES: dict[str, str] = {
    "job_id": "VARCHAR",
    "company_name": "VARCHAR",
    "company_size_tier": "VARCHAR",
    "employee_count": "BIGINT",
    "is_successful_growth_peer": "BOOLEAN",
    "publication_date": "DATE",
    "job_title": "VARCHAR",
    "description_text": "VARCHAR",
}

# Grenzen (bovengrens exclusief) per tier. "unknown" als het aantal onbekend is.
SIZE_TIER_BOUNDS: tuple[tuple[int, str], ...] = (
    (10, "micro"),
    (50, "small"),
    (250, "medium"),
    (1000, "large"),
)
UNKNOWN_TIER = "unknown"
ENTERPRISE_TIER = "enterprise"


def size_tier(employee_count: int | None) -> str:
    if employee_count is None:
        return UNKNOWN_TIER
    for upper, tier in SIZE_TIER_BOUNDS:
        if employee_count < upper:
            return tier
    return ENTERPRISE_TIER


def validate_contract_schema(schema: Mapping[str, str]) -> None:
    """Gooit ValueError als kolommen, volgorde of types niet overeenkomen met het contract."""
    columns = tuple(schema.keys())
    if columns != CONTRACT_COLUMNS:
        raise ValueError(f"Contract-kolommen wijken af.\n  verwacht: {CONTRACT_COLUMNS}\n  gevonden: {columns}")
    for column, expected in CONTRACT_TYPES.items():
        actual = schema[column].upper()
        if actual != expected:
            raise ValueError(f"Kolom {column!r} heeft type {actual}, verwacht {expected}")
