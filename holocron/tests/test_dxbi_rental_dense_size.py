import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path


def test_adjacent_positive_size_values_split_before_unreachable_pagination():
    path = Path(__file__).parents[1] / "scripts/dxbi_rental_backfill.py"
    spec = importlib.util.spec_from_file_location("dense_rental_scraper", path)
    scraper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scraper)
    shard = {
        **scraper.initial_shards(date(2025, 11, 1))[0],
        "min_price": Decimal("43200.00"),
        "max_price": Decimal("43200.00"),
        "min_size": Decimal("328.29"),
        "max_size": Decimal("328.30"),
    }
    children = scraper.split_capped_shard(shard)
    assert [(c["min_size"], c["max_size"]) for c in children] == [
        (Decimal("328.29"), Decimal("328.29")),
        (Decimal("328.30"), Decimal("328.30")),
    ]
    assert all(scraper.split_capped_shard(c) == [] for c in children)
