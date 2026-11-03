"""Orkestratie van Slice 1: doelbedrijf -> peers -> groeifilter -> vacature-export."""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from datetime import date

import duckdb
import pandas as pd

from .cache import JsonCache
from .company_resolver import CompanyResolver
from .config import PipelineConfig
from .contract import size_tier
from .market_data import MarketDataClient
from .models import CompanyProfile
from .names import normalize_name
from .peers import candidate_peers, has_positive_growth
from .vacancy_export import export_contract, raw_company_counts

log = logging.getLogger(__name__)

GROWTH_WINDOWS_YEARS = (3, 5)
PROGRESS_EVERY = 100


class TargetNotFoundError(RuntimeError):
    """Het doelbedrijf is niet te vinden op de beurs en er zijn onvoldoende overrides opgegeven."""


@dataclass
class PipelineResult:
    target: CompanyProfile
    as_of: date
    successful_peers: list[CompanyProfile]
    rejected_candidates: list[CompanyProfile]
    contract_rows: int
    unresolved_companies: list[tuple[str, int]] = field(default_factory=list)


def resolve_target(config: PipelineConfig, resolver: CompanyResolver, market: MarketDataClient) -> CompanyProfile:
    """Bepaal het doelbedrijf. Overrides uit de config winnen van Yahoo-gegevens."""
    if config.target_symbol:
        profile = market.profile(config.target_symbol)
    else:
        profile = resolver.resolve(config.target_name)

    overrides = {
        "sector": config.target_sector,
        "country": config.target_country,
        "market_cap_usd": config.target_market_cap_usd,
    }
    if profile is None:
        if any(value is None for value in overrides.values()):
            raise TargetNotFoundError(
                f"Doelbedrijf {config.target_name!r} is niet gevonden op de beurs. "
                "Geef sector, land en marktkapitalisatie op met --target-sector, --target-country "
                "en --target-market-cap-usd, of gebruik --target-symbol."
            )
        profile = CompanyProfile(
            key=f"name:{normalize_name(config.target_name)}",
            name=config.target_name,
            symbol=None,
            sector=None,
            country=None,
            market_cap_usd=None,
            employee_count=None,
        )

    applied = {k: v for k, v in overrides.items() if v is not None}
    profile = dataclasses.replace(profile, **applied)
    if profile.market_cap_usd is None or profile.sector is None or profile.country is None:
        raise TargetNotFoundError(
            f"Onvoldoende gegevens voor doelbedrijf {config.target_name!r} "
            f"(sector={profile.sector}, land={profile.country}, marktkapitalisatie={profile.market_cap_usd}). "
            "Vul de ontbrekende waarden aan via de --target-* opties."
        )
    return profile


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    cache = JsonCache(config.cache_dir / "market_cache.json")
    market = MarketDataClient(cache)
    resolver = CompanyResolver(market)

    try:
        target = resolve_target(config, resolver, market)
        log.info("Doelbedrijf: %s | sector=%s | land=%s | mcap=%.1f mld USD",
                 target.name, target.sector, target.country, (target.market_cap_usd or 0) / 1e9)

        counts = raw_company_counts(config.input_files)
        as_of = config.as_of or _latest_posting_date(config)
        target_norm = normalize_name(config.target_name)

        # Selecteer welke ruwe namen we opzoeken: voldoende vacatures, of de doelbedrijfsnaam zelf.
        is_target_name = counts["company"].map(normalize_name) == target_norm
        to_resolve = counts[(counts["n_vacancies"] >= config.min_company_vacancies) | is_target_name]
        if config.max_companies is not None:
            to_resolve = to_resolve.head(config.max_companies)
        log.info("%d van %d ruwe bedrijfsnamen worden opgezocht", len(to_resolve), len(counts))

        profiles: dict[str, CompanyProfile] = {target.key: target}
        raw_to_key: dict[str, str] = {}
        unresolved: list[tuple[str, int]] = []
        for i, row in enumerate(to_resolve.itertuples(index=False), start=1):
            raw, n = row.company, int(row.n_vacancies)
            if normalize_name(raw) == target_norm:
                raw_to_key[raw] = target.key
                continue
            profile = resolver.resolve(raw)
            if profile is None:
                unresolved.append((raw, n))
                continue
            profiles.setdefault(profile.key, profile)
            raw_to_key[raw] = profile.key
            if i % PROGRESS_EVERY == 0:
                log.info("  %d/%d bedrijven opgezocht", i, len(to_resolve))
                cache.flush()

        candidates = candidate_peers(target, profiles.values(), config.region_scope)
        log.info("%d kandidaat-peers (zelfde sector/regio, grotere marktkapitalisatie)", len(candidates))

        successful: list[CompanyProfile] = []
        rejected: list[CompanyProfile] = []
        returns_by_key: dict[str, dict] = {}
        for peer in candidates:
            returns = market.price_returns(peer.symbol, as_of, GROWTH_WINDOWS_YEARS)
            returns_by_key[peer.key] = returns or {}
            (successful if has_positive_growth(returns, config.min_return) else rejected).append(peer)
        cache.flush()
        log.info("%d peers met een succesvol groeipad", len(successful))

        successful_keys = {p.key for p in successful}
        companies = _companies_frame(profiles, target.key, successful_keys, returns_by_key)
        company_map = _company_map_frame(raw_to_key)

        rows = export_contract(
            config.input_files,
            company_map,
            companies,
            config.contract_path,
            config.contract_jsonl_path if config.write_jsonl else None,
        )
        companies.to_parquet(config.company_profiles_path, index=False)

        result = PipelineResult(
            target=target,
            as_of=as_of,
            successful_peers=successful,
            rejected_candidates=rejected,
            contract_rows=rows,
            unresolved_companies=unresolved,
        )
        _write_report(config, result)
        return result
    finally:
        cache.flush()


def _latest_posting_date(config: PipelineConfig) -> date:
    con = duckdb.connect()
    try:
        files = ", ".join("'" + str(f).replace("'", "''") + "'" for f in config.input_files)
        value = con.execute(f"SELECT MAX(date_posted) FROM read_parquet([{files}], union_by_name = true)").fetchone()[0]
    finally:
        con.close()
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _companies_frame(
    profiles: dict[str, CompanyProfile],
    target_key: str,
    successful_keys: set[str],
    returns_by_key: dict[str, dict],
) -> pd.DataFrame:
    rows = []
    for key, profile in profiles.items():
        returns = returns_by_key.get(key, {})
        is_peer = key in successful_keys
        rows.append(
            {
                "company_key": key,
                "company_name": profile.name,
                "symbol": profile.symbol,
                "sector": profile.sector,
                "country": profile.country,
                "market_cap_usd": profile.market_cap_usd,
                "employee_count": profile.employee_count,
                "company_size_tier": size_tier(profile.employee_count),
                "ret_3y": returns.get("ret_3y"),
                "ret_5y": returns.get("ret_5y"),
                "is_target_company": key == target_key,
                "is_successful_growth_peer": is_peer,
                "selected": is_peer or key == target_key,
            }
        )
    frame = pd.DataFrame(rows)
    frame["employee_count"] = pd.array(frame["employee_count"].tolist(), dtype="Int64")
    return frame


def _company_map_frame(raw_to_key: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"raw_company": list(raw_to_key.keys()), "company_key": list(raw_to_key.values())}
    )


def _write_report(config: PipelineConfig, result: PipelineResult) -> None:
    report = {
        "target": result.target.name,
        "target_key": result.target.key,
        "as_of": result.as_of.isoformat(),
        "region_scope": config.region_scope,
        "min_return": config.min_return,
        "min_company_vacancies": config.min_company_vacancies,
        "successful_peers": [p.name for p in result.successful_peers],
        "candidates_rejected_by_growth": [p.name for p in result.rejected_candidates],
        "contract_rows": result.contract_rows,
        "unresolved_companies_top50": [
            {"company": name, "vacancies": n} for name, n in result.unresolved_companies[:50]
        ],
        "unresolved_company_count": len(result.unresolved_companies),
    }
    config.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
