"""Filter options service for transaction and rental facets."""

import re
from typing import Optional

from app.clickhouse.client import query
from app.clickhouse.queries import _project_filter
from app.filters.models import FilterOptionsResponse


def _rooms_sort_key(room: str) -> tuple:
    """Studio first, then numeric bedroom counts in order, then anything else."""
    normalized = room.strip()
    if normalized.lower() == "studio":
        return (0, 0, normalized)
    m = re.match(r"^(\d+)", normalized)
    if m:
        return (1, int(m.group(1)), normalized)
    return (2, 0, normalized.lower())


def _clean_option(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_options(rows: list[dict], field: str) -> list[str]:
    values = {_clean_option(row.get(field)) for row in rows}
    return sorted(value for value in values if value is not None)


def _normalize_room_options(rows: list[dict], field: str) -> list[str]:
    values = {_clean_option(row.get(field)) for row in rows}
    return sorted((value for value in values if value is not None), key=_rooms_sort_key)


def _append_common_transaction_filters(
    where_clauses: list[str],
    params: dict,
    *,
    property_usage: Optional[str] = None,
    project: Optional[str] = None,
    filter_type: str = "project",
    property_type_field: str,
    property_type: Optional[str] = None,
    property_sub_type_field: str,
    property_sub_type: Optional[str] = None,
    area: Optional[str] = None,
    timeframe_field: str,
    timeframe_days: Optional[int] = None,
    area_field: str,
    area_min: Optional[float] = None,
    area_max: Optional[float] = None,
) -> None:
    if property_usage:
        where_clauses.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage

    if project:
        where_clauses.append(_project_filter(filter_type))
        params["project_name"] = project + " - %" if filter_type == "virtual_master" else project

    if property_type:
        where_clauses.append(f"{property_type_field} = {{property_type:String}}")
        params["property_type"] = property_type

    if property_sub_type:
        where_clauses.append(f"{property_sub_type_field} = {{property_sub_type:String}}")
        params["property_sub_type"] = property_sub_type

    if area:
        where_clauses.append("area_name_en = {area:String}")
        params["area"] = area

    if timeframe_days is not None:
        where_clauses.append(f"{timeframe_field} >= today() - {{timeframe_days:Int32}}")
        params["timeframe_days"] = timeframe_days

    if area_min is not None:
        where_clauses.append(f"{area_field} >= {{area_min:Decimal64(2)}}")
        params["area_min"] = area_min

    if area_max is not None:
        where_clauses.append(f"{area_field} <= {{area_max:Decimal64(2)}}")
        params["area_max"] = area_max


async def get_sales_filter_options(
    property_usage: Optional[str] = None,
    project: Optional[str] = None,
    filter_type: str = "project",
    property_type: Optional[str] = None,
    property_sub_type: Optional[str] = None,
    rooms: Optional[str] = None,
    registration_type: Optional[str] = None,
    area: Optional[str] = None,
    building: Optional[str] = None,
    timeframe_days: Optional[int] = None,
    area_min: Optional[float] = None,
    area_max: Optional[float] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    price_per_sqm_min: Optional[float] = None,
    price_per_sqm_max: Optional[float] = None,
) -> FilterOptionsResponse:
    """Get dynamically narrowed filter options for sales transactions."""

    where_clauses = ["trans_group_en = 'Sales'"]
    params: dict = {}

    _append_common_transaction_filters(
        where_clauses,
        params,
        property_usage=property_usage,
        project=project,
        filter_type=filter_type,
        property_type_field="property_type_en",
        property_type=property_type,
        property_sub_type_field="property_sub_type_en",
        property_sub_type=property_sub_type,
        area=area,
        timeframe_field="instance_date",
        timeframe_days=timeframe_days,
        area_field="procedure_area",
        area_min=area_min,
        area_max=area_max,
    )

    if rooms:
        where_clauses.append("rooms_en = {rooms:String}")
        params["rooms"] = rooms

    if registration_type:
        where_clauses.append("reg_type_en = {registration_type:String}")
        params["registration_type"] = registration_type

    if building:
        where_clauses.append("building_name_en = {building:String}")
        params["building"] = building

    if price_min is not None:
        where_clauses.append("actual_worth >= {price_min:Decimal64(2)}")
        params["price_min"] = price_min

    if price_max is not None:
        where_clauses.append("actual_worth <= {price_max:Decimal64(2)}")
        params["price_max"] = price_max

    if price_per_sqm_min is not None:
        where_clauses.append("meter_sale_price >= {price_per_sqm_min:Decimal64(2)}")
        params["price_per_sqm_min"] = price_per_sqm_min

    if price_per_sqm_max is not None:
        where_clauses.append("meter_sale_price <= {price_per_sqm_max:Decimal64(2)}")
        params["price_per_sqm_max"] = price_per_sqm_max

    where_clause = " AND ".join(where_clauses)

    property_types_result = await query(
        f"""
        SELECT DISTINCT property_type_en
        FROM ch_transactions
        WHERE {where_clause} AND property_type_en != ''
        ORDER BY property_type_en
        """,
        params,
    )
    property_sub_types_result = await query(
        f"""
        SELECT DISTINCT property_sub_type_en
        FROM ch_transactions
        WHERE {where_clause} AND property_sub_type_en != ''
        ORDER BY property_sub_type_en
        """,
        params,
    )
    rooms_result = await query(
        f"""
        SELECT DISTINCT rooms_en
        FROM ch_transactions
        WHERE {where_clause} AND rooms_en != ''
        """,
        params,
    )
    reg_types_result = await query(
        f"""
        SELECT DISTINCT reg_type_en
        FROM ch_transactions
        WHERE {where_clause} AND reg_type_en != ''
        ORDER BY reg_type_en
        """,
        params,
    )
    areas_result = await query(
        f"""
        SELECT DISTINCT area_name_en
        FROM ch_transactions
        WHERE {where_clause} AND area_name_en != ''
        ORDER BY area_name_en
        """,
        params,
    )
    projects_result = await query(
        f"""
        SELECT DISTINCT project_name_en
        FROM ch_transactions
        WHERE {where_clause} AND project_name_en != ''
        ORDER BY project_name_en
        """,
        params,
    )
    buildings_result = await query(
        f"""
        SELECT DISTINCT building_name_en
        FROM ch_transactions
        WHERE {where_clause} AND building_name_en != ''
        ORDER BY building_name_en
        LIMIT 1000
        """,
        params,
    )

    return FilterOptionsResponse(
        property_types=_normalize_options(property_types_result, "property_type_en"),
        property_sub_types=_normalize_options(property_sub_types_result, "property_sub_type_en"),
        rooms=_normalize_room_options(rooms_result, "rooms_en"),
        registration_types=_normalize_options(reg_types_result, "reg_type_en"),
        areas=_normalize_options(areas_result, "area_name_en"),
        projects=_normalize_options(projects_result, "project_name_en"),
        buildings=_normalize_options(buildings_result, "building_name_en"),
    )


async def get_rental_filter_options(
    property_usage: Optional[str] = None,
    project: Optional[str] = None,
    filter_type: str = "project",
    property_type: Optional[str] = None,
    property_sub_type: Optional[str] = None,
    tenant_type: Optional[str] = None,
    contract_reg_type: Optional[str] = None,
    area: Optional[str] = None,
    timeframe_days: Optional[int] = None,
    area_min: Optional[float] = None,
    area_max: Optional[float] = None,
    rent_min: Optional[float] = None,
    rent_max: Optional[float] = None,
) -> FilterOptionsResponse:
    """Get dynamically narrowed filter options for rental contracts."""

    where_clauses: list[str] = []
    params: dict = {}

    _append_common_transaction_filters(
        where_clauses,
        params,
        property_usage=property_usage,
        project=project,
        filter_type=filter_type,
        property_type_field="ejari_property_type_en",
        property_type=property_type,
        property_sub_type_field="ejari_property_sub_type_en",
        property_sub_type=property_sub_type,
        area=area,
        timeframe_field="contract_start_date",
        timeframe_days=timeframe_days,
        area_field="actual_area",
        area_min=area_min,
        area_max=area_max,
    )

    if tenant_type:
        where_clauses.append("tenant_type_en = {tenant_type:String}")
        params["tenant_type"] = tenant_type

    if contract_reg_type:
        where_clauses.append("contract_reg_type_en = {contract_reg_type:String}")
        params["contract_reg_type"] = contract_reg_type

    if rent_min is not None:
        where_clauses.append("annual_amount >= {rent_min:Decimal64(2)}")
        params["rent_min"] = rent_min

    if rent_max is not None:
        where_clauses.append("annual_amount <= {rent_max:Decimal64(2)}")
        params["rent_max"] = rent_max

    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

    property_types_result = await query(
        f"""
        SELECT DISTINCT ejari_property_type_en
        FROM ch_rent_contracts
        WHERE {where_clause} AND ejari_property_type_en != ''
        ORDER BY ejari_property_type_en
        """,
        params,
    )
    property_sub_types_result = await query(
        f"""
        SELECT DISTINCT ejari_property_sub_type_en
        FROM ch_rent_contracts
        WHERE {where_clause} AND ejari_property_sub_type_en != ''
        ORDER BY ejari_property_sub_type_en
        """,
        params,
    )
    tenant_types_result = await query(
        f"""
        SELECT DISTINCT tenant_type_en
        FROM ch_rent_contracts
        WHERE {where_clause} AND tenant_type_en != ''
        ORDER BY tenant_type_en
        """,
        params,
    )
    contract_reg_types_result = await query(
        f"""
        SELECT DISTINCT contract_reg_type_en
        FROM ch_rent_contracts
        WHERE {where_clause} AND contract_reg_type_en != ''
        ORDER BY contract_reg_type_en
        """,
        params,
    )
    areas_result = await query(
        f"""
        SELECT DISTINCT area_name_en
        FROM ch_rent_contracts
        WHERE {where_clause} AND area_name_en != ''
        ORDER BY area_name_en
        """,
        params,
    )
    projects_result = await query(
        f"""
        SELECT DISTINCT project_name_en
        FROM ch_rent_contracts
        WHERE {where_clause} AND project_name_en != ''
        ORDER BY project_name_en
        """,
        params,
    )

    return FilterOptionsResponse(
        property_types=_normalize_options(property_types_result, "ejari_property_type_en"),
        property_sub_types=_normalize_options(
            property_sub_types_result, "ejari_property_sub_type_en"
        ),
        tenant_types=_normalize_options(tenant_types_result, "tenant_type_en"),
        contract_reg_types=_normalize_options(contract_reg_types_result, "contract_reg_type_en"),
        areas=_normalize_options(areas_result, "area_name_en"),
        projects=_normalize_options(projects_result, "project_name_en"),
        buildings=[],
    )
