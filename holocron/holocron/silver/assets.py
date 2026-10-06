from dagster import MaterializeResult, asset

from holocron.platform.resources import ClickHouseResource
from holocron.silver.transforms import (
    materialize_silver_rent_contracts,
    materialize_silver_transactions,
)

_SILVER_GROUP = "silver"


@asset(
    name="silver_transactions",
    group_name=_SILVER_GROUP,
    deps=["dld_od_transactions_bronze"],
    description="Cleaned, normalised transactions derived from dld_od_transactions_bronze.",
)
def silver_transactions_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    row_count = materialize_silver_transactions(clickhouse=clickhouse.client())
    context.log.info("silver_transactions materialised: %d rows", row_count)
    return MaterializeResult(
        metadata={
            "stage": "silver",
            "table": "silver_transactions",
            "row_count": row_count,
        }
    )


@asset(
    name="silver_rent_contracts",
    group_name=_SILVER_GROUP,
    deps=["dld_od_rents_bronze"],
    description="Cleaned, normalised rent contracts derived from dld_od_rents_bronze.",
)
def silver_rent_contracts_asset(
    context,
    clickhouse: ClickHouseResource,
) -> MaterializeResult:
    row_count = materialize_silver_rent_contracts(clickhouse=clickhouse.client())
    context.log.info("silver_rent_contracts materialised: %d rows", row_count)
    return MaterializeResult(
        metadata={
            "stage": "silver",
            "table": "silver_rent_contracts",
            "row_count": row_count,
        }
    )
