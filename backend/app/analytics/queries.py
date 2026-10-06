from typing import Literal, Optional

from app.clickhouse.queries import ProjectFilterType, ProjectScopeType, _project_filter

TrendInterval = Literal["day", "week", "month"]


def search_projects() -> str:
    return """
        WITH virtual_masters AS (
            SELECT DISTINCT substring(project_name_en, 1, position(project_name_en, ' - ') - 1) AS prefix
            FROM ch_transactions
            WHERE position(project_name_en, ' - ') > 0
              AND (master_project_en = '' OR master_project_en IS NULL)
              AND project_name_en <> ''
        )
        SELECT name, filter_type
        FROM (
            SELECT DISTINCT master_project_en AS name, 'master' AS filter_type
            FROM ch_transactions
            WHERE master_project_en <> ''
              AND lower(master_project_en) LIKE {search_pattern:String}

            UNION ALL

            SELECT prefix AS name, 'virtual_master' AS filter_type
            FROM virtual_masters
            WHERE lower(prefix) LIKE {search_pattern:String}

            UNION ALL

            SELECT DISTINCT project_name_en AS name, 'project' AS filter_type
            FROM ch_transactions
            WHERE (master_project_en = '' OR master_project_en IS NULL)
              AND project_name_en <> ''
              AND lower(project_name_en) LIKE {search_pattern:String}
              AND project_name_en NOT IN (SELECT prefix FROM virtual_masters)
              AND (
                  position(project_name_en, ' - ') = 0
                  OR substring(project_name_en, 1, position(project_name_en, ' - ') - 1)
                     NOT IN (SELECT prefix FROM virtual_masters)
              )
              AND NOT (
                  position(project_name_en, ' - ') > 0
                  AND lower(substring(project_name_en, 1, position(project_name_en, ' - ') - 1))
                      IN (SELECT lower(master_project_en) FROM ch_transactions WHERE master_project_en <> '')
              )
        )
        ORDER BY name
        LIMIT {limit:Int32}
    """


def search_sub_projects(filter_type: ProjectFilterType = "master") -> str:
    if filter_type == "virtual_master":
        where = "project_name_en LIKE {master_project:String}"
    else:
        where = """(master_project_en = {master_project:String}
            OR (lower(project_name_en) LIKE concat(lower({master_project:String}), ' - %')
                AND (master_project_en = '' OR master_project_en IS NULL)))"""
    return f"""
        SELECT project_name_en, count() AS transaction_count
        FROM ch_transactions
        WHERE {where}
          AND project_name_en IS NOT NULL
          AND project_name_en <> ''
        GROUP BY project_name_en
        ORDER BY transaction_count DESC
    """


def project_sales_summary(
    filter_type: ProjectScopeType = "project", reg_type: Optional[str] = None
) -> str:
    reg_filter = "AND reg_type_en = {reg_type_en:String}" if reg_type else ""
    return f"""
        SELECT
            count() as transaction_count,
            round(coalesce(sum(actual_worth), 0), 2) as total_volume,
            round(coalesce(avg(actual_worth), 0), 2) as avg_price,
            round(coalesce(avg(meter_sale_price), 0), 2) as avg_price_sqm,
            round(coalesce(median(actual_worth), 0), 2) as median_price
        FROM ch_transactions
        WHERE {_project_filter(filter_type)}
          AND trans_group_en = 'Sales'
          AND property_type_en IN ('Unit', 'Villa')
          AND property_usage_en = 'Residential'
          AND actual_worth > 0
          {reg_filter}
    """


def project_sales_by_rooms(
    filter_type: ProjectScopeType = "project", reg_type: Optional[str] = None
) -> str:
    reg_filter = "AND reg_type_en = {reg_type_en:String}" if reg_type else ""
    return f"""
        SELECT
            rooms_en,
            count() as sale_count,
            round(avg(actual_worth), 2) as avg_sale_price,
            round(median(actual_worth), 2) as median_sale_price,
            round(avg(meter_sale_price), 2) as avg_sale_price_sqm
        FROM ch_transactions
        WHERE {_project_filter(filter_type)}
          AND trans_group_en = 'Sales'
          AND property_type_en IN ('Unit', 'Villa')
          AND property_usage_en = 'Residential'
          AND rooms_en IS NOT NULL
          AND actual_worth > 0
          {reg_filter}
        GROUP BY rooms_en
        ORDER BY sale_count DESC
    """


def project_configuration_sales(
    filter_type: ProjectScopeType = "project", reg_type: Optional[str] = None
) -> str:
    reg_filter = "AND reg_type_en = {reg_type_en:String}" if reg_type else ""
    return f"""
        WITH scoped_sales AS (
            SELECT
                rooms_en,
                instance_date,
                actual_worth,
                meter_sale_price
            FROM ch_transactions
            WHERE {_project_filter(filter_type)}
              AND trans_group_en = 'Sales'
              AND property_type_en IN ('Unit', 'Villa')
              AND property_usage_en = 'Residential'
              AND rooms_en IS NOT NULL
              AND actual_worth > 0
              {reg_filter}
        ),
        anchor AS (
            SELECT max(instance_date) AS latest_sale_date
            FROM scoped_sales
        )
        SELECT
            rooms_en,
            count() AS sale_count,
            countIf(instance_date >= addYears(latest_sale_date, -1)) AS sales_last_12m,
            countIf(
                instance_date >= addYears(latest_sale_date, -2)
                AND instance_date < addYears(latest_sale_date, -1)
            ) AS sales_prev_12m,
            countIf(instance_date >= addDays(latest_sale_date, -90)) AS sales_last_90d,
            countIf(
                instance_date >= addDays(latest_sale_date, -180)
                AND instance_date < addDays(latest_sale_date, -90)
            ) AS sales_prev_90d,
            round(avg(actual_worth), 2) AS avg_sale_price,
            round(median(actual_worth), 2) AS median_sale_price,
            round(avg(meter_sale_price), 2) AS avg_sale_price_sqm,
            round(quantile(0.25)(actual_worth), 2) AS price_p25,
            round(median(actual_worth), 2) AS price_p50,
            round(quantile(0.75)(actual_worth), 2) AS price_p75,
            round(avgIf(meter_sale_price, instance_date >= addYears(latest_sale_date, -1)), 2) AS avg_price_sqm_last_12m,
            round(
                avgIf(
                    meter_sale_price,
                    instance_date >= addYears(latest_sale_date, -2)
                    AND instance_date < addYears(latest_sale_date, -1)
                ),
                2
            ) AS avg_price_sqm_prev_12m
        FROM scoped_sales
        CROSS JOIN anchor
        GROUP BY rooms_en, latest_sale_date
        ORDER BY sale_count DESC
    """


def project_sales_by_property_type(filter_type: ProjectScopeType = "project") -> str:
    return f"""
        SELECT
            property_type_en,
            count() as count,
            round(avg(actual_worth), 2) as avg_price
        FROM ch_transactions
        WHERE {_project_filter(filter_type)}
          AND trans_group_en = 'Sales'
          AND property_type_en IS NOT NULL
          AND actual_worth > 0
        GROUP BY property_type_en
        ORDER BY count DESC
    """


def project_sales_by_reg_type(filter_type: ProjectScopeType = "project") -> str:
    return f"""
        SELECT
            reg_type_en,
            count() as count,
            round(avg(actual_worth), 2) as avg_price
        FROM ch_transactions
        WHERE {_project_filter(filter_type)}
          AND trans_group_en = 'Sales'
          AND property_type_en IN ('Unit', 'Villa')
          AND property_usage_en = 'Residential'
          AND reg_type_en IS NOT NULL
        GROUP BY reg_type_en
        ORDER BY count DESC
    """


def project_rentals_summary(filter_type: ProjectScopeType = "project") -> str:
    return f"""
        SELECT
            count() as contract_count,
            round(coalesce(sum(annual_amount), 0), 2) as total_annual_value,
            round(coalesce(median(annual_amount), 0), 2) as median_annual_rent,
            round(coalesce(median(annual_amount / nullIf(actual_area, 0)), 0), 2) as median_rent_sqm
        FROM ch_rent_contracts
        WHERE {_project_filter(filter_type)}
          AND property_usage_en = 'Residential'
          AND annual_amount > 0
    """


def project_rentals_by_rooms(filter_type: ProjectScopeType = "project") -> str:
    if filter_type == "market":
        unit_filter = "1 = 1"
    elif filter_type == "virtual_master":
        unit_filter = "project_name_en LIKE {project_name:String}"
    elif filter_type == "master":
        unit_filter = """(master_project_en = {project_name:String}
            OR (lower(project_name_en) LIKE concat(lower({project_name:String}), ' - %')
                AND (master_project_en = '' OR master_project_en IS NULL)))"""
    else:
        unit_filter = "project_name_en = {project_name:String}"

    rent_filter = _project_filter(filter_type)

    return f"""
        SELECT
            rooms_en,
            count() AS rental_count,
            round(median(annual_amount), 2) AS median_annual_rent,
            round(median(annual_amount / nullIf(actual_area, 0)), 2) AS median_rent_sqm
        FROM (
            SELECT any(ar.rooms_en) AS rooms_en, annual_amount, actual_area
            FROM ch_rent_contracts
            INNER JOIN (
                SELECT
                    rooms_en,
                    quantile(0.25)(actual_area) AS lo,
                    quantile(0.75)(actual_area) AS hi,
                    count() AS n
                FROM ch_units
                WHERE {unit_filter}
                  AND (rooms_en LIKE '% B/R' OR rooms_en = 'Studio' OR rooms_en LIKE '%ENTHOUSE')
                  AND actual_area > 0
                GROUP BY rooms_en
                HAVING n >= 3
            ) AS ar ON actual_area BETWEEN ar.lo AND ar.hi
            WHERE {rent_filter}
              AND property_usage_en = 'Residential'
              AND annual_amount > 0
              AND actual_area > 0
            GROUP BY contract_id, line_number, annual_amount, actual_area
            HAVING count(DISTINCT ar.rooms_en) = 1
        )
        GROUP BY rooms_en
        ORDER BY rental_count DESC
    """


def project_units_composition(filter_type: ProjectScopeType = "project") -> str:
    if filter_type == "market":
        where = "1 = 1"
    elif filter_type == "virtual_master":
        where = "project_name_en LIKE {project_name:String}"
    elif filter_type == "master":
        where = """(master_project_en = {project_name:String}
            OR (lower(project_name_en) LIKE concat(lower({project_name:String}), ' - %')
                AND (master_project_en = '' OR master_project_en IS NULL)))"""
    else:
        where = "master_project_en = {project_name:String}"
    return f"""
        SELECT
            rooms_en,
            count() as unit_count,
            round(avgIf(actual_area, actual_area > 0), 2) as avg_unit_size_sqm
        FROM ch_units
        WHERE {where}
          AND rooms_en IS NOT NULL
        GROUP BY rooms_en
        ORDER BY unit_count DESC
    """


def project_meta_by_name() -> str:
    return """
        SELECT
            p.project_name_en,
            p.area_name_en,
            coalesce(
                nullIf(d.developer_name_en, ''),
                nullIf(dn.developer_name_en, ''),
                nullIf(md.developer_name_en, ''),
                nullIf(mdn.developer_name_en, ''),
                nullIf(p.developer_name, ''),
                nullIf(p.master_developer_name, '')
            ) as developer_name_en,
            p.project_status,
            coalesce(p.completion_date, p.project_end_date) as completion_date,
            p.percent_completed,
            p.no_of_units,
            p.no_of_buildings
        FROM ch_projects p
        ANY LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
        ANY LEFT JOIN ch_developers dn
            ON notEmpty(trim(BOTH ' ' FROM ifNull(p.developer_name, '')))
            AND notEmpty(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')))
            AND replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.developer_name, '')), '\\s+', ' ')
                = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')), '\\s+', ' ')
        ANY LEFT JOIN ch_developers md ON p.master_developer_id = md.developer_id
        ANY LEFT JOIN ch_developers mdn
            ON notEmpty(trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')))
            AND notEmpty(trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')))
            AND replaceRegexpAll(
                trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')), '\\s+', ' '
            ) = replaceRegexpAll(
                trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')), '\\s+', ' '
            )
        WHERE p.project_name_en = {project_name:String}
        LIMIT 1
    """


def project_meta_by_master() -> str:
    return """
        SELECT
            any(p.area_name_en) as area_name_en,
            argMax(
                coalesce(
                    nullIf(d.developer_name_en, ''),
                    nullIf(dn.developer_name_en, ''),
                    nullIf(md.developer_name_en, ''),
                    nullIf(mdn.developer_name_en, ''),
                    nullIf(p.developer_name, ''),
                    nullIf(p.master_developer_name, '')
                ),
                coalesce(p.no_of_units, 0)
            ) as developer_name_en,
            nullIf(argMax(p.project_status, coalesce(p.percent_completed, 0)), '') as project_status,
            toNullable(
                if(
                    countIf(
                        coalesce(p.completion_date, p.project_end_date) IS NOT NULL
                        AND coalesce(p.completion_date, p.project_end_date) <= today()
                    ) > 0,
                    minIf(
                        coalesce(p.completion_date, p.project_end_date),
                        coalesce(p.completion_date, p.project_end_date) IS NOT NULL
                        AND coalesce(p.completion_date, p.project_end_date) <= today()
                    ),
                    minIf(
                        coalesce(p.completion_date, p.project_end_date),
                        coalesce(p.completion_date, p.project_end_date) IS NOT NULL
                        AND coalesce(p.completion_date, p.project_end_date) > today()
                    )
                )
            ) as completion_date,
            toNullable(round(sumWithOverflow(p.percent_completed * coalesce(p.no_of_units, 0)) / nullIf(sumWithOverflow(coalesce(p.no_of_units, 0)), 0), 1)) as percent_completed,
            toNullable(toInt64(sum(p.no_of_units))) as no_of_units,
            toNullable(toInt64(sum(p.no_of_buildings))) as no_of_buildings,
            arrayMap(
                x -> tupleElement(x, 2),
                arrayReverseSort(
                    x -> tupleElement(x, 1),
                    arrayFilter(
                        x -> notEmpty(tupleElement(x, 2)),
                        groupArray((
                            coalesce(p.no_of_units, 0),
                            coalesce(
                                nullIf(d.developer_name_en, ''),
                                nullIf(dn.developer_name_en, ''),
                                nullIf(md.developer_name_en, ''),
                                nullIf(mdn.developer_name_en, ''),
                                nullIf(p.developer_name, ''),
                                nullIf(p.master_developer_name, '')
                            )
                        ))
                    )
                )
            ) as developer_names
        FROM ch_projects p
        ANY LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
        ANY LEFT JOIN ch_developers dn
            ON notEmpty(trim(BOTH ' ' FROM ifNull(p.developer_name, '')))
            AND notEmpty(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')))
            AND replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.developer_name, '')), '\\s+', ' ')
                = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')), '\\s+', ' ')
        ANY LEFT JOIN ch_developers md ON p.master_developer_id = md.developer_id
        ANY LEFT JOIN ch_developers mdn
            ON notEmpty(trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')))
            AND notEmpty(trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')))
            AND replaceRegexpAll(
                trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')), '\\s+', ' '
            ) = replaceRegexpAll(
                trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')), '\\s+', ' '
            )
        WHERE (p.master_project_en = {project_name:String}
            OR lower(p.project_name_en) LIKE concat(lower({project_name:String}), ' - %'))
    """


def project_meta_by_virtual_master() -> str:
    return """
        SELECT
            any(p.area_name_en) as area_name_en,
            argMax(
                coalesce(
                    nullIf(d.developer_name_en, ''),
                    nullIf(dn.developer_name_en, ''),
                    nullIf(md.developer_name_en, ''),
                    nullIf(mdn.developer_name_en, ''),
                    nullIf(p.developer_name, ''),
                    nullIf(p.master_developer_name, '')
                ),
                coalesce(p.no_of_units, 0)
            ) as developer_name_en,
            nullIf(argMax(p.project_status, coalesce(p.percent_completed, 0)), '') as project_status,
            toNullable(
                if(
                    countIf(
                        coalesce(p.completion_date, p.project_end_date) IS NOT NULL
                        AND coalesce(p.completion_date, p.project_end_date) <= today()
                    ) > 0,
                    minIf(
                        coalesce(p.completion_date, p.project_end_date),
                        coalesce(p.completion_date, p.project_end_date) IS NOT NULL
                        AND coalesce(p.completion_date, p.project_end_date) <= today()
                    ),
                    minIf(
                        coalesce(p.completion_date, p.project_end_date),
                        coalesce(p.completion_date, p.project_end_date) IS NOT NULL
                        AND coalesce(p.completion_date, p.project_end_date) > today()
                    )
                )
            ) as completion_date,
            toNullable(round(sumWithOverflow(p.percent_completed * coalesce(p.no_of_units, 0)) / nullIf(sumWithOverflow(coalesce(p.no_of_units, 0)), 0), 1)) as percent_completed,
            toNullable(toInt64(sum(p.no_of_units))) as no_of_units,
            toNullable(toInt64(sum(p.no_of_buildings))) as no_of_buildings,
            arrayMap(
                x -> tupleElement(x, 2),
                arrayReverseSort(
                    x -> tupleElement(x, 1),
                    arrayFilter(
                        x -> notEmpty(tupleElement(x, 2)),
                        groupArray((
                            coalesce(p.no_of_units, 0),
                            coalesce(
                                nullIf(d.developer_name_en, ''),
                                nullIf(dn.developer_name_en, ''),
                                nullIf(md.developer_name_en, ''),
                                nullIf(mdn.developer_name_en, ''),
                                nullIf(p.developer_name, ''),
                                nullIf(p.master_developer_name, '')
                            )
                        ))
                    )
                )
            ) as developer_names
        FROM ch_projects p
        LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
        LEFT JOIN ch_developers dn
            ON replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.developer_name, '')), '\\s+', ' ')
            = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')), '\\s+', ' ')
        LEFT JOIN ch_developers md ON p.master_developer_id = md.developer_id
        LEFT JOIN ch_developers mdn
            ON replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')), '\\s+', ' ')
            = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')), '\\s+', ' ')
        WHERE p.project_name_en LIKE {project_name:String}
    """


def project_developers_by_scope(filter_type: ProjectFilterType = "master") -> str:
    if filter_type == "virtual_master":
        where = "p.project_name_en LIKE {project_name:String}"
    else:
        where = """(p.master_project_en = {project_name:String}
            OR lower(p.project_name_en) LIKE concat(lower({project_name:String}), ' - %'))"""

    return f"""
        SELECT
            developer_name_en,
            toInt64(sum(unit_count)) AS unit_count,
            count() AS development_count
        FROM (
            SELECT
                replaceRegexpAll(
                    trim(BOTH ' ' FROM coalesce(
                        nullIf(d.developer_name_en, ''),
                        nullIf(dn.developer_name_en, ''),
                        nullIf(md.developer_name_en, ''),
                        nullIf(mdn.developer_name_en, ''),
                        nullIf(p.developer_name, ''),
                        nullIf(p.master_developer_name, ''),
                        ''
                    )),
                    '\\s+',
                    ' '
                ) AS developer_name_en,
                coalesce(p.no_of_units, 0) AS unit_count
            FROM ch_projects p
            LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
            LEFT JOIN ch_developers dn
                ON replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.developer_name, '')), '\\s+', ' ')
                = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')), '\\s+', ' ')
            LEFT JOIN ch_developers md ON p.master_developer_id = md.developer_id
            LEFT JOIN ch_developers mdn
                ON replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')), '\\s+', ' ')
                = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')), '\\s+', ' ')
            WHERE {where}
        )
        WHERE developer_name_en <> ''
        GROUP BY developer_name_en
        ORDER BY unit_count DESC, development_count DESC, developer_name_en ASC
    """


def project_price_distribution(
    filter_type: ProjectScopeType = "project", reg_type: Optional[str] = None
) -> str:
    reg_filter = "AND reg_type_en = {reg_type_en:String}" if reg_type else ""
    project_filter = _project_filter(filter_type)
    return f"""
        SELECT
            rooms_en,
            count() as sale_count,
            round(avg(actual_worth), 2) as mean_price,
            round(stddevPop(actual_worth), 2) as std_price,
            round(avg(log(actual_worth)), 6) as log_mean_price,
            round(stddevPop(log(actual_worth)), 6) as log_std_price,
            round(quantile(0.05)(actual_worth), 2) as p05_price,
            round(quantile(0.25)(actual_worth), 2) as p25_price,
            round(quantile(0.50)(actual_worth), 2) as p50_price,
            round(quantile(0.75)(actual_worth), 2) as p75_price,
            round(quantile(0.95)(actual_worth), 2) as p95_price,
            round(avg(meter_sale_price), 2) as mean_price_sqm,
            round(stddevPop(meter_sale_price), 2) as std_price_sqm
        FROM ch_transactions
        WHERE {project_filter}
          AND trans_group_en = 'Sales'
          AND property_type_en IN ('Unit', 'Villa')
          AND property_usage_en = 'Residential'
          AND rooms_en IS NOT NULL
          AND actual_worth > 0
          {reg_filter}
        GROUP BY rooms_en
        UNION ALL
        SELECT
            '__all__' as rooms_en,
            count() as sale_count,
            round(avg(actual_worth), 2) as mean_price,
            round(stddevPop(actual_worth), 2) as std_price,
            round(avg(log(actual_worth)), 6) as log_mean_price,
            round(stddevPop(log(actual_worth)), 6) as log_std_price,
            round(quantile(0.05)(actual_worth), 2) as p05_price,
            round(quantile(0.25)(actual_worth), 2) as p25_price,
            round(quantile(0.50)(actual_worth), 2) as p50_price,
            round(quantile(0.75)(actual_worth), 2) as p75_price,
            round(quantile(0.95)(actual_worth), 2) as p95_price,
            round(avg(meter_sale_price), 2) as mean_price_sqm,
            round(stddevPop(meter_sale_price), 2) as std_price_sqm
        FROM ch_transactions
        WHERE {project_filter}
          AND trans_group_en = 'Sales'
          AND property_type_en IN ('Unit', 'Villa')
          AND property_usage_en = 'Residential'
          AND actual_worth > 0
          {reg_filter}
    """


def project_price_trends(
    interval: TrendInterval = "month", filter_type: ProjectScopeType = "project"
) -> str:
    if interval not in ("day", "week", "month"):
        raise ValueError("interval must be 'day', 'week', or 'month'")

    if interval == "day":
        time_group = "instance_date"
    elif interval == "week":
        time_group = "toStartOfWeek(instance_date)"
    else:
        time_group = "toStartOfMonth(instance_date)"

    return f"""
        SELECT
            {time_group} as period,
            count() as transaction_count,
            round(avg(actual_worth), 2) as avg_price,
            round(avg(meter_sale_price), 2) as avg_price_sqm
        FROM ch_transactions
        WHERE {_project_filter(filter_type)}
          AND trans_group_en = 'Sales'
          AND property_type_en IN ('Unit', 'Villa')
          AND property_usage_en = 'Residential'
          AND instance_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
          AND actual_worth > 0
        GROUP BY period
        ORDER BY period ASC
    """


def project_offplan_price_curve(
    interval: TrendInterval = "month", filter_type: ProjectScopeType = "project"
) -> str:
    if interval not in ("day", "week", "month"):
        raise ValueError("interval must be 'day', 'week', or 'month'")

    if interval == "day":
        time_group = "t.instance_date"
    elif interval == "week":
        time_group = "toStartOfWeek(t.instance_date)"
    else:
        time_group = "toStartOfMonth(t.instance_date)"

    project_where = (
        _project_filter(filter_type)
        .replace("project_name_en", "t.project_name_en")
        .replace("master_project_en", "t.master_project_en")
    )

    return f"""
        SELECT
            {time_group} as period,
            count() as transaction_count,
            round(avg(t.actual_worth), 2) as avg_price,
            round(avg(t.meter_sale_price), 2) as avg_price_sqm,
            round(
                avg(dateDiff('month', t.instance_date, coalesce(p.completion_date, p.project_end_date))),
                2
            ) as avg_months_to_delivery
        FROM ch_transactions t
        LEFT JOIN ch_projects p ON t.project_name_en = p.project_name_en
        WHERE {project_where}
          AND t.trans_group_en = 'Sales'
          AND t.property_type_en IN ('Unit', 'Villa')
          AND t.property_usage_en = 'Residential'
          AND t.reg_type_en = 'Off-Plan Properties'
          AND t.instance_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
          AND t.actual_worth > 0
          AND coalesce(p.completion_date, p.project_end_date) IS NOT NULL
          AND dateDiff('month', t.instance_date, coalesce(p.completion_date, p.project_end_date)) >= 0
        GROUP BY period
        ORDER BY period ASC
    """


def area_supply_projects(filter_by_area: bool = True) -> str:
    area_filter = "p.area_name_en = {area_name:String} AND" if filter_by_area else ""
    return f"""
        SELECT
            p.project_name_en,
            coalesce(
                nullIf(d.developer_name_en, ''),
                nullIf(dn.developer_name_en, ''),
                nullIf(md.developer_name_en, ''),
                nullIf(mdn.developer_name_en, ''),
                nullIf(p.developer_name, ''),
                nullIf(p.master_developer_name, '')
            ) as developer_name_en,
            p.area_name_en,
            p.project_status,
            p.project_start_date,
            p.project_end_date,
            p.completion_date,
            p.percent_completed,
            p.no_of_units
        FROM ch_projects p
        ANY LEFT JOIN ch_developers d ON p.developer_id = d.developer_id
        ANY LEFT JOIN ch_developers dn
            ON notEmpty(trim(BOTH ' ' FROM ifNull(p.developer_name, '')))
            AND notEmpty(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')))
            AND replaceRegexpAll(trim(BOTH ' ' FROM ifNull(p.developer_name, '')), '\\s+', ' ')
                = replaceRegexpAll(trim(BOTH ' ' FROM ifNull(dn.developer_name_ar, '')), '\\s+', ' ')
        ANY LEFT JOIN ch_developers md ON p.master_developer_id = md.developer_id
        ANY LEFT JOIN ch_developers mdn
            ON notEmpty(trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')))
            AND notEmpty(trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')))
            AND replaceRegexpAll(
                trim(BOTH ' ' FROM ifNull(p.master_developer_name, '')), '\\s+', ' '
            ) = replaceRegexpAll(
                trim(BOTH ' ' FROM ifNull(mdn.developer_name_ar, '')), '\\s+', ' '
            )
        WHERE {area_filter}
          coalesce(p.no_of_units, 0) > 0
          AND p.cancellation_date IS NULL
    """
