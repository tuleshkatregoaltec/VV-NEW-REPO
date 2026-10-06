"""Dubai-only scope shared by product queries that consume Reelly projects."""

from __future__ import annotations

import re

REELLY_DUBAI_LATITUDE_RANGE = (24.55, 25.55)
REELLY_DUBAI_LONGITUDE_RANGE = (54.75, 56.25)
REELLY_NON_DUBAI_AREA_MARKERS = (
    "abu dhabi",
    "ras al khaimah",
    "umm al quwain",
    "sharjah",
    "ajman",
    "fujairah",
    "bali",
    "phuket",
    "thailand",
    "oman",
    "yas island",
    "saadiyat island",
)

_SQL_ALIAS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def reelly_dubai_project_scope(alias: str | None = None) -> str:
    """Return a fail-closed ClickHouse predicate for Dubai catalogue projects."""
    if alias and not _SQL_ALIAS.fullmatch(alias):
        raise ValueError(f"Invalid SQL alias: {alias!r}")
    prefix = f"{alias}." if alias else ""
    region = f"{prefix}region"
    area = f"{prefix}area_name"
    latitude = f"{prefix}latitude"
    longitude = f"{prefix}longitude"
    area_checks = "\n            AND ".join(
        f"positionCaseInsensitiveUTF8({area}, '{marker}') = 0"
        for marker in REELLY_NON_DUBAI_AREA_MARKERS
    )
    return f"""
        lowerUTF8(trim({region})) = 'dubai'
        AND {area_checks}
        AND (
            {latitude} IS NULL
            OR {longitude} IS NULL
            OR (
                {latitude} BETWEEN {REELLY_DUBAI_LATITUDE_RANGE[0]}
                    AND {REELLY_DUBAI_LATITUDE_RANGE[1]}
                AND {longitude} BETWEEN {REELLY_DUBAI_LONGITUDE_RANGE[0]}
                    AND {REELLY_DUBAI_LONGITUDE_RANGE[1]}
            )
        )
    """.strip()
