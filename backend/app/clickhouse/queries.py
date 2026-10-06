from typing import Literal, Optional

ProjectFilterType = Literal["project", "master", "virtual_master"]
ProjectScopeType = Literal["project", "master", "virtual_master", "market"]

# Server-side market type filters — frontend passes market_type, never raw predicates.
# See analytics_architecture.md for taxonomy rationale.
MARKET_FILTERS: dict[str, dict] = {
    "residential_units": {
        "property_type_en": "Unit",
        "property_usage_en": "Residential",
        "trans_group_en": "Sales",
    },
    "villas": {
        "property_type_en": "Villa",
        "trans_group_en": "Sales",
    },
    "commercial_units": {
        "property_type_en": "Unit",
        "property_usage_en__in": ["Commercial", "Hospitality"],
        "trans_group_en": "Sales",
    },
    "bulk_building": {
        "property_type_en": "Building",
        "trans_group_en": "Sales",
    },
    "land": {
        "property_type_en": "Land",
        "trans_group_en": "Sales",
    },
    "mortgages": {"trans_group_en": "Mortgages"},
    "gifts": {"trans_group_en": "Gifts"},
}


def sales_summary(
    property_usage: Optional[str],
    start_date: str,
    end_date: str,
    master_project: Optional[str] = None,
    property_type: Optional[str] = None,
    property_sub_type: Optional[str] = None,
    rooms: Optional[str] = None,
    area_name: Optional[str] = None,
    reg_type: Optional[str] = None,
    price_bucket: Optional[str] = None,
    area_bucket: Optional[str] = None,
    property_usage_in: Optional[list] = None,
) -> str:
    """
    Get sales analytics summary for a date range.

    Returns: transaction_count, median_price, avg_price, total_volume,
             median_price_per_sqm, median_area_sqm

    All filtering uses parameter binding - no SQL injection risk.
    property_usage_in values must come from MARKET_FILTERS (trusted, not user input).
    """
    # Build WHERE clause with parameter placeholders
    where_clauses = [
        "trans_group_en = 'Sales'",
        "instance_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]
    if property_usage is not None:
        where_clauses.append("property_usage_en = {property_usage:String}")
    elif property_usage_in is not None:
        vals = "', '".join(property_usage_in)
        where_clauses.append(f"property_usage_en IN ('{vals}')")

    if master_project is not None:
        where_clauses.append("master_project_en = {master_project:String}")
    if property_type is not None:
        where_clauses.append("property_type_en = {property_type:String}")
    if property_sub_type is not None:
        where_clauses.append("property_sub_type_en = {property_sub_type:String}")
    if rooms is not None:
        where_clauses.append("rooms_en = {rooms:String}")
    if area_name is not None:
        where_clauses.append("area_name_en = {area_name:String}")
    if reg_type is not None:
        where_clauses.append("reg_type_en = {reg_type:String}")
    if price_bucket is not None:
        where_clauses.append("price_bucket = {price_bucket:String}")
    if area_bucket is not None:
        where_clauses.append("area_bucket = {area_bucket:String}")

    where_clause = " AND ".join(where_clauses)

    return f"""
        SELECT
            count() as transaction_count,
            round(median(actual_worth), 2) as median_price,
            round(avg(actual_worth), 2) as avg_price,
            round(sum(actual_worth), 2) as total_volume,
            round(median(meter_sale_price), 2) as median_price_per_sqm,
            round(median(procedure_area), 2) as median_area_sqm
        FROM ch_transactions
        WHERE {where_clause}
    """


def price_trends(
    property_usage: Optional[str],
    start_date: str,
    end_date: str,
    interval: str = "month",
    master_project: Optional[str] = None,
    property_type: Optional[str] = None,
    area_name: Optional[str] = None,
    property_usage_in: Optional[list] = None,
) -> str:
    """
    Get price trends over time (grouped by day, week, or month).

    Args:
        interval: 'day', 'week', or 'month'

    Returns: period, transaction_count, avg_price, avg_price_sqm
    property_usage_in values must come from MARKET_FILTERS (trusted, not user input).
    """
    # SAFE: interval is controlled by application, not user input
    if interval not in ("day", "week", "month"):
        raise ValueError("interval must be 'day', 'week', or 'month'")

    if interval == "day":
        time_group = "toDate(instance_date)"
    elif interval == "week":
        time_group = "toStartOfWeek(instance_date)"
    else:
        time_group = "toStartOfMonth(instance_date)"

    where_clauses = [
        "trans_group_en = 'Sales'",
        "instance_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]
    if property_usage is not None:
        where_clauses.append("property_usage_en = {property_usage:String}")
    elif property_usage_in is not None:
        vals = "', '".join(property_usage_in)
        where_clauses.append(f"property_usage_en IN ('{vals}')")

    if master_project is not None:
        where_clauses.append("master_project_en = {master_project:String}")
    if property_type is not None:
        where_clauses.append("property_type_en = {property_type:String}")
    if area_name is not None:
        where_clauses.append("area_name_en = {area_name:String}")

    where_clause = " AND ".join(where_clauses)

    return f"""
        SELECT
            {time_group} as period,
            count() as transaction_count,
            round(avg(actual_worth), 2) as avg_price,
            round(avg(meter_sale_price), 2) as avg_price_sqm
        FROM ch_transactions
        WHERE {where_clause}
        GROUP BY period
        ORDER BY period ASC
    """


def rentals_summary(
    property_usage: str,
    start_date: str,
    end_date: str,
    master_project: Optional[str] = None,
    property_type: Optional[str] = None,
    area_name: Optional[str] = None,
) -> str:
    """
    Get rental analytics summary for a date range.

    Returns: contract_count, median_rent, avg_rent, total_annual_value,
             median_rent_per_sqm, median_area_sqm
    """
    where_clauses = [
        "property_usage_en = {property_usage:String}",
        "contract_start_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]

    if master_project is not None:
        where_clauses.append("master_project_en = {master_project:String}")
    if property_type is not None:
        where_clauses.append("ejari_property_type_en = {property_type:String}")
    if area_name is not None:
        where_clauses.append("area_name_en = {area_name:String}")

    where_clause = " AND ".join(where_clauses)

    return f"""
        SELECT
            count() as contract_count,
            round(median(annual_amount), 2) as median_rent,
            round(avg(annual_amount), 2) as avg_rent,
            round(sum(annual_amount), 2) as total_annual_value,
            round(median(annual_amount / nullIf(actual_area, 0)), 2) as median_rent_per_sqm,
            round(median(actual_area), 2) as median_area_sqm
        FROM ch_rent_contracts
        WHERE {where_clause}
    """


def _project_filter(filter_type: ProjectScopeType) -> str:
    """WHERE clause condition for a given filter type.

    master: matches rows with master_project_en = X OR orphaned rows whose
    project_name_en starts with X + ' - ' (absorbs inconsistently-linked sub-projects).
    """
    if filter_type == "market":
        return "1 = 1"
    if filter_type == "master":
        return """(master_project_en = {project_name:String}
            OR (lower(project_name_en) LIKE concat(lower({project_name:String}), ' - %')
                AND (master_project_en = '' OR master_project_en IS NULL)))"""
    if filter_type == "virtual_master":
        return "project_name_en LIKE {project_name:String}"
    return "project_name_en = {project_name:String}"
