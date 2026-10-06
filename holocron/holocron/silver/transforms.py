from __future__ import annotations

from holocron.platform.clickhouse import ClickHouseClient
from holocron.platform.clickhouse_schema import ensure_schema

_SILVER_TRANSACTIONS_SQL = """
INSERT INTO `silver_transactions_staging`
WITH
    open_data_cutoff AS (
        SELECT minOrNull(toDate(instance_date)) AS cutoff_date
        FROM dld_od_transactions_bronze
        WHERE source_system = 'dld_open_data'
    )
SELECT
    row_key,
    if(transaction_number != '', transaction_number, row_key) AS transaction_number,
    toDate(instance_date)                                      AS transaction_date,
    group_en                                                   AS trans_group,
    group_ar                                                   AS trans_group_ar,
    procedure_en                                               AS procedure_name,
    procedure_ar                                               AS procedure_name_ar,
    procedure_area,
    prop_type_en                                               AS property_type,
    prop_type_ar                                               AS property_type_ar,
    prop_sb_type_en                                            AS property_sub_type,
    prop_sb_type_ar                                            AS property_sub_type_ar,
    usage_en                                                   AS property_usage,
    usage_ar                                                   AS property_usage_ar,
    reg_type_en                                                AS reg_type,
    reg_type_ar                                                AS reg_type_ar,
    rooms_en,
    rooms_ar,
    parking,
    building_age,
    parcel_id,
    area_id,
    initcap(trim(area_en))                                     AS area_name_en,
    area_ar                                                    AS area_name_ar,
    initcap(trim(project_en))                                  AS project_name_en,
    project_ar                                                 AS project_name_ar,
    initcap(trim(master_project_en))                           AS master_project_en,
    master_project_ar,
    initcap(trim(building_name_en))                            AS building_name_en,
    building_name_ar,
    project_number,
    property_id,
    actual_area                                                AS actual_area_sqm,
    trans_value                                                AS sale_price_aed,
    price_per_sqm_aed,
    is_free_hold,
    is_offplan                                                 AS is_off_plan,
    total_buyer                                                AS total_buyers,
    total_seller                                               AS total_sellers,
    nearest_metro_en,
    nearest_metro_ar,
    nearest_mall_en,
    nearest_mall_ar,
    nearest_landmark_en,
    nearest_landmark_ar,
    no_of_parties_role_1,
    no_of_parties_role_2,
    no_of_parties_role_3,
    property_category,
    market_scope,
    toUInt8(market_scope = 'residential_home')                 AS is_residential_home,
    is_price_per_sqm_valid,
    toUInt8(
        market_scope = 'residential_home'
        AND is_offplan = 0
        AND is_price_per_sqm_valid = 1
    )                                                          AS is_yield_eligible
FROM
(
    SELECT
        categorized.*,
        multiIf(
            usage_lc = 'residential' AND property_category IN ('apartment', 'villa'),
            'residential_home',
            usage_lc = 'residential' AND property_category = 'land',
            'residential_land',
            usage_lc = 'residential' AND property_category = 'hotel_unit',
            'residential_hospitality',
            usage_lc = 'residential',
            'residential_other',
            usage_lc LIKE '%commercial%' OR property_category = 'commercial',
            'commercial',
            usage_lc = '',
            'unknown',
            'other'
        ) AS market_scope
    FROM
    (
        SELECT
            source.*,
            multiIf(
                usage_lc = 'residential'
                    AND type_lc IN ('unit', 'flat', 'apartment')
                    AND subtype_lc IN ('flat', 'apartment', 'studio'),
                'apartment',
                usage_lc = 'residential'
                    AND (
                        type_lc = 'villa'
                        OR subtype_lc IN ('villa', 'stacked townhouses', 'townhouse', 'town house')
                        OR (type_lc = 'building' AND subtype_lc = 'villa')
                    ),
                'villa',
                usage_lc = 'residential'
                    AND subtype_lc IN ('hotel apartment', 'hotel rooms'),
                'hotel_unit',
                type_lc = 'land'
                    OR subtype_lc IN (
                        'land',
                        'residential',
                        'residential / villas',
                        'residential / attached villas',
                        'residential flats',
                        'residential / residential villa',
                        'government housing'
                    ),
                'land',
                usage_lc LIKE '%commercial%'
                    OR subtype_lc IN ('office', 'shop', 'show rooms', 'warehouse', 'workshop'),
                'commercial',
                'other'
            ) AS property_category
        FROM
        (
            SELECT
                b.*,
                lower(trim(b.usage_en)) AS usage_lc,
                lower(trim(b.prop_type_en)) AS type_lc,
                lower(trim(b.prop_sb_type_en)) AS subtype_lc,
                if(
                    b.meter_sale_price > 0,
                    b.meter_sale_price,
                    b.trans_value / nullIf(b.procedure_area, 0)
                ) AS price_per_sqm_aed,
                toUInt8(
                    ifNull(
                        price_per_sqm_aed > 100
                        AND price_per_sqm_aed < 250000
                        AND b.procedure_area > 0,
                        0
                    )
                ) AS is_price_per_sqm_valid
            FROM dld_od_transactions_bronze AS b
            CROSS JOIN open_data_cutoff
            WHERE b.trans_value > 0
              AND (
                  b.source_system != 'dubai_pulse'
                  OR isNull(cutoff_date)
                  OR toDate(b.instance_date) < cutoff_date
              )
        ) AS source
    ) AS categorized
) AS classified
"""

_SILVER_RENT_CONTRACTS_SQL = """
INSERT INTO `silver_rent_contracts_staging`
WITH
    open_data_cutoff AS (
        SELECT minOrNull(toDate(registration_date)) AS cutoff_date
        FROM dld_od_rents_bronze
        WHERE source_system = 'dld_open_data'
    )
SELECT
    row_key,
    if(contract_number != '', contract_number, row_key) AS contract_id,
    contract_number,
    line_number,
    toDate(registration_date)                           AS registration_date,
    toDate(start_date)                                  AS contract_start_date,
    toDate(end_date)                                    AS contract_end_date,
    prop_type_en                                        AS property_type,
    prop_type_ar                                        AS property_type_ar,
    prop_sub_type_en                                    AS property_sub_type,
    prop_sub_type_ar                                    AS property_sub_type_ar,
    usage_en                                            AS property_usage,
    usage_ar                                            AS property_usage_ar,
    rooms,
    parking,
    actual_area                                         AS actual_area_sqm,
    annual_amount                                       AS annual_amount_aed,
    contract_amount                                     AS contract_amount_aed,
    rent_per_sqm_aed,
    total_properties,
    version_number,
    version_en                                          AS contract_version,
    version_ar                                          AS contract_version_ar,
    parcel_id,
    area_id,
    initcap(trim(area_en))                              AS area_name_en,
    area_ar                                             AS area_name_ar,
    initcap(trim(project_en))                           AS project_name_en,
    project_ar                                          AS project_name_ar,
    initcap(trim(master_project_en))                    AS master_project_en,
    master_project_ar,
    project_number,
    property_id,
    land_property_id,
    is_free_hold,
    tenant_type_en                                      AS tenant_type,
    tenant_type_ar,
    contract_reg_type_en                                AS contract_reg_type,
    contract_reg_type_ar,
    ejari_property_type_id,
    ejari_property_sub_type_id,
    ejari_bus_property_type_en                          AS ejari_business_property_type,
    ejari_bus_property_type_ar                          AS ejari_business_property_type_ar,
    nearest_metro_en,
    nearest_metro_ar,
    nearest_mall_en,
    nearest_mall_ar,
    nearest_landmark_en,
    nearest_landmark_ar,
    annual_amount / greatest(total_properties, 1)       AS annual_amount_per_property_aed,
    property_category,
    market_scope,
    toUInt8(market_scope = 'residential_home')          AS is_residential_home,
    toUInt8(total_properties = 1)                       AS is_single_property_contract,
    is_rent_per_sqm_valid,
    toUInt8(
        market_scope = 'residential_home'
        AND total_properties = 1
        AND lower(trim(version_en)) = 'new'
        AND is_rent_per_sqm_valid = 1
    )                                                   AS is_yield_eligible
FROM
(
    SELECT
        categorized.*,
        multiIf(
            usage_lc = 'residential' AND property_category IN ('apartment', 'villa'),
            'residential_home',
            usage_lc = 'residential' AND property_category = 'land',
            'residential_land',
            usage_lc = 'residential',
            'residential_other',
            usage_lc LIKE '%commercial%' OR property_category = 'commercial',
            'commercial',
            usage_lc = '',
            'unknown',
            'other'
        ) AS market_scope
    FROM
    (
        SELECT
            source.*,
            multiIf(
                usage_lc = 'residential'
                    AND (
                        type_lc IN ('flat', 'studio')
                        OR (type_lc = 'unit' AND subtype_lc IN ('flat', 'studio'))
                    )
                    AND subtype_lc != 'room',
                'apartment',
                usage_lc = 'residential'
                    AND (
                        type_lc IN ('villa', 'complex villas')
                        OR subtype_lc LIKE '%villa%'
                        OR subtype_lc = 'arabian house'
                    ),
                'villa',
                type_lc = 'land',
                'land',
                usage_lc LIKE '%commercial%'
                    OR subtype_lc IN ('office', 'shop', 'show rooms', 'warehouse', 'workshop'),
                'commercial',
                'other'
            ) AS property_category
        FROM
        (
            SELECT
                r.*,
                lower(trim(r.usage_en)) AS usage_lc,
                lower(trim(r.prop_type_en)) AS type_lc,
                lower(trim(r.prop_sub_type_en)) AS subtype_lc,
                r.annual_amount / nullIf(r.actual_area, 0) AS rent_per_sqm_aed,
                toUInt8(
                    ifNull(
                        rent_per_sqm_aed > 10
                        AND rent_per_sqm_aed < 10000
                        AND r.actual_area > 0,
                        0
                    )
                ) AS is_rent_per_sqm_valid
            FROM dld_od_rents_bronze AS r
            CROSS JOIN open_data_cutoff
            WHERE r.annual_amount > 0
              AND (
                  r.source_system != 'dubai_pulse'
                  OR isNull(cutoff_date)
                  OR toDate(r.registration_date) < cutoff_date
              )
        ) AS source
    ) AS categorized
) AS classified
"""


def _materialize(
    *,
    clickhouse: ClickHouseClient,
    target_table: str,
    insert_sql: str,
) -> int:
    staging = f"{target_table}_staging"
    clickhouse.command(f"DROP TABLE IF EXISTS `{staging}`")
    clickhouse.command(f"CREATE TABLE `{staging}` AS `{target_table}`")
    try:
        clickhouse.command(insert_sql)
        clickhouse.command(f"EXCHANGE TABLES `{target_table}` AND `{staging}`")
    finally:
        clickhouse.command(f"DROP TABLE IF EXISTS `{staging}`")
    result = clickhouse.query(f"SELECT count() FROM `{target_table}`")
    return int(result.result_rows[0][0])


def materialize_silver_transactions(*, clickhouse: ClickHouseClient) -> int:
    ensure_schema(clickhouse=clickhouse)
    return _materialize(
        clickhouse=clickhouse,
        target_table="silver_transactions",
        insert_sql=_SILVER_TRANSACTIONS_SQL,
    )


def materialize_silver_rent_contracts(*, clickhouse: ClickHouseClient) -> int:
    ensure_schema(clickhouse=clickhouse)
    return _materialize(
        clickhouse=clickhouse,
        target_table="silver_rent_contracts",
        insert_sql=_SILVER_RENT_CONTRACTS_SQL,
    )
