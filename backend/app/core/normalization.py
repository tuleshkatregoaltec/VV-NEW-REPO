"""Shared name normalization for market-facing labels and search aliases."""

from __future__ import annotations

import re

AREA_ALIASES = {
    "jvc": "Jumeirah Village Circle",
    "jumeirah village circle": "Jumeirah Village Circle",
    "dubai marina": "Dubai Marina",
    "jlt": "Jumeirah Lakes Towers",
    "jumeirah lake towers": "Jumeirah Lakes Towers",
    "jumeirah lakes towers": "Jumeirah Lakes Towers",
    "jbr": "Jumeirah Beach Residence",
    "jumeirah beach residence": "Jumeirah Beach Residence",
    "downtown": "Downtown Dubai",
    "downtown dubai": "Downtown Dubai",
}

AREA_CONTAINS_ALIASES = (
    (("jvc", "jumeirah village circle"), "Jumeirah Village Circle"),
    (("jbr", "jumeirah beach residence"), "Jumeirah Beach Residence"),
    (("jlt", "jumeirah lake towers", "jumeirah lakes towers"), "Jumeirah Lakes Towers"),
)

DEVELOPER_BRAND_ALIASES = {
    "ALFURJAN ( L.L.C )": "Nakheel",
    "BUSINESS BAY (L.L.C)": "Dubai Properties",
    "DISTRICT ONE - FZ": "Meydan",
    "DUBAI AVIATION CITY CORPORATION": "Dubai South Developers",
    "DUBAI CREEK HARBOUR L.L.C": "Emaar",
    "DUBAI HILLS ESTATE L.L.C": "Emaar",
    "DUBAI LAND (L.L.C)": "Dubai Properties",
    "DUBAI LAND RESIDENCES (L.L.C)": "Dubai Properties",
    "DUBAI PROPERTIES(L.L.C)": "Dubai Properties",
    "DUBAI PROPERTIES (L.L.C)": "Dubai Properties",
    "EMAAR DEVELOPMENT (P.J.S.C)": "Emaar",
    "EMAAR DEVELOPMENT P.J.S.C.": "Emaar",
    "EMAAR PROPERTIES (P.J.S.C)": "Emaar",
    "INTERNATIONAL CITY ( L.L.C )": "Nakheel",
    "JUMAIRAH VILLAGE L.L.C": "Nakheel",
    "MERAAS ESTATES (L.L.C)": "Meraas",
    "NAKHEEL .(P J S C)": "Nakheel",
    "LIWAN (L.L.C)": "Dubai Properties",
    "REMRAAM L.L.C": "Dubai Properties",
    "SHAMAL ESTATES L.L.C": "Shamal",
    "DHAM FZ-LLC": "Dubai Holding",
    "DAMAC PROPERTIES CO. LLC": "DAMAC",
    "DAMAC WORLD REAL ESTATE L.L.C": "DAMAC",
    "BINGHATTI DEVELOPERS FZE": "Binghatti",
    "MEYDAN GROUP (L.L.C)": "Meydan",
    "MEYDAN CITY CORPORATION": "Meydan",
    "SOBHA L.L.C": "Sobha",
    "DUBAI HEALTHCARE CITY FZ - LLC": "Dubai Healthcare City",
    "JUMEIRAH HILLS DEVELOPMENT L.L.C": "Jumeirah Hills",
    "CITYWALK RESIDENTIAL 1 L.L.C": "Meraas",
    "DUBAI MARITIME CITY FZE": "Dubai Maritime City",
    "TECOM INVESTMENTS FZ-LLC": "TECOM",
    "DUBAI INVESTMENT REAL ESTATE (L L C)": "Dubai Investments",
    "MINA RASHID PROPERTIES L.L.C": "Mina Rashid",
    "AL KHAIL HEIGHTS L.L.C": "Al Khail Heights",
    "AL HABTOOR CITY REAL ESTATE DEVELOPMENT (BR. OF DUBAI NATIONAL INVESTMENT CO L.L.C)": "Al Habtoor",
    "ONE ZAABEEL L.L.C": "One Za'abeel",
    "MERAAS BAY AND RESIDENCE L.L.C": "Meraas",
    "THE LAGOONS PHASE ONE L.L.C": "Emaar",
    "THE PALM - DEIRA (L.L.C)": "Nakheel",
    "THE PALM - JEBEL ALI CO. (L.L.C)": "Nakheel",
    "THE PALM - JUMEIRAH CO. (L.L.C)": "Nakheel",
    "THE WORLD ( L.L.C )": "Nakheel",
}

DEVELOPER_LEGAL_ENTITY_PATTERN = re.compile(
    r"\b(l\.?\s*l\.?\s*c\.?|fz-?\s*llc|fze|fzco|p\.?\s*j\.?\s*s\.?\s*c\.?|p\.?\s*s\.?\s*c\.?|limited)\b",
    re.IGNORECASE,
)


def area_search_text(area: str) -> str:
    normalized = " ".join(area.lower().replace("(", " ").replace(")", " ").split())
    for tokens, canonical_name in AREA_CONTAINS_ALIASES:
        if any(token in normalized for token in tokens):
            return canonical_name
    return AREA_ALIASES.get(normalized, area.strip())


def listing_area_terms(area: str) -> list[str]:
    search_text = area_search_text(area)
    terms = [area.strip(), search_text]
    if search_text == "Jumeirah Village Circle":
        terms.append("JVC")
    elif search_text == "Jumeirah Beach Residence":
        terms.append("JBR")
    elif search_text == "Jumeirah Lakes Towers":
        terms.extend(["JLT", "Jumeirah Lake Towers"])

    unique_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        cleaned = " ".join(str(term).strip().split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            unique_terms.append(cleaned)
    return unique_terms


def developer_match_key(value: str | None) -> str:
    text_value = (value or "").lower().replace("&", " and ")
    legal_suffixes = (
        r"l\.?\s*l\.?\s*c\.?",
        r"p\.?\s*j\.?\s*s\.?\s*c\.?",
        r"fze",
        r"company",
        r"co",
        r"owned\s+by",
    )
    for suffix in legal_suffixes:
        text_value = re.sub(rf"\b{suffix}\b", " ", text_value)
    text_value = re.sub(r"[^a-z0-9]+", " ", text_value)
    return "".join(part for part in text_value.split() if len(part) > 1)


DEVELOPER_ALIAS_MATCH_KEYS = {
    developer_match_key(alias): brand for alias, brand in DEVELOPER_BRAND_ALIASES.items()
}


def developer_brand_name(developer_name: str) -> str:
    return DEVELOPER_ALIAS_MATCH_KEYS.get(developer_match_key(developer_name), developer_name)


def developer_filter_names(developer_name: str) -> list[str]:
    normalized = developer_name.strip()
    if not normalized:
        return []
    names = {normalized.lower()}
    for source_name, brand_name in DEVELOPER_BRAND_ALIASES.items():
        if brand_name.lower() == normalized.lower():
            names.add(source_name.lower())
    return sorted(names)


def is_rankable_developer_brand(developer_name: str) -> bool:
    return DEVELOPER_LEGAL_ENTITY_PATTERN.search(developer_name) is None
