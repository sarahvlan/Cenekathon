"""Normalisatie en vergelijking van bedrijfsnamen."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Juridische en generieke woorden die geen onderscheidend karakter hebben.
LEGAL_TOKENS = frozenset(
    {
        "plc", "ltd", "limited", "nv", "bv", "sa", "inc", "corp", "corporation",
        "co", "company", "holdings", "holding", "group", "the", "and", "de",
        "llc", "ag", "se", "n", "v", "b",
    }
)


def normalize_name(raw: str | None) -> str:
    """Zet een bedrijfsnaam om naar een vergelijkbare vorm.

    Voorbeelden: "ABN AMRO Bank N.V." -> "abn amro bank",
    "Lloyds Banking Group" -> "lloyds banking", "Legal & General" -> "legal general".
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKD", str(raw))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ")
    tokens = re.findall(r"[a-z0-9]+", text)
    return " ".join(token for token in tokens if token not in LEGAL_TOKENS)


def name_similarity(a: str | None, b: str | None) -> float:
    """Similarity tussen 0 en 1 op basis van genormaliseerde namen."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()
