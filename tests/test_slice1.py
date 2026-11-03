"""Offline tests voor Slice 1 (geen netwerk nodig). Draaien met: python -m unittest discover tests"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from slice1.company_resolver import CompanyResolver  # noqa: E402
from slice1.contract import CONTRACT_COLUMNS, size_tier, validate_contract_schema  # noqa: E402
from slice1.models import CompanyProfile  # noqa: E402
from slice1.names import name_lookup_score, name_similarity, normalize_name  # noqa: E402
from slice1.peers import candidate_peers, has_positive_growth  # noqa: E402
from slice1.vacancy_export import export_contract  # noqa: E402


def profile(key: str, mcap: float | None, country: str = "Netherlands", sector: str = "Financial Services",
            symbol: str | None = None, employees: int | None = None) -> CompanyProfile:
    return CompanyProfile(key=key, name=key, symbol=symbol or key, sector=sector, country=country,
                          market_cap_usd=mcap, employee_count=employees)


class NormalizeNameTests(unittest.TestCase):
    def test_legal_suffixes_and_case_are_removed(self):
        self.assertEqual(normalize_name("ABN AMRO Bank N.V."), "abn amro bank")
        self.assertEqual(normalize_name("Lloyds Banking Group"), "lloyds banking")
        self.assertEqual(normalize_name("barclays"), normalize_name("Barclays"))

    def test_ampersand_and_accents(self):
        self.assertEqual(normalize_name("Legal & General"), "legal general")
        self.assertEqual(normalize_name("Coöperatie VGZ"), "cooperatie vgz")

    def test_similarity(self):
        self.assertGreaterEqual(name_similarity("Barclays", "Barclays PLC"), 0.85)
        self.assertLess(name_similarity("Barclays", "Lloyds Banking Group"), 0.85)

    def test_lookup_accepts_leading_name_match(self):
        # Getypte naam "KBC" moet "KBC Groep NV" (Yahoo) herkennen zonder alias.
        self.assertGreaterEqual(name_lookup_score("KBC", "KBC Groep NV"), 0.85)
        self.assertGreaterEqual(name_lookup_score("KBC", "KBC Group NV"), 0.85)
        self.assertGreaterEqual(name_lookup_score("ING", "ING Groep NV"), 0.85)

    def test_lookup_rejects_unrelated_and_too_long(self):
        self.assertLess(name_lookup_score("KBC", "Kbc Lighting Manufacturing Solutions Ltd"), 0.85)
        self.assertLess(name_lookup_score("Barclays", "Lloyds Banking Group"), 0.85)
        self.assertLess(name_lookup_score("KBC", "Akbc Capital"), 0.85)

    def test_exact_match_beats_prefix(self):
        self.assertEqual(name_lookup_score("Shell", "Shell plc"), 1.0)
        self.assertLess(name_lookup_score("Shell", "Shell Midstream Partners LP Units"), 0.85)


class PeerSelectionTests(unittest.TestCase):
    def setUp(self):
        self.target = profile("target", mcap=10e9)
        self.profiles = [
            self.target,
            profile("bigger_nl", mcap=20e9),
            profile("smaller_nl", mcap=5e9),
            profile("bigger_uk", mcap=50e9, country="United Kingdom"),
            profile("bigger_de", mcap=30e9, country="Germany"),
            profile("bigger_other_sector", mcap=40e9, sector="Technology"),
            profile("unlisted", mcap=None, symbol=None),
        ]

    def test_country_scope(self):
        keys = {p.key for p in candidate_peers(self.target, self.profiles, "country")}
        self.assertEqual(keys, {"bigger_nl"})

    def test_europe_scope(self):
        keys = {p.key for p in candidate_peers(self.target, self.profiles, "europe")}
        self.assertEqual(keys, {"bigger_nl", "bigger_uk", "bigger_de"})

    def test_any_region_keeps_sector_and_size_rule(self):
        keys = {p.key for p in candidate_peers(self.target, self.profiles, "any")}
        self.assertEqual(keys, {"bigger_nl", "bigger_uk", "bigger_de"})

    def test_target_without_market_cap_raises(self):
        with self.assertRaises(ValueError):
            candidate_peers(profile("t", mcap=None), self.profiles, "country")


class GrowthFilterTests(unittest.TestCase):
    def test_positive_three_and_five_year_returns(self):
        self.assertTrue(has_positive_growth({"ret_3y": 0.2, "ret_5y": 0.5}))

    def test_negative_five_year_rejects(self):
        self.assertFalse(has_positive_growth({"ret_3y": 0.2, "ret_5y": -0.1}))

    def test_missing_five_year_history_is_accepted(self):
        self.assertTrue(has_positive_growth({"ret_3y": 0.2, "ret_5y": None}))

    def test_missing_or_negative_three_year_rejects(self):
        self.assertFalse(has_positive_growth({"ret_3y": None, "ret_5y": 0.5}))
        self.assertFalse(has_positive_growth({"ret_3y": 0.0, "ret_5y": 0.5}))
        self.assertFalse(has_positive_growth(None))

    def test_min_return_threshold(self):
        self.assertFalse(has_positive_growth({"ret_3y": 0.05, "ret_5y": 0.5}, min_return=0.1))


class SizeTierTests(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(size_tier(None), "unknown")
        self.assertEqual(size_tier(5), "micro")
        self.assertEqual(size_tier(10), "small")
        self.assertEqual(size_tier(49), "small")
        self.assertEqual(size_tier(249), "medium")
        self.assertEqual(size_tier(250), "large")
        self.assertEqual(size_tier(999), "large")
        self.assertEqual(size_tier(1000), "enterprise")


class ResolverTests(unittest.TestCase):
    class FakeMarket:
        def __init__(self):
            self.searched = []

        def profile(self, symbol):
            return CompanyProfile(symbol, symbol, symbol, "Financial Services", "Netherlands", 1.0, None)

        def search_symbol(self, name):
            self.searched.append(name)
            return None

    def test_alias_takes_precedence_and_collapses_spellings(self):
        market = self.FakeMarket()
        resolver = CompanyResolver(market, aliases={"ING": "INGA.AS", "ING Netherlands": "INGA.AS"})
        self.assertEqual(resolver.resolve("ING Netherlands").key, "INGA.AS")
        self.assertEqual(resolver.resolve("ing").key, "INGA.AS")
        self.assertEqual(market.searched, [])

    def test_known_unlisted_is_not_searched(self):
        market = self.FakeMarket()
        resolver = CompanyResolver(market, aliases={"Rabobank": None})
        self.assertIsNone(resolver.resolve("Rabobank"))
        self.assertEqual(market.searched, [])

    def test_unknown_name_falls_back_to_search(self):
        market = self.FakeMarket()
        resolver = CompanyResolver(market, aliases={})
        self.assertIsNone(resolver.resolve("Onbekend Bedrijf"))
        self.assertEqual(market.searched, ["Onbekend Bedrijf"])


class ContractTests(unittest.TestCase):
    def test_validate_accepts_contract_schema(self):
        from slice1.contract import CONTRACT_TYPES
        validate_contract_schema({c: CONTRACT_TYPES[c] for c in CONTRACT_COLUMNS})

    def test_validate_rejects_extra_or_wrong_columns(self):
        from slice1.contract import CONTRACT_TYPES
        schema = {c: CONTRACT_TYPES[c] for c in CONTRACT_COLUMNS}
        schema["extra"] = "VARCHAR"
        with self.assertRaises(ValueError):
            validate_contract_schema(schema)
        schema = {c: CONTRACT_TYPES[c] for c in CONTRACT_COLUMNS}
        schema["employee_count"] = "VARCHAR"
        with self.assertRaises(ValueError):
            validate_contract_schema(schema)


class ExportTests(unittest.TestCase):
    def test_export_keeps_only_selected_companies_and_matches_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw = pa.table({
                "vacancy_id": ["1", "2", "3", "4"],
                "title": ["Compliance", "Risk", "Teller", "Other"],
                "description": ["d1", "d2", "d3", "d4"],
                "company": ["ING", "ING Netherlands", "Rabobank", "Peer B"],
                "date_posted": [date(2021, 1, 5), date(2022, 6, 1), date(2021, 3, 2), date(2023, 2, 2)],
                "country": ["NL"] * 4,
                "city": ["Amsterdam"] * 4,
            })
            src = tmp_path / "vacancies_test.parquet"
            pq.write_table(raw, src)

            company_map = pd.DataFrame({
                "raw_company": ["ING", "ING Netherlands", "Rabobank", "Peer B"],
                "company_key": ["INGA.AS", "INGA.AS", "name:rabobank", "name:peerb"],
            })
            companies = pd.DataFrame({
                "company_key": ["INGA.AS", "name:rabobank", "name:peerb"],
                "company_name": ["ING Groep N.V.", "Rabobank", "Peer B"],
                "employee_count": pd.array([60000, None, 300], dtype="Int64"),
                "company_size_tier": ["enterprise", "unknown", "large"],
                "is_successful_growth_peer": [True, False, False],
                "selected": [True, False, False],
            })
            out = tmp_path / "out" / "spine_raw_jobs.parquet"
            rows = export_contract([src], company_map, companies, out, tmp_path / "out" / "spine.jsonl")

            self.assertEqual(rows, 2)  # ING (2 rijen), Rabobank en Peer B niet geselecteerd
            result = pd.read_parquet(out)
            self.assertEqual(list(result.columns), list(CONTRACT_COLUMNS))
            self.assertEqual(sorted(result["job_id"].tolist()), ["1", "2"])
            self.assertTrue(result["is_successful_growth_peer"].all())
            self.assertEqual(result["employee_count"].tolist(), [60000, 60000])
            self.assertTrue((result["company_name"] == "ING Groep N.V.").all())
            self.assertTrue(Path(tmp_path / "out" / "spine.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
