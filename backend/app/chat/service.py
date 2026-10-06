import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, AsyncGenerator, List, Optional

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.messages import (
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.openrouter import OpenRouterModelSettings
from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.chat.agent import agent
from app.chat.models import Conversation, Message
from app.clickhouse import query as ch_query
from app.clickhouse.queries import price_trends
from app.core.market_constants import SQM_TO_SQFT
from app.core.normalization import area_search_text, listing_area_terms
from app.listings.models import ListingMode
from app.listings.service import list_listings_from_clickhouse
from app.token_usage.service import token_usage_service

logger = logging.getLogger(__name__)

SALE_LISTING_INTENT_RE = re.compile(
    r"\b(buy|buying|purchase|sales?|for[-\s]?sale|off[-\s]?plan|resale)\b",
    re.IGNORECASE,
)
DEFAULT_CHART_DAYS = 365
MIN_CHART_DAYS = 30
MAX_CHART_DAYS = 3650
DAILY_INTERVAL_MAX_DAYS = 30
WEEKLY_INTERVAL_MAX_DAYS = 180


async def create_conversation(
    db: AsyncSession, user_id: str, organization_id: str, title: Optional[str] = None
) -> Conversation:
    """Create a new conversation"""
    now = datetime.now(timezone.utc)
    conversation = Conversation(
        user_id=user_id,
        organization_id=organization_id,
        title=title or "New Conversation",
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def get_user_conversations(
    db: AsyncSession, user_id: str, limit: int = 50, offset: int = 0
) -> List[Conversation]:
    """Get all conversations for a user"""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.exec(stmt)
    return list(result.all())


async def get_conversation(
    db: AsyncSession, conversation_id: int, user_id: str
) -> Optional[Conversation]:
    """Get a conversation by ID (with auth check)"""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    result = await db.exec(stmt)
    return result.first()


async def update_conversation(
    db: AsyncSession, conversation_id: int, user_id: str, title: str
) -> Optional[Conversation]:
    """Update a conversation's title"""
    conversation = await get_conversation(db, conversation_id, user_id)
    if not conversation:
        return None

    conversation.title = title
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def delete_conversation(db: AsyncSession, conversation_id: int, user_id: str) -> bool:
    """Delete a conversation and all its messages"""
    conversation = await get_conversation(db, conversation_id, user_id)
    if not conversation:
        return False

    await db.execute(
        delete(Message)
        .where(Message.conversation_id == conversation_id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        delete(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return True


async def get_conversation_messages(
    db: AsyncSession, conversation_id: int, limit: int = 100
) -> List[Message]:
    """Get messages for a conversation"""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    result = await db.exec(stmt)
    return list(result.all())


async def add_message(
    db: AsyncSession,
    conversation_id: int,
    role: str,
    content: str,
    meta_data: Optional[dict[str, Any]] = None,
) -> Message:
    """Add a message to a conversation"""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        meta_data=meta_data or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(message)

    # Update conversation timestamp
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.exec(stmt)
    conversation = result.first()
    if conversation:
        conversation.updated_at = datetime.now(timezone.utc)
        # Auto-generate title from first user message
        if not conversation.title or conversation.title == "New Conversation":
            conversation.title = content[:50] + ("..." if len(content) > 50 else "")

    await db.commit()
    await db.refresh(message)
    return message


def _format_history_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _artifact_point_summary(point: dict[str, Any], metric_label: str | None) -> str:
    label = str(point.get("label") or "Unknown")
    value = _format_history_value(point.get("value"))
    record_count = point.get("record_count")
    records = f", {_format_history_value(record_count)} records" if record_count is not None else ""
    metric = metric_label or "value"
    return f"{label}: {metric} {value}{records}"


def _artifact_history_context(meta_data: dict[str, Any] | None) -> str | None:
    artifacts = (meta_data or {}).get("artifacts")
    if not isinstance(artifacts, list):
        return None

    lines: list[str] = []
    for artifact in artifacts[-3:]:
        if not isinstance(artifact, dict) or artifact.get("status") != "ready":
            continue

        artifact_type = artifact.get("type")
        query = artifact.get("query") if isinstance(artifact.get("query"), dict) else {}
        data = artifact.get("data") if isinstance(artifact.get("data"), dict) else {}

        if artifact_type == "custom_chart":
            title = str(artifact.get("title") or data.get("metric_label") or "Chart")
            subtitle = str(artifact.get("subtitle") or "")
            metric_label = str(data.get("metric_label") or "value")
            sort_direction = str(
                data.get("sort_direction") or query.get("sort_direction") or "desc"
            )
            points = data.get("points") if isinstance(data.get("points"), list) else []
            series = data.get("series") if isinstance(data.get("series"), list) else []

            if points:
                row_summaries = [
                    _artifact_point_summary(point, metric_label)
                    for point in points[:5]
                    if isinstance(point, dict)
                ]
            else:
                row_summaries = []
                for item in series[:5]:
                    if not isinstance(item, dict):
                        continue
                    series_points = (
                        item.get("points") if isinstance(item.get("points"), list) else []
                    )
                    latest_point = series_points[-1] if series_points else {}
                    if isinstance(latest_point, dict):
                        row_summaries.append(
                            _artifact_point_summary(
                                {**latest_point, "label": item.get("label")},
                                metric_label,
                            )
                        )

            if row_summaries:
                scope = f" ({subtitle})" if subtitle else ""
                lines.append(
                    f"Rendered chart{scope}: {title}; sort {sort_direction}; "
                    f"displayed rows in order: {'; '.join(row_summaries)}."
                )

        elif artifact_type == "listing_results":
            title = str(artifact.get("title") or "Listings")
            mode = str(query.get("mode") or "")
            area = str(query.get("area") or "Dubai")
            total = data.get("total")
            lines.append(
                f"Rendered listings card: {title}; mode {mode or 'unknown'}; "
                f"area {area}; exact matches {_format_history_value(total)}."
            )

        elif artifact_type == "market_trend":
            title = str(artifact.get("title") or "Market trend")
            area = str(query.get("area") or "Dubai")
            total = data.get("total_transactions")
            summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
            period_start = summary.get("period_start")
            period_end = summary.get("period_end")
            period = (
                f"; period {period_start} to {period_end}" if period_start and period_end else ""
            )
            lines.append(
                f"Rendered market trend card: {title}; area {area}; "
                f"transactions {_format_history_value(total)}{period}."
            )

    if not lines:
        return None
    return "\n".join(lines)


def _convert_to_pydantic_messages(messages: List[Message]) -> List[ModelMessage]:
    """Convert database messages to Pydantic AI message format"""
    pydantic_messages: List[ModelMessage] = []

    for msg in messages:
        if msg.role == "user":
            pydantic_messages.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        elif msg.role == "assistant":
            artifact_context = _artifact_history_context(msg.meta_data)
            content = msg.content
            if artifact_context:
                content = (
                    f"{content}\n\n"
                    "[Rendered card context for follow-up references]\n"
                    f"{artifact_context}"
                )
            pydantic_messages.append(ModelResponse(parts=[TextPart(content=content)]))

    return pydantic_messages


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _clamp_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _listing_mode(value: Any) -> ListingMode:
    return "sale" if str(value).lower() == "sale" else "rent"


def _message_requests_sale_inventory(message: str | None) -> bool:
    if not message:
        return False
    return bool(SALE_LISTING_INTENT_RE.search(message))


def _chart_area_inputs(args: dict[str, Any]) -> list[str]:
    raw_areas = args.get("areas")
    if isinstance(raw_areas, list):
        areas: list[str] = []
        seen: set[str] = set()
        for raw_item in raw_areas:
            area = " ".join(str(raw_item).strip().split())
            key = area.lower()
            if area and key not in seen:
                seen.add(key)
                areas.append(area)
            if len(areas) >= 5:
                break
        if len(areas) >= 2:
            return areas

    area = _clean_text(args.get("area"))
    return [area] if area else []


def _bedroom_values(args: dict[str, Any]) -> list[str] | None:
    exact = _clean_text(args.get("bedrooms"))
    if exact:
        return [exact.lower() if exact.lower() == "studio" else exact]

    min_bedrooms = _positive_int(args.get("bedrooms_min"))
    max_bedrooms = _positive_int(args.get("bedrooms_max"))
    if min_bedrooms is None and max_bedrooms is None:
        return None

    start = min_bedrooms if min_bedrooms is not None else 0
    end = max_bedrooms if max_bedrooms is not None else start
    if end < start:
        start, end = end, start
    return [str(value) for value in range(start, min(end, 10) + 1)]


def _artifact_shell(tool_name: str, tool_call_id: str, args: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    if tool_name == "show_listings":
        mode = _listing_mode(args.get("mode"))
        area = _clean_text(args.get("area"))
        title = "Rental listings" if mode == "rent" else "Sales listings"
        subtitle = area or "Dubai"
        return {
            "id": f"{tool_name}:{tool_call_id}",
            "type": "listing_results",
            "status": "loading",
            "title": title,
            "subtitle": subtitle,
            "created_at": now,
            "query": args,
        }
    if tool_name == "show_market_trend":
        area = _clean_text(args.get("area"))
        return {
            "id": f"{tool_name}:{tool_call_id}",
            "type": "market_trend",
            "status": "loading",
            "title": "Market trend",
            "subtitle": area or "Dubai market",
            "created_at": now,
            "query": args,
        }
    if tool_name == "show_chart":
        dataset = _clean_text(args.get("dataset")) or "sales"
        group_by = _clean_text(args.get("group_by")) or "area"
        metric = _clean_text(args.get("metric")) or "transaction_count"
        return {
            "id": f"{tool_name}:{tool_call_id}",
            "type": "custom_chart",
            "status": "loading",
            "title": _metric_label(metric),
            "subtitle": f"{dataset.title()} · {_dimension_label(group_by)}",
            "created_at": now,
            "query": args,
        }
    return {
        "id": f"{tool_name}:{tool_call_id}",
        "type": "unknown",
        "status": "loading",
        "title": tool_name.replace("_", " ").title(),
        "created_at": now,
        "query": args,
    }


async def _resolve_transaction_area(area: str | None) -> str | None:
    if not area:
        return None

    search_text = area_search_text(area)
    sql = """
    SELECT area_name_en
    FROM ch_transactions
    WHERE area_name_en != ''
      AND (
        lower(area_name_en) = lower({area:String})
        OR lower(area_name_en) = lower({search_text:String})
        OR area_name_en ILIKE {pattern:String}
        OR lower(master_project_en) = lower({search_text:String})
        OR master_project_en ILIKE {pattern:String}
        OR project_name_en ILIKE {pattern:String}
      )
      AND trans_group_en = 'Sales'
      AND actual_worth > 0
    GROUP BY area_name_en
    ORDER BY
        (lower(area_name_en) = lower({area:String})) DESC,
        (lower(area_name_en) = lower({search_text:String})) DESC,
        count() DESC
    LIMIT 1
    """
    rows = await ch_query(
        sql, {"area": area, "search_text": search_text, "pattern": f"%{search_text}%"}
    )
    return rows[0]["area_name_en"] if rows else area


async def _latest_transaction_date(
    *,
    property_usage: str | None,
    property_type: str | None,
    area: str | None,
    master_project: str | None = None,
) -> date | None:
    where_clauses = ["trans_group_en = 'Sales'", "actual_worth > 0", "instance_date IS NOT NULL"]
    params: dict[str, Any] = {}

    if property_usage:
        where_clauses.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if property_type:
        where_clauses.append("property_type_en = {property_type:String}")
        params["property_type"] = property_type
    if area:
        where_clauses.append("area_name_en = {area_name:String}")
        params["area_name"] = area
    if master_project:
        where_clauses.append("master_project_en = {master_project:String}")
        params["master_project"] = master_project

    rows = await ch_query(
        f"""
        SELECT max(instance_date) AS max_date
        FROM ch_transactions
        WHERE {" AND ".join(where_clauses)}
        """,
        params,
    )
    if not rows:
        return None

    max_date = rows[0].get("max_date")
    if isinstance(max_date, date):
        return max_date
    if isinstance(max_date, str):
        try:
            return date.fromisoformat(max_date)
        except ValueError:
            return None
    return None


async def _latest_rental_contract_date(
    *,
    property_usage: str | None,
    property_type: str | None,
    area: str | None,
    master_project: str | None = None,
) -> date | None:
    where_clauses = [
        "annual_amount > 0",
        "contract_start_date IS NOT NULL",
        "contract_start_date <= today()",
    ]
    params: dict[str, Any] = {}

    if property_usage:
        where_clauses.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if property_type:
        where_clauses.append("ejari_property_type_en = {property_type:String}")
        params["property_type"] = property_type
    if area:
        where_clauses.append("area_name_en = {area_name:String}")
        params["area_name"] = area
    if master_project:
        where_clauses.append("master_project_en = {master_project:String}")
        params["master_project"] = master_project

    rows = await ch_query(
        f"""
        SELECT max(contract_start_date) AS max_date
        FROM ch_rent_contracts
        WHERE {" AND ".join(where_clauses)}
        """,
        params,
    )
    if not rows:
        return None

    max_date = rows[0].get("max_date")
    if isinstance(max_date, date):
        return max_date
    if isinstance(max_date, str):
        try:
            return date.fromisoformat(max_date)
        except ValueError:
            return None
    return None


async def _resolve_transaction_scope(area: str | None) -> dict[str, str | None]:
    if not area:
        return {"label": None, "area": None, "master_project": None}

    search_text = area_search_text(area)
    master_rows = await ch_query(
        """
        SELECT master_project_en
        FROM ch_transactions
        WHERE master_project_en != ''
          AND lower(master_project_en) = lower({search_text:String})
          AND trans_group_en = 'Sales'
          AND actual_worth > 0
        GROUP BY master_project_en
        ORDER BY count() DESC
        LIMIT 1
        """,
        {"search_text": search_text},
    )
    if master_rows:
        master_project = str(master_rows[0]["master_project_en"])
        return {"label": master_project, "area": None, "master_project": master_project}

    resolved_area = await _resolve_transaction_area(area)
    return {"label": resolved_area, "area": resolved_area, "master_project": None}


async def _resolve_fact_area(area: str | None) -> str | None:
    if not area:
        return None

    search_text = area_search_text(area)
    rows = await ch_query(
        """
        SELECT area_name_en
        FROM ch_area_fact
        WHERE area_name_en != ''
          AND (
            lower(area_name_en) = lower({area:String})
            OR lower(area_name_en) = lower({search_text:String})
            OR positionCaseInsensitive(area_name_en, {search_text:String}) > 0
            OR arrayExists(
                project -> positionCaseInsensitive(project, {search_text:String}) > 0,
                top_master_projects
            )
          )
        ORDER BY
            (lower(area_name_en) = lower({area:String})) DESC,
            (lower(area_name_en) = lower({search_text:String})) DESC,
            sales_transaction_count_12m DESC,
            pipeline_units DESC,
            area_name_en ASC
        LIMIT 1
        """,
        {"area": area, "search_text": search_text},
    )
    return str(rows[0]["area_name_en"]) if rows else search_text


def _trend_interval(days: int) -> str:
    if days <= DAILY_INTERVAL_MAX_DAYS:
        return "day"
    if days <= WEEKLY_INTERVAL_MAX_DAYS:
        return "week"
    return "month"


def _chart_days(value: Any) -> int:
    return _clamp_int(
        value,
        default=DEFAULT_CHART_DAYS,
        min_value=MIN_CHART_DAYS,
        max_value=MAX_CHART_DAYS,
    )


def _chart_type(value: Any, group_by: str) -> str:
    requested = str(value or "").lower().replace("-", "_")
    if requested in {"donut", "doughnut", "pie"}:
        return "doughnut"
    if requested in {"horizontal_bar", "bar_horizontal"}:
        return "horizontal_bar"
    if requested in {"line", "area"}:
        return "line"
    if group_by == "time":
        return "line"
    if requested == "bar":
        return "bar"
    return "horizontal_bar"


def _chart_sort_direction(value: Any) -> str:
    requested = str(value or "").lower().strip()
    if requested in {"asc", "ascending", "bottom", "lowest", "least", "cheap", "cheapest"}:
        return "asc"
    return "desc"


def _chart_order_clause(sort_direction: str, *, limit_key: str) -> str:
    if sort_direction == "asc":
        return f"ORDER BY value ASC LIMIT {{{limit_key}:Int32}}"
    return f"ORDER BY value DESC LIMIT {{{limit_key}:Int32}}"


def _chart_min_records(args: dict[str, Any], *, group_by: str, metric: str) -> int:
    default = (
        25
        if group_by == "area"
        and metric
        in {
            "avg_price",
            "median_price",
            "avg_price_sqm",
            "median_price_sqm",
            "avg_price_sqft",
            "median_price_sqft",
            "avg_rent",
            "median_rent",
            "median_rent_sqm",
            "median_rent_sqft",
        }
        else 1
    )
    return _clamp_int(args.get("min_records"), default=default, min_value=1, max_value=10_000)


def _metric_label(metric: str) -> str:
    labels = {
        "transaction_count": "Transactions",
        "contract_count": "Contracts",
        "project_count": "Projects",
        "active_projects": "Active projects",
        "completed_projects": "Completed projects",
        "total_volume": "Total value",
        "total_annual_value": "Total annual rent",
        "total_sales_volume_12m": "12m sales value",
        "avg_price": "Average price",
        "median_price": "Median price",
        "avg_price_sqm": "Average price / sqm",
        "median_price_sqm": "Median price / sqm",
        "avg_price_sqft": "Average price / sqft",
        "median_price_sqft": "Median price / sqft",
        "avg_rent": "Average rent",
        "median_rent": "Median rent",
        "median_rent_sqm": "Median rent / sqm",
        "median_rent_sqft": "Median rent / sqft",
        "pipeline_units": "Pipeline units",
        "units_delivering_next_12_months": "Units delivering next 12m",
        "sales_transaction_count_12m": "12m sales transactions",
        "rental_contract_count_12m": "12m rental contracts",
        "gross_yield_pct": "Gross yield",
        "avg_completion_pct": "Average completion",
    }
    return labels.get(metric, metric.replace("_", " ").title())


def _dimension_label(group_by: str) -> str:
    labels = {
        "time": "Time",
        "area": "Area",
        "property_type": "Property type",
        "bedrooms": "Bedrooms",
        "project": "Project",
        "master_project": "Master project",
        "transaction_type": "Transaction type",
        "tenant_type": "Tenant type",
        "developer": "Developer",
        "completion_status": "Completion status",
        "pipeline_status": "Pipeline status",
    }
    return labels.get(group_by, group_by.replace("_", " ").title())


def _chart_points(rows: list[dict[str, Any]], *, time_series: bool) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        raw_label = row.get("label")
        if raw_label is None or raw_label == "":
            raw_label = "Unknown"
        value = float(row.get("value") or 0)
        point = {
            "label": str(raw_label),
            "value": value,
            "record_count": _clamp_int(
                row.get("record_count"), default=0, min_value=0, max_value=10_000_000
            ),
        }
        if time_series:
            point["date"] = str(raw_label)
        points.append(point)
    return points


def _chart_summary(
    points: list[dict[str, Any]], *, period_start: date | None, period_end: date | None
) -> dict[str, Any]:
    return {
        "point_count": len(points),
        "total_records": sum(int(point.get("record_count") or 0) for point in points),
        "period_start": str(period_start) if period_start else None,
        "period_end": str(period_end) if period_end else None,
    }


def _chart_series_summary(
    series: list[dict[str, Any]], *, period_start: date | None, period_end: date | None
) -> dict[str, Any]:
    points = [
        point
        for series_item in series
        for point in series_item.get("points", [])
        if isinstance(point, dict)
    ]
    return _chart_summary(points, period_start=period_start, period_end=period_end)


def _scope_clauses(scope: dict[str, str | None], params: dict[str, Any], prefix: str) -> list[str]:
    clauses: list[str] = []
    if scope.get("area"):
        key = f"{prefix}_area"
        params[key] = scope["area"]
        clauses.append(f"area_name_en = {{{key}:String}}")
    if scope.get("master_project"):
        key = f"{prefix}_master_project"
        params[key] = scope["master_project"]
        clauses.append(f"master_project_en = {{{key}:String}}")
    return clauses


def _scope_filter_and_label_expr(
    scopes: list[dict[str, str | None]], params: dict[str, Any], prefix: str
) -> tuple[str | None, str | None]:
    filters: list[str] = []
    label_expr_parts: list[str] = []
    for index, scope in enumerate(scopes):
        scope_prefix = f"{prefix}_{index}"
        clauses = _scope_clauses(scope, params, scope_prefix)
        label = scope.get("label")
        if not clauses or not label:
            continue

        condition = "(" + " OR ".join(clauses) + ")"
        label_key = f"{scope_prefix}_label"
        params[label_key] = label
        filters.append(condition)
        label_expr_parts.extend([condition, f"{{{label_key}:String}}"])

    if not filters:
        return None, None
    return "(" + " OR ".join(filters) + ")", f"multiIf({', '.join(label_expr_parts)}, 'Other')"


async def _resolve_transaction_scopes(area_inputs: list[str]) -> list[dict[str, str | None]]:
    scopes: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for area in area_inputs:
        scope = await _resolve_transaction_scope(area)
        key = (scope.get("area"), scope.get("master_project"), scope.get("label"))
        if scope.get("label") and key not in seen:
            scopes.append(scope)
            seen.add(key)
    return scopes


async def _latest_transaction_date_for_scopes(
    *,
    property_usage: str | None,
    property_type: str | None,
    scopes: list[dict[str, str | None]],
) -> date | None:
    where_clauses = ["trans_group_en = 'Sales'", "actual_worth > 0", "instance_date IS NOT NULL"]
    params: dict[str, Any] = {}

    if property_usage:
        where_clauses.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if property_type:
        where_clauses.append("property_type_en = {property_type:String}")
        params["property_type"] = property_type

    scope_filter, _ = _scope_filter_and_label_expr(scopes, params, "scope")
    if scope_filter:
        where_clauses.append(scope_filter)

    rows = await ch_query(
        f"""
        SELECT max(instance_date) AS max_date
        FROM ch_transactions
        WHERE {" AND ".join(where_clauses)}
        """,
        params,
    )
    if not rows:
        return None

    max_date = rows[0].get("max_date")
    if isinstance(max_date, date):
        return max_date
    if isinstance(max_date, str):
        try:
            return date.fromisoformat(max_date)
        except ValueError:
            return None
    return None


async def _latest_rental_contract_date_for_scopes(
    *,
    property_usage: str | None,
    property_type: str | None,
    scopes: list[dict[str, str | None]],
) -> date | None:
    where_clauses = [
        "annual_amount > 0",
        "contract_start_date IS NOT NULL",
        "contract_start_date <= today()",
    ]
    params: dict[str, Any] = {}

    if property_usage:
        where_clauses.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if property_type:
        where_clauses.append("ejari_property_type_en = {property_type:String}")
        params["property_type"] = property_type

    scope_filter, _ = _scope_filter_and_label_expr(scopes, params, "scope")
    if scope_filter:
        where_clauses.append(scope_filter)

    rows = await ch_query(
        f"""
        SELECT max(contract_start_date) AS max_date
        FROM ch_rent_contracts
        WHERE {" AND ".join(where_clauses)}
        """,
        params,
    )
    if not rows:
        return None

    max_date = rows[0].get("max_date")
    if isinstance(max_date, date):
        return max_date
    if isinstance(max_date, str):
        try:
            return date.fromisoformat(max_date)
        except ValueError:
            return None
    return None


def _chart_series(
    rows: list[dict[str, Any]], *, time_series: bool, series_order: list[str]
) -> list[dict[str, Any]]:
    points_by_series = {label: [] for label in series_order}
    for row in rows:
        label = str(row.get("series_label") or "Other")
        points_by_series.setdefault(label, [])
        points_by_series[label].extend(_chart_points([row], time_series=time_series))

    return [
        {"label": label, "points": points} for label, points in points_by_series.items() if points
    ]


def _flatten_chart_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        point
        for series_item in series
        for point in series_item.get("points", [])
        if isinstance(point, dict)
    ]


def _listing_subtitle(args: dict[str, Any], total: int) -> str:
    parts: list[str] = []
    area = _clean_text(args.get("area"))
    if area:
        parts.append(area)
    bedrooms = _bedroom_values(args)
    if bedrooms:
        parts.append(f"{'-'.join(bedrooms)} bed" if len(bedrooms) > 1 else f"{bedrooms[0]} bed")
    price_min = _positive_int(args.get("price_min"))
    price_max = _positive_int(args.get("price_max"))
    if price_min is not None or price_max is not None:
        low = f"AED {price_min:,}" if price_min is not None else "Any"
        high = f"AED {price_max:,}" if price_max is not None else "Any"
        suffix = "/mo" if args.get("price_basis") == "monthly" else ""
        parts.append(f"{low}-{high}{suffix}")
    parts.append(f"{total:,} matches")
    return " · ".join(parts)


async def _resolve_listing_area(
    db: AsyncSession, mode: ListingMode, area: str | None
) -> str | None:
    del db
    if not area:
        return None

    terms = listing_area_terms(area)
    params: dict[str, Any] = {
        "category_ids": [2, 4] if mode == "rent" else [1, 3],
        "area": area,
        "primary": terms[0],
    }
    match_clauses = []
    for index, term in enumerate(terms):
        term_key = f"area_term_{index}"
        params[term_key] = term
        match_clauses.append(
            f"""
            lower(area_name) = lower({{{term_key}:String}})
            OR positionCaseInsensitive(listing_location_names_json, {{{term_key}:String}}) > 0
            """
        )

    rows = await ch_query(
        f"""
        SELECT JSONExtract(listing_location_names_json, 'Array(String)')[2] AS area_name
        FROM pf_listings_bronze
        WHERE category_id IN {{category_ids:Array(UInt16)}}
          AND is_available = 1
          AND area_name != ''
          AND ({" OR ".join(f"({clause})" for clause in match_clauses)})
        GROUP BY area_name
        ORDER BY
            (lower(area_name) = lower({{area:String}})) DESC,
            (lower(area_name) = lower({{primary:String}})) DESC,
            count() DESC,
            area_name ASC
        LIMIT 1
        """,
        params,
    )
    return rows[0]["area_name"] if rows else area


async def _fetch_listing_artifact(
    db: AsyncSession,
    artifact: dict[str, Any],
    args: dict[str, Any],
    user_message: str | None = None,
) -> dict[str, Any]:
    mode = _listing_mode(args.get("mode"))
    requested_mode = mode
    if mode == "sale" and not _message_requests_sale_inventory(user_message):
        mode = "rent"
    limit = _clamp_int(args.get("limit"), default=12, min_value=1, max_value=24)
    price_basis = "monthly" if str(args.get("price_basis")).lower() == "monthly" else "raw"
    price_period = _clean_text(args.get("price_period"))
    raw_area = _clean_text(args.get("area"))
    property_type = _clean_text(args.get("property_type"))
    bedrooms = _bedroom_values(args)
    price_min = _positive_int(args.get("price_min"))
    price_max = _positive_int(args.get("price_max"))

    async def load_for_mode(next_mode: ListingMode):
        resolved_area = await _resolve_listing_area(db, next_mode, raw_area)
        result = await list_listings_from_clickhouse(
            mode=next_mode,
            limit=limit,
            offset=0,
            area=resolved_area,
            property_type=property_type,
            bedrooms_in=bedrooms,
            price_min=price_min,
            price_max=price_max,
            price_period=price_period,
            price_basis=price_basis,
        )
        return resolved_area, result

    area, listings = await load_for_mode(mode)
    fallback_from_mode: ListingMode | None = None
    if requested_mode != mode:
        fallback_from_mode = requested_mode

    payload = listings.model_dump(mode="json")
    subtitle_args = {**args, "area": area, "mode": mode}
    title = "Rental listings" if mode == "rent" else "Sales listings"
    return {
        **artifact,
        "status": "ready",
        "title": title,
        "subtitle": _listing_subtitle(subtitle_args, listings.total),
        "query": {
            "mode": mode,
            "area": area,
            "property_type": property_type,
            "bedrooms": bedrooms,
            "price_min": price_min,
            "price_max": price_max,
            "price_basis": price_basis,
            "limit": limit,
            "fallback_from_mode": fallback_from_mode,
        },
        "data": payload,
    }


async def _fetch_market_trend_artifact(
    artifact: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    days = _chart_days(args.get("days"))
    interval = _trend_interval(days)
    property_usage = _clean_text(args.get("property_usage")) or "Residential"
    property_type = _clean_text(args.get("property_type"))
    area = await _resolve_transaction_area(_clean_text(args.get("area")))
    end_date = (
        await _latest_transaction_date(
            property_usage=property_usage,
            property_type=property_type,
            area=area,
        )
        or date.today()
    )
    start_date = end_date - timedelta(days=days)

    sql = price_trends(
        property_usage=property_usage,
        property_type=property_type,
        area_name=area,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        interval=interval,
    )
    params: dict[str, Any] = {
        "property_usage": property_usage,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if property_type:
        params["property_type"] = property_type
    if area:
        params["area_name"] = area

    rows = await ch_query(sql, params)
    points = [
        {
            "date": str(row["period"]),
            "transaction_count": int(row["transaction_count"]),
            "avg_price": float(row["avg_price"] or 0),
            "avg_price_sqm": float(row["avg_price_sqm"] or 0),
        }
        for row in rows
    ]
    first = next((point for point in points if point["avg_price_sqm"] > 0), None)
    last = next((point for point in reversed(points) if point["avg_price_sqm"] > 0), None)
    change_pct = (
        round((last["avg_price_sqm"] - first["avg_price_sqm"]) / first["avg_price_sqm"] * 100, 1)
        if first and last and first["avg_price_sqm"]
        else None
    )
    total_transactions = sum(point["transaction_count"] for point in points)
    return {
        **artifact,
        "status": "ready",
        "subtitle": f"{area or 'Dubai market'} · {days} days · {total_transactions:,} transactions",
        "query": {
            "area": area,
            "property_usage": property_usage,
            "property_type": property_type,
            "days": days,
            "interval": interval,
        },
        "data": {
            "data": points,
            "total_transactions": total_transactions,
            "avg_price_sqm_change_pct": change_pct,
        },
    }


def _optional_chart_filter(value: Any) -> str | None:
    text_value = _clean_text(value)
    if not text_value or text_value.lower() in {"all", "any", "none"}:
        return None
    return text_value


def _rental_property_type(value: Any) -> str | None:
    property_type = _optional_chart_filter(value)
    if not property_type:
        return None
    normalized = property_type.lower()
    if normalized in {"unit", "apartment", "apartments", "flat", "flats"}:
        return "Flat"
    if normalized in {"villa", "villas"}:
        return "Villa"
    return property_type


def _sales_property_type(value: Any) -> str | None:
    property_type = _optional_chart_filter(value)
    if not property_type:
        return None
    normalized = property_type.lower()
    if normalized in {"unit", "apartment", "apartments", "flat", "flats"}:
        return "Unit"
    if normalized in {"villa", "villas"}:
        return "Villa"
    return property_type


async def _fetch_sales_chart_artifact(
    artifact: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    days = _chart_days(args.get("days"))
    limit = _clamp_int(args.get("limit"), default=8, min_value=1, max_value=20)
    group_by = str(args.get("group_by") or "area").lower()
    metric = str(args.get("metric") or "transaction_count").lower()
    sort_direction = _chart_sort_direction(args.get("sort_direction"))
    property_usage = _optional_chart_filter(args.get("property_usage")) or "Residential"
    property_type = _sales_property_type(args.get("property_type"))
    area_inputs = _chart_area_inputs(args)
    scopes = await _resolve_transaction_scopes(area_inputs) if len(area_inputs) > 1 else []
    is_multi_area = len(scopes) > 1
    scope = (
        {"label": None, "area": None, "master_project": None}
        if is_multi_area
        else await _resolve_transaction_scope(area_inputs[0] if area_inputs else None)
    )
    area = scope["area"]
    master_project = scope["master_project"]
    scope_label = scope["label"]

    group_exprs = {
        "time": None,
        "area": "area_name_en",
        "property_type": "property_type_en",
        "bedrooms": "rooms_en",
        "project": "project_name_en",
        "master_project": "master_project_en",
        "transaction_type": "reg_type_en",
    }
    if group_by not in group_exprs:
        group_by = "area"

    metric_exprs = {
        "transaction_count": "count()",
        "total_volume": "round(sum(actual_worth), 0)",
        "avg_price": "round(avg(actual_worth), 0)",
        "median_price": "round(median(actual_worth), 0)",
        "avg_price_sqm": "round(avg(meter_sale_price), 0)",
        "median_price_sqm": "round(median(meter_sale_price), 0)",
        "avg_price_sqft": f"round(avg(meter_sale_price) / {SQM_TO_SQFT}, 0)",
        "median_price_sqft": f"round(median(meter_sale_price) / {SQM_TO_SQFT}, 0)",
    }
    if metric not in metric_exprs:
        metric = "transaction_count"
    min_records = _chart_min_records(args, group_by=group_by, metric=metric)

    if is_multi_area:
        end_date = (
            await _latest_transaction_date_for_scopes(
                property_usage=property_usage,
                property_type=property_type,
                scopes=scopes,
            )
            or date.today()
        )
    else:
        end_date = (
            await _latest_transaction_date(
                property_usage=property_usage,
                property_type=property_type,
                area=area,
                master_project=master_project,
            )
            or date.today()
        )
    start_date = end_date - timedelta(days=days)
    interval = _trend_interval(days)
    params: dict[str, Any] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "limit": limit,
        "series_limit": limit * max(len(scopes), 1),
        "min_records": min_records,
    }
    scope_filter = None
    scope_label_expr = None
    if is_multi_area:
        scope_filter, scope_label_expr = _scope_filter_and_label_expr(scopes, params, "scope")

    if group_by == "time":
        if interval == "day":
            label_expr = "instance_date"
        elif interval == "week":
            label_expr = "toStartOfWeek(instance_date)"
        else:
            label_expr = "toStartOfMonth(instance_date)"
    elif is_multi_area and group_by == "area" and scope_label_expr:
        label_expr = scope_label_expr
    else:
        label_expr = group_exprs[group_by]

    where = [
        "trans_group_en = 'Sales'",
        "actual_worth > 0",
        "instance_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]
    if property_usage:
        where.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if property_type:
        where.append("property_type_en = {property_type:String}")
        params["property_type"] = property_type
    if is_multi_area and scope_filter:
        where.append(scope_filter)
    if not is_multi_area and area:
        where.append("area_name_en = {area_name:String}")
        params["area_name"] = area
    if not is_multi_area and master_project:
        where.append("master_project_en = {master_project:String}")
        params["master_project"] = master_project
    if group_by != "time" and label_expr:
        where.append(f"{label_expr} != ''")

    if is_multi_area and group_by != "area" and scope_label_expr:
        order_limit = (
            "ORDER BY series_label ASC, label ASC"
            if group_by == "time"
            else _chart_order_clause(sort_direction, limit_key="series_limit")
        )
        rows = await ch_query(
            f"""
            SELECT
                {scope_label_expr} AS series_label,
                {label_expr} AS label,
                {metric_exprs[metric]} AS value,
                count() AS record_count
            FROM ch_transactions
            WHERE {" AND ".join(where)}
            GROUP BY series_label, label
            HAVING value > 0 AND record_count >= {{min_records:Int32}}
            {order_limit}
            """,
            params,
        )
        series = _chart_series(
            rows,
            time_series=group_by == "time",
            series_order=[str(scope["label"]) for scope in scopes if scope.get("label")],
        )
        points = _flatten_chart_series(series)
    else:
        order_limit = (
            "ORDER BY label ASC"
            if group_by == "time"
            else _chart_order_clause(sort_direction, limit_key="limit")
        )
        rows = await ch_query(
            f"""
            SELECT
                {label_expr} AS label,
                {metric_exprs[metric]} AS value,
                count() AS record_count
            FROM ch_transactions
            WHERE {" AND ".join(where)}
            GROUP BY label
            HAVING value > 0 AND record_count >= {{min_records:Int32}}
            {order_limit}
            """,
            params,
        )
        series = []
        points = _chart_points(rows, time_series=group_by == "time")
    chart_type = _chart_type(args.get("chart_type"), group_by)
    if series and chart_type == "doughnut":
        chart_type = "line" if group_by == "time" else "bar"
    scope_title = (
        ", ".join(str(scope["label"]) for scope in scopes) if is_multi_area else scope_label
    )
    return {
        **artifact,
        "status": "ready",
        "title": _metric_label(metric),
        "subtitle": f"Sales · {_dimension_label(group_by)} · {scope_title or 'Dubai'}",
        "query": {
            "dataset": "sales",
            "chart_type": chart_type,
            "group_by": group_by,
            "metric": metric,
            "area": scope_label,
            "areas": [scope["label"] for scope in scopes] if is_multi_area else [],
            "sort_direction": sort_direction,
            "min_records": min_records,
            "area_name": area,
            "master_project": master_project,
            "property_usage": property_usage,
            "property_type": property_type,
            "days": days,
            "interval": interval,
            "limit": limit,
        },
        "data": {
            "chart_type": chart_type,
            "metric": metric,
            "metric_label": _metric_label(metric),
            "dimension": group_by,
            "dimension_label": _dimension_label(group_by),
            "data_source": "DLD sales transactions",
            "sort_direction": sort_direction,
            "points": points,
            "series": series,
            "summary": (
                _chart_series_summary(series, period_start=start_date, period_end=end_date)
                if series
                else _chart_summary(points, period_start=start_date, period_end=end_date)
            ),
        },
    }


async def _fetch_rental_chart_artifact(
    artifact: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    days = _chart_days(args.get("days"))
    limit = _clamp_int(args.get("limit"), default=8, min_value=1, max_value=20)
    group_by = str(args.get("group_by") or "area").lower()
    metric = str(args.get("metric") or "contract_count").lower()
    sort_direction = _chart_sort_direction(args.get("sort_direction"))
    property_usage = _optional_chart_filter(args.get("property_usage")) or "Residential"
    property_type = _rental_property_type(args.get("property_type"))
    area_inputs = _chart_area_inputs(args)
    scopes = await _resolve_transaction_scopes(area_inputs) if len(area_inputs) > 1 else []
    is_multi_area = len(scopes) > 1
    scope = (
        {"label": None, "area": None, "master_project": None}
        if is_multi_area
        else await _resolve_transaction_scope(area_inputs[0] if area_inputs else None)
    )
    area = scope["area"]
    master_project = scope["master_project"]
    scope_label = scope["label"]

    group_exprs = {
        "time": None,
        "area": "area_name_en",
        "property_type": "ejari_property_type_en",
        "project": "project_name_en",
        "master_project": "master_project_en",
        "tenant_type": "tenant_type_en",
    }
    if group_by not in group_exprs:
        group_by = "area"

    metric_exprs = {
        "contract_count": "count()",
        "total_annual_value": "round(sum(annual_amount), 0)",
        "avg_rent": "round(avg(annual_amount), 0)",
        "median_rent": "round(median(annual_amount), 0)",
        "median_rent_sqm": "round(median(annual_amount / nullIf(actual_area, 0)), 0)",
        "median_rent_sqft": f"round(median(annual_amount / nullIf(actual_area, 0)) / {SQM_TO_SQFT}, 0)",
    }
    if metric not in metric_exprs:
        metric = "contract_count"
    min_records = _chart_min_records(args, group_by=group_by, metric=metric)

    if is_multi_area:
        end_date = (
            await _latest_rental_contract_date_for_scopes(
                property_usage=property_usage,
                property_type=property_type,
                scopes=scopes,
            )
            or date.today()
        )
    else:
        end_date = (
            await _latest_rental_contract_date(
                property_usage=property_usage,
                property_type=property_type,
                area=area,
                master_project=master_project,
            )
            or date.today()
        )
    start_date = end_date - timedelta(days=days)
    interval = _trend_interval(days)
    params: dict[str, Any] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "limit": limit,
        "series_limit": limit * max(len(scopes), 1),
        "min_records": min_records,
    }
    scope_filter = None
    scope_label_expr = None
    if is_multi_area:
        scope_filter, scope_label_expr = _scope_filter_and_label_expr(scopes, params, "scope")

    if group_by == "time":
        if interval == "day":
            label_expr = "contract_start_date"
        elif interval == "week":
            label_expr = "toStartOfWeek(contract_start_date)"
        else:
            label_expr = "toStartOfMonth(contract_start_date)"
    elif is_multi_area and group_by == "area" and scope_label_expr:
        label_expr = scope_label_expr
    else:
        label_expr = group_exprs[group_by]

    where = [
        "annual_amount > 0",
        "contract_start_date <= today()",
        "contract_start_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]
    if property_usage:
        where.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if property_type:
        where.append("ejari_property_type_en = {property_type:String}")
        params["property_type"] = property_type
    if is_multi_area and scope_filter:
        where.append(scope_filter)
    if not is_multi_area and area:
        where.append("area_name_en = {area_name:String}")
        params["area_name"] = area
    if not is_multi_area and master_project:
        where.append("master_project_en = {master_project:String}")
        params["master_project"] = master_project
    if group_by != "time" and label_expr:
        where.append(f"{label_expr} != ''")

    if is_multi_area and group_by != "area" and scope_label_expr:
        order_limit = (
            "ORDER BY series_label ASC, label ASC"
            if group_by == "time"
            else _chart_order_clause(sort_direction, limit_key="series_limit")
        )
        rows = await ch_query(
            f"""
            SELECT
                {scope_label_expr} AS series_label,
                {label_expr} AS label,
                {metric_exprs[metric]} AS value,
                count() AS record_count
            FROM ch_rent_contracts
            WHERE {" AND ".join(where)}
            GROUP BY series_label, label
            HAVING value > 0 AND record_count >= {{min_records:Int32}}
            {order_limit}
            """,
            params,
        )
        series = _chart_series(
            rows,
            time_series=group_by == "time",
            series_order=[str(scope["label"]) for scope in scopes if scope.get("label")],
        )
        points = _flatten_chart_series(series)
    else:
        order_limit = (
            "ORDER BY label ASC"
            if group_by == "time"
            else _chart_order_clause(sort_direction, limit_key="limit")
        )
        rows = await ch_query(
            f"""
            SELECT
                {label_expr} AS label,
                {metric_exprs[metric]} AS value,
                count() AS record_count
            FROM ch_rent_contracts
            WHERE {" AND ".join(where)}
            GROUP BY label
            HAVING value > 0 AND record_count >= {{min_records:Int32}}
            {order_limit}
            """,
            params,
        )
        series = []
        points = _chart_points(rows, time_series=group_by == "time")
    chart_type = _chart_type(args.get("chart_type"), group_by)
    if series and chart_type == "doughnut":
        chart_type = "line" if group_by == "time" else "bar"
    scope_title = (
        ", ".join(str(scope["label"]) for scope in scopes) if is_multi_area else scope_label
    )
    return {
        **artifact,
        "status": "ready",
        "title": _metric_label(metric),
        "subtitle": f"Rentals · {_dimension_label(group_by)} · {scope_title or 'Dubai'}",
        "query": {
            "dataset": "rentals",
            "chart_type": chart_type,
            "group_by": group_by,
            "metric": metric,
            "area": scope_label,
            "areas": [scope["label"] for scope in scopes] if is_multi_area else [],
            "sort_direction": sort_direction,
            "min_records": min_records,
            "area_name": area,
            "master_project": master_project,
            "property_usage": property_usage,
            "property_type": property_type,
            "days": days,
            "interval": interval,
            "limit": limit,
        },
        "data": {
            "chart_type": chart_type,
            "metric": metric,
            "metric_label": _metric_label(metric),
            "dimension": group_by,
            "dimension_label": _dimension_label(group_by),
            "data_source": "DLD Ejari rental contracts",
            "sort_direction": sort_direction,
            "points": points,
            "series": series,
            "summary": (
                _chart_series_summary(series, period_start=start_date, period_end=end_date)
                if series
                else _chart_summary(points, period_start=start_date, period_end=end_date)
            ),
        },
    }


async def _fetch_project_chart_artifact(
    artifact: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    limit = _clamp_int(args.get("limit"), default=8, min_value=1, max_value=20)
    group_by = str(args.get("group_by") or "area").lower()
    metric = str(args.get("metric") or "pipeline_units").lower()
    sort_direction = _chart_sort_direction(args.get("sort_direction"))
    area_inputs = _chart_area_inputs(args)
    areas: list[str] = []
    seen_areas: set[str] = set()
    for area_input in area_inputs:
        resolved_area = await _resolve_fact_area(area_input)
        key = (resolved_area or "").lower()
        if resolved_area and key not in seen_areas:
            areas.append(resolved_area)
            seen_areas.add(key)
    is_multi_area = len(areas) > 1
    area = None if is_multi_area else (areas[0] if areas else None)

    group_exprs = {
        "area": "area_name_en",
        "developer": "developer_name",
        "completion_status": "completion_status",
        "pipeline_status": "pipeline_status",
        "master_project": "master_project_en",
    }
    if group_by not in group_exprs:
        group_by = "area"

    metric_exprs = {
        "project_count": "count()",
        "active_projects": "countIf(completion_status != 'FINISHED')",
        "completed_projects": "countIf(completion_status = 'FINISHED')",
        "pipeline_units": "sum(no_of_units)",
        "units_delivering_next_12_months": (
            "sumIf(no_of_units, pipeline_status = 'delivering_next_12_months' "
            "AND completion_status != 'FINISHED')"
        ),
        "sales_transaction_count_12m": "sum(sales_transaction_count_12m)",
        "rental_contract_count_12m": "sum(rental_contract_count_12m)",
        "total_sales_volume_12m": "round(sum(total_sales_volume_12m), 0)",
        "gross_yield_pct": "round(avg(gross_yield_pct), 2)",
        "avg_completion_pct": "round(avg(percent_completed), 1)",
    }
    if metric not in metric_exprs:
        metric = "pipeline_units"
    min_records = _chart_min_records(args, group_by=group_by, metric=metric)

    label_expr = group_exprs[group_by]
    where = [f"{label_expr} != ''"]
    params: dict[str, Any] = {
        "limit": limit,
        "series_limit": limit * max(len(areas), 1),
        "min_records": min_records,
    }
    if is_multi_area:
        where.append("area_name_en IN {areas:Array(String)}")
        params["areas"] = areas
    elif area:
        where.append("area_name_en = {area_name:String}")
        params["area_name"] = area

    if is_multi_area and group_by != "area":
        rows = await ch_query(
            f"""
            SELECT
                area_name_en AS series_label,
                {label_expr} AS label,
                {metric_exprs[metric]} AS value,
                count() AS record_count
            FROM ch_project_fact
            WHERE {" AND ".join(where)}
            GROUP BY series_label, label
            HAVING value > 0 AND record_count >= {{min_records:Int32}}
            {_chart_order_clause(sort_direction, limit_key="series_limit")}
            """,
            params,
        )
        series = _chart_series(rows, time_series=False, series_order=areas)
        points = _flatten_chart_series(series)
    else:
        rows = await ch_query(
            f"""
            SELECT
                {label_expr} AS label,
                {metric_exprs[metric]} AS value,
                count() AS record_count
            FROM ch_project_fact
            WHERE {" AND ".join(where)}
            GROUP BY label
            HAVING value > 0 AND record_count >= {{min_records:Int32}}
            {_chart_order_clause(sort_direction, limit_key="limit")}
            """,
            params,
        )
        series = []
        points = _chart_points(rows, time_series=False)
    chart_type = _chart_type(args.get("chart_type"), group_by)
    if series and chart_type == "doughnut":
        chart_type = "bar"
    scope_title = ", ".join(areas) if is_multi_area else area
    return {
        **artifact,
        "status": "ready",
        "title": _metric_label(metric),
        "subtitle": f"Projects · {_dimension_label(group_by)} · {scope_title or 'Dubai'}",
        "query": {
            "dataset": "projects",
            "chart_type": chart_type,
            "group_by": group_by,
            "metric": metric,
            "area": area,
            "areas": areas if is_multi_area else [],
            "sort_direction": sort_direction,
            "min_records": min_records,
            "limit": limit,
        },
        "data": {
            "chart_type": chart_type,
            "metric": metric,
            "metric_label": _metric_label(metric),
            "dimension": group_by,
            "dimension_label": _dimension_label(group_by),
            "data_source": "DLD project registry and 12-month market facts",
            "sort_direction": sort_direction,
            "points": points,
            "series": series,
            "summary": (
                _chart_series_summary(series, period_start=None, period_end=None)
                if series
                else _chart_summary(points, period_start=None, period_end=None)
            ),
        },
    }


async def _fetch_area_yield_chart_artifact(
    artifact: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    days = _chart_days(args.get("days"))
    limit = _clamp_int(args.get("limit"), default=8, min_value=1, max_value=20)
    sort_direction = _chart_sort_direction(args.get("sort_direction"))
    min_records = _clamp_int(args.get("min_records"), default=250, min_value=1, max_value=10_000)
    property_usage = _optional_chart_filter(args.get("property_usage")) or "Residential"
    raw_property_type = _clean_text(args.get("property_type")) or ""
    if raw_property_type.lower() in {"all", "any", "none"}:
        yield_property_type = None
    else:
        yield_property_type = raw_property_type or "Flat"
    sales_property_type = _sales_property_type(yield_property_type)
    rental_property_type = _rental_property_type(yield_property_type)

    latest_sales_date = await _latest_transaction_date(
        property_usage=property_usage,
        property_type=sales_property_type,
        area=None,
    )
    latest_rental_date = await _latest_rental_contract_date(
        property_usage=property_usage,
        property_type=rental_property_type,
        area=None,
    )
    latest_dates = [value for value in [latest_sales_date, latest_rental_date] if value]
    end_date = min(latest_dates) if latest_dates else date.today()
    start_date = end_date - timedelta(days=days)

    sales_where = [
        "trans_group_en = 'Sales'",
        "actual_worth > 0",
        "area_name_en != ''",
        "lower(area_name_en) != 'unknown'",
        "instance_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]
    rental_where = [
        "annual_amount > 0",
        "area_name_en != ''",
        "lower(area_name_en) != 'unknown'",
        "contract_start_date <= today()",
        "contract_start_date BETWEEN {start_date:Date} AND {end_date:Date}",
    ]
    params: dict[str, Any] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "limit": limit,
        "min_records": min_records,
    }
    if property_usage:
        sales_where.append("property_usage_en = {property_usage:String}")
        rental_where.append("property_usage_en = {property_usage:String}")
        params["property_usage"] = property_usage
    if sales_property_type:
        sales_where.append("property_type_en = {sales_property_type:String}")
        params["sales_property_type"] = sales_property_type
    if rental_property_type:
        rental_where.append("ejari_property_type_en = {rental_property_type:String}")
        params["rental_property_type"] = rental_property_type

    rows = await ch_query(
        f"""
        WITH
            sales AS (
                SELECT
                    area_name_en AS area,
                    median(actual_worth) AS median_sale_price,
                    count() AS sales_count
                FROM ch_transactions
                WHERE {" AND ".join(sales_where)}
                GROUP BY area
                HAVING sales_count >= {{min_records:Int32}}
            ),
            rentals AS (
                SELECT
                    area_name_en AS area,
                    median(annual_amount) AS median_annual_rent,
                    count() AS rental_count
                FROM ch_rent_contracts
                WHERE {" AND ".join(rental_where)}
                GROUP BY area
                HAVING rental_count >= {{min_records:Int32}}
            )
        SELECT
            s.area AS label,
            round(r.median_annual_rent / nullIf(s.median_sale_price, 0) * 100, 2) AS value,
            least(s.sales_count, r.rental_count) AS record_count
        FROM sales AS s
        INNER JOIN rentals AS r ON s.area = r.area
        WHERE value BETWEEN 1 AND 25
        {_chart_order_clause(sort_direction, limit_key="limit")}
        """,
        params,
    )
    points = _chart_points(rows, time_series=False)
    chart_type = _chart_type(args.get("chart_type"), "area")
    return {
        **artifact,
        "status": "ready",
        "title": _metric_label("gross_yield_pct"),
        "subtitle": "Areas · Gross yield · Dubai",
        "query": {
            "dataset": "areas",
            "chart_type": chart_type,
            "group_by": "area",
            "metric": "gross_yield_pct",
            "sort_direction": sort_direction,
            "min_records": min_records,
            "property_usage": property_usage,
            "property_type": yield_property_type,
            "days": days,
            "limit": limit,
        },
        "data": {
            "chart_type": chart_type,
            "metric": "gross_yield_pct",
            "metric_label": _metric_label("gross_yield_pct"),
            "dimension": "area",
            "dimension_label": _dimension_label("area"),
            "data_source": "DLD sales transactions and Ejari rental contracts",
            "sort_direction": sort_direction,
            "points": points,
            "series": [],
            "summary": _chart_summary(points, period_start=start_date, period_end=end_date),
        },
    }


async def _fetch_custom_chart_artifact(
    artifact: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    dataset = str(args.get("dataset") or "sales").lower()
    metric = str(args.get("metric") or "").lower()
    group_by = str(args.get("group_by") or "area").lower()
    if dataset in {"rent", "rental"}:
        dataset = "rentals"
    if dataset in {"area", "areas", "community", "communities", "yield"}:
        dataset = "areas"
    if dataset in {"project", "pipeline", "development", "developments"}:
        dataset = "projects"

    if metric in {"yield", "rental_yield", "gross_yield", "gross_yield_pct"} and group_by == "area":
        return await _fetch_area_yield_chart_artifact(artifact, args)
    if dataset == "areas":
        return await _fetch_area_yield_chart_artifact(artifact, args)
    if dataset == "rentals":
        return await _fetch_rental_chart_artifact(artifact, args)
    if dataset == "projects":
        return await _fetch_project_chart_artifact(artifact, args)
    return await _fetch_sales_chart_artifact(artifact, args)


async def _fetch_artifact(
    db: AsyncSession,
    tool_name: str,
    tool_call_id: str,
    args: dict[str, Any],
    user_message: str | None = None,
) -> dict[str, Any] | None:
    if tool_name not in {"show_listings", "show_market_trend", "show_chart"}:
        return None

    artifact = _artifact_shell(tool_name, tool_call_id, args)
    try:
        if tool_name == "show_listings":
            return await _fetch_listing_artifact(db, artifact, args, user_message)
        if tool_name == "show_market_trend":
            return await _fetch_market_trend_artifact(artifact, args)
        if tool_name == "show_chart":
            return await _fetch_custom_chart_artifact(artifact, args)
    except Exception as exc:
        logger.exception("Failed to build chat artifact for %s", tool_name)
        return {**artifact, "status": "error", "error": str(exc)}
    return None


async def stream_chat_response(
    db: AsyncSession,
    conversation_id: int,
    user_message: str,
    user_id: str,
    organization_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream chat response using Pydantic AI agent via SSE"""
    # Verify conversation ownership
    conversation = await get_conversation(db, conversation_id, user_id)
    if not conversation:
        yield f"data: {json.dumps({'type': 'error', 'error': 'Conversation not found'})}\n\n"
        return

    # Save user message
    await add_message(db, conversation_id, "user", user_message)

    # Get conversation history
    messages = await get_conversation_messages(db, conversation_id)
    message_history = _convert_to_pydantic_messages(messages[:-1])  # Exclude the just-added message

    assistant_message = ""
    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    artifacts: list[dict[str, Any]] = []
    tool_names_by_call_id: dict[str, str] = {}

    try:
        yield _sse({"type": "thinking"})

        async with agent.iter(
            user_message,
            message_history=message_history,
            model_settings=OpenRouterModelSettings(openrouter_reasoning={"effort": "low"}),
        ) as run:
            async for node in run:
                if PydanticAgent.is_model_request_node(node):
                    async with node.stream(run.ctx) as stream:
                        async for chunk_text in stream.stream_text(delta=True, debounce_by=0.01):
                            assistant_message += chunk_text
                            yield _sse({"type": "content", "content": chunk_text})
                elif PydanticAgent.is_call_tools_node(node):
                    for part in node.model_response.parts:
                        if not isinstance(part, ToolCallPart):
                            continue
                        tool_names_by_call_id[part.tool_call_id] = part.tool_name
                        yield _sse(
                            {
                                "type": "tool_call_start",
                                "tool": part.tool_name,
                                "tool_call_id": part.tool_call_id,
                            }
                        )
                        if part.tool_name in {"show_listings", "show_market_trend", "show_chart"}:
                            yield _sse(
                                {
                                    "type": "artifact_opened",
                                    "artifact": _artifact_shell(
                                        part.tool_name, part.tool_call_id, part.args_as_dict()
                                    ),
                                }
                            )
                        artifact = await _fetch_artifact(
                            db,
                            part.tool_name,
                            part.tool_call_id,
                            part.args_as_dict(),
                            user_message,
                        )
                        if artifact is not None:
                            artifacts = [item for item in artifacts if item["id"] != artifact["id"]]
                            artifacts.append(artifact)
                            yield _sse({"type": "artifact_updated", "artifact": artifact})

                    async with node.stream(run.ctx) as tool_stream:
                        async for event in tool_stream:
                            if isinstance(event, FunctionToolResultEvent):
                                tool_call_id = getattr(event.result, "tool_call_id", "")
                                tool_name = getattr(event.result, "tool_name", None)
                                yield _sse(
                                    {
                                        "type": "tool_call_result",
                                        "tool_call_id": tool_call_id,
                                        "tool": tool_name
                                        or tool_names_by_call_id.get(tool_call_id, "tool"),
                                    }
                                )

            usage = run.usage()
            total_tokens = getattr(usage, "total_tokens", 0)
            prompt_tokens = getattr(usage, "request_tokens", 0)
            completion_tokens = getattr(usage, "response_tokens", 0)

            if total_tokens:
                logger.info(
                    f"Token usage: prompt={prompt_tokens}, "
                    f"completion={completion_tokens}, "
                    f"total={total_tokens}"
                )

                await token_usage_service.record_usage(
                    db=db,
                    user_id=user_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )

        # Save assistant message with metadata
        if assistant_message or artifacts:
            meta_data = {}
            if total_tokens:
                meta_data["total_tokens"] = total_tokens
            if artifacts:
                meta_data["artifacts"] = artifacts
            if not assistant_message:
                assistant_message = "I added the requested view below."

            await add_message(db, conversation_id, "assistant", assistant_message, meta_data)

        yield _sse({"type": "done"})

    except Exception as e:
        logger.exception("Error during chat streaming")
        yield _sse({"type": "error", "error": str(e)})
