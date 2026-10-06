import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessagesTypeAdapter, ToolCallPart
from pydantic_ai.usage import UsageLimits

from app.clickhouse.client import query as ch_query
from app.core.openrouter import create_openrouter_model
from app.feasibility.models import (
    FeasibilityPaymentPlan,
    PlotDetails,
    Usage,
)
from app.feasibility.queries import (
    Stage,
    get_land_sale_evidence,
    get_market_pricing,
    get_plot_details,
    rank_plot_comparables,
    transaction_stage_clause,
    transaction_usage_clause,
)

logger = logging.getLogger(__name__)


@dataclass
class FeasibilityChatDeps:
    plot_number: str
    area_name: str
    plot: dict[str, Any]
    study: dict[str, Any] | None
    assumptions: dict[str, Any]
    unit_type_keys: list[str] = field(default_factory=list)


class WorkspaceUnitMixUpdate(BaseModel):
    type: str
    count: int = Field(ge=0)
    avgSizeSqm: float | None = Field(default=None, gt=0)
    price_sqm: float | None = Field(default=None, gt=0)
    parkingRatio: float | None = Field(default=None, ge=0)


class WorkspaceUnitMixReplacement(BaseModel):
    type: str
    count: int = Field(ge=0)
    avgSizeSqm: float = Field(gt=0)
    price_sqm: float | None = Field(default=None, gt=0)
    parkingRatio: float | None = Field(default=None, ge=0)


model = create_openrouter_model()

workspace_chat_agent = Agent(
    model,
    deps_type=FeasibilityChatDeps,
    model_settings={"temperature": 0.1},
    system_prompt=(
        "You are a Dubai real estate feasibility workspace assistant.\n\n"
        "The frontend owns the live workbook. You receive the current assumptions and workbook state each turn.\n"
        "Use tools for precise context or research, and use mutation tools when you want to suggest changes.\n"
        "For unit mix changes, use replace_unit_mix when proposing a new complete target mix; omitted unit "
        "types will be removed. Use update_unit_mix only for partial edits to listed existing unit types.\n"
        "Keep suggestions compact, practical, and evidence-led.\n"
        "When you call a mutation tool, do not write a long rationale. Use at most two short sentences "
        "that explain what the proposed change is and why it is being staged for approval."
    ),
)


@workspace_chat_agent.system_prompt
async def inject_workspace_context(ctx: RunContext[FeasibilityChatDeps]) -> str:
    return (
        "## Current feasibility context\n"
        f"Plot number: {ctx.deps.plot_number}\n"
        f"Area: {ctx.deps.area_name}\n\n"
        "### Plot\n"
        f"{json.dumps(ctx.deps.plot, indent=2)}\n\n"
        "### HBU study\n"
        f"{json.dumps(ctx.deps.study, indent=2)}\n\n"
        "### Current assumptions\n"
        f"{json.dumps(ctx.deps.assumptions, indent=2)}\n"
    )


@workspace_chat_agent.tool
async def get_current_plot(ctx: RunContext[FeasibilityChatDeps]) -> dict[str, Any]:
    return {"success": True, "plot": ctx.deps.plot}


@workspace_chat_agent.tool_plain
async def get_area_market_data(
    area: str, usage: Usage = "residential", stage: Stage = "existing", days: int = 365
) -> dict[str, Any]:
    sql = """
    SELECT area_name_en
    FROM ch_transactions
    WHERE trans_group_en = 'Sales'
      AND area_name_en ILIKE {pattern:String}
    GROUP BY area_name_en
    ORDER BY (lower(area_name_en) = lower({area:String})) DESC, count() DESC
    LIMIT 1
    """
    resolved = await ch_query(sql, {"area": area, "pattern": f"%{area}%"})
    resolved_area = resolved[0]["area_name_en"] if resolved else area
    rows = await get_market_pricing(resolved_area, usage=usage, stage=stage, days=days)
    return {"success": True, "area": resolved_area, "data": [row.model_dump() for row in rows]}


@workspace_chat_agent.tool
async def rank_pricing_comparables(
    ctx: RunContext[FeasibilityChatDeps], usage: Usage = "residential", limit: int = 5
) -> dict[str, Any]:
    details = await get_plot_details(ctx.deps.plot_number)
    if details is None:
        return {"success": False, "error": "Current plot was not found."}
    rows = await rank_plot_comparables(details, usage=usage, comparison_type="pricing", limit=limit)
    return {"success": True, "comparables": [row.model_dump() for row in rows]}


@workspace_chat_agent.tool
async def rank_pipeline_comparables(
    ctx: RunContext[FeasibilityChatDeps], usage: Usage = "residential", limit: int = 5
) -> dict[str, Any]:
    details = await get_plot_details(ctx.deps.plot_number)
    if details is None:
        return {"success": False, "error": "Current plot was not found."}
    rows = await rank_plot_comparables(
        details, usage=usage, comparison_type="pipeline", limit=limit
    )
    return {"success": True, "comparables": [row.model_dump() for row in rows]}


@workspace_chat_agent.tool
async def get_plot_land_sales(
    ctx: RunContext[FeasibilityChatDeps], days: int = 1825, limit: int = 12
) -> dict[str, Any]:
    details = await get_plot_details(ctx.deps.plot_number)
    if details is None:
        return {"success": False, "error": "Current plot was not found."}
    rows = await get_land_sale_evidence(
        area_name=details.community_name,
        plot_area_sqm=details.plot_area_sqm,
        days=days,
        limit=limit,
    )
    return {"success": True, "land_sales": [row.model_dump() for row in rows]}


@workspace_chat_agent.tool_plain
async def show_transactions(
    area: str,
    unit_type: str = "",
    usage: Usage = "residential",
    stage: Stage = "existing",
    days: int = 365,
    limit: int = 50,
) -> str:
    subject = (
        f"recent {unit_type} transactions in {area}"
        if unit_type
        else f"recent transactions in {area}"
    )
    return f"Pulling up {subject} ({usage}, {stage}, last {days} days, up to {limit}) in the Research panel."


@workspace_chat_agent.tool_plain
async def show_analytics(
    area: str = "",
    project_name: str = "",
    usage: Usage = "residential",
    stage: Stage = "existing",
    days: int = 365,
) -> str:
    subject = project_name or area or "current area"
    return f"Pulling up price analytics for {subject} ({usage}, {stage}, last {days} days) in the Research panel."


@workspace_chat_agent.tool
async def update_prices(ctx: RunContext[FeasibilityChatDeps], prices: dict[str, float]) -> str:
    if ctx.deps.unit_type_keys:
        invalid = [key for key in prices if key not in ctx.deps.unit_type_keys]
        if invalid:
            return f"Invalid unit type keys. Valid keys are: {json.dumps(ctx.deps.unit_type_keys)}."
    return f"Proposed price update for {len(prices)} unit type(s). Awaiting user approval."


@workspace_chat_agent.tool_plain
async def update_unit_mix(unit_mix: list[WorkspaceUnitMixUpdate]) -> str:
    """Patch only the listed unit types, keeping unmentioned unit types unchanged."""
    return f"Proposed partial unit mix update for {len(unit_mix)} unit type(s). Awaiting user approval."


@workspace_chat_agent.tool_plain
async def replace_unit_mix(unit_mix: list[WorkspaceUnitMixReplacement]) -> str:
    """Replace the full unit mix with exactly the listed unit types."""
    return f"Proposed full unit mix replacement with {len(unit_mix)} unit type(s). Awaiting user approval."


@workspace_chat_agent.tool_plain
async def update_assumptions(assumptions: dict[str, Any]) -> str:
    return (
        f"Proposed assumption update for {len(assumptions)} parameter(s). Awaiting user approval."
    )


@workspace_chat_agent.tool_plain
async def update_payment_plan(payment_plan: FeasibilityPaymentPlan) -> str:
    return f"Proposed payment plan update: deposit {payment_plan.depositPct}%, construction {payment_plan.constructionPct}%, handover {payment_plan.handoverPct}%. Awaiting user approval."


_RESEARCH_TOOLS = {"show_transactions": "transactions", "show_analytics": "analytics"}
_MUTATION_TOOLS = {
    "update_prices": "set_price_per_sqm",
    "update_unit_mix": "update_unit_mix",
    "replace_unit_mix": "replace_unit_mix",
    "update_assumptions": "set_assumptions",
    "update_payment_plan": "set_payment_plan",
}


def _extract_payload(part: ToolCallPart) -> Any:
    args = part.args_as_dict()
    if part.tool_name == "update_prices":
        return args.get("prices", args)
    if part.tool_name == "update_unit_mix":
        raw = args.get("unit_mix", args)
        return [WorkspaceUnitMixUpdate(**row).model_dump(exclude_none=True) for row in raw]
    if part.tool_name == "replace_unit_mix":
        raw = args.get("unit_mix", args)
        return [WorkspaceUnitMixReplacement(**row).model_dump(exclude_none=True) for row in raw]
    if part.tool_name == "update_assumptions":
        return args.get("assumptions", args)
    if part.tool_name == "update_payment_plan":
        raw = args.get("payment_plan", args)
        return FeasibilityPaymentPlan(**raw).model_dump()
    return None


def _unit_type_keys_from_assumptions(assumptions: dict[str, Any]) -> list[str]:
    unit_configs = assumptions.get("unitConfigs")
    if not isinstance(unit_configs, list):
        return []

    keys: list[str] = []
    for row in unit_configs:
        if not isinstance(row, dict):
            continue
        unit_id = row.get("id")
        if isinstance(unit_id, str):
            keys.append(unit_id)
    return keys


async def _resolve_area(area: str) -> str:
    if not area:
        return area
    sql = """
    SELECT area_name_en
    FROM ch_transactions
    WHERE area_name_en ILIKE {pattern:String}
      AND trans_group_en = 'Sales' AND meter_sale_price > 0
    GROUP BY area_name_en
    ORDER BY (area_name_en = {area:String}) DESC, count() DESC
    LIMIT 1
    """
    rows = await ch_query(sql, {"area": area, "pattern": f"%{area}%"})
    return rows[0]["area_name_en"] if rows else area


async def _fetch_research_payload(tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    if tool_name == "show_transactions":
        area = await _resolve_area(args.get("area", ""))
        unit_type = args.get("unit_type", "")
        usage = args.get("usage", "residential")
        stage = args.get("stage", "existing")
        days = args.get("days", 365)
        limit = min(args.get("limit", 50), 100)
        where = [
            "trans_group_en = 'Sales'",
            "meter_sale_price > 0",
            transaction_usage_clause(usage),
            transaction_stage_clause(stage),
        ]
        params: dict[str, Any] = {"limit": limit}
        if area:
            where.append("area_name_en = {area:String}")
            params["area"] = area
        if unit_type:
            where.append("rooms_en = {unit_type:String}")
            params["unit_type"] = unit_type
        if days:
            where.append("instance_date >= today() - {days:Int32}")
            params["days"] = days
        sql = f"""
        SELECT transaction_id, instance_date, project_name_en, rooms_en,
               procedure_area, actual_worth, meter_sale_price, reg_type_en
        FROM ch_transactions
        WHERE {" AND ".join(where)}
        ORDER BY instance_date DESC
        LIMIT {{limit:Int32}}
        """
        rows = await ch_query(sql, params)
        return {"rows": rows, "filters": {"area": area, "unit_type": unit_type}, "count": len(rows)}
    if tool_name == "show_analytics":
        area = args.get("area", "")
        project_name = args.get("project_name", "")
        usage = args.get("usage", "residential")
        stage = args.get("stage", "existing")
        days = args.get("days", 365)
        if area and not project_name:
            area = await _resolve_area(area)
        where = [
            "meter_sale_price > 0",
            "trans_group_en = 'Sales'",
            transaction_usage_clause(usage),
            transaction_stage_clause(stage),
        ]
        params: dict[str, Any] = {}
        if project_name:
            where.append("project_name_en = {project_name:String}")
            params["project_name"] = project_name
        elif area:
            where.append("area_name_en = {area:String}")
            params["area"] = area
        if days:
            where.append("instance_date >= today() - {days:Int32}")
            params["days"] = days
        where_clause = " AND ".join(where)
        trend_sql = f"""
        SELECT toStartOfMonth(instance_date) AS month,
               round(median(meter_sale_price), 0) AS median_price_sqm,
               count() AS txn_count
        FROM ch_transactions
        WHERE {where_clause}
        GROUP BY month ORDER BY month
        """
        rooms_sql = f"""
        SELECT rooms_en, count() AS txn_count,
               round(median(meter_sale_price), 0) AS median_price_sqm,
               round(avg(procedure_area), 0) AS avg_area_sqm
        FROM ch_transactions
        WHERE {where_clause}
        GROUP BY rooms_en ORDER BY txn_count DESC
        """
        trend_rows = await ch_query(trend_sql, params)
        rooms_rows = await ch_query(rooms_sql, params)
        return {
            "trend": trend_rows,
            "by_rooms": rooms_rows,
            "filters": {"area": area, "project_name": project_name},
        }
    return None


async def stream_feasibility_response(
    messages: list[dict],
    plot_data: PlotDetails,
    assumptions: dict[str, Any],
    research: dict | None = None,
    history_json: str | None = None,
) -> AsyncGenerator[str, None]:
    deps = FeasibilityChatDeps(
        plot_number=plot_data.plot_number,
        area_name=plot_data.community_name,
        plot=plot_data.model_dump(mode="json"),
        study=research,
        assumptions=assumptions,
        unit_type_keys=_unit_type_keys_from_assumptions(assumptions),
    )

    history: list[Any] = []
    if history_json:
        try:
            history = ModelMessagesTypeAdapter.validate_json(history_json)
        except Exception:
            logger.exception("Failed to deserialize feasibility history_json")
            yield f"data: {json.dumps({'type': 'warning', 'content': 'Session context reset — conversation history could not be restored.'})}\n\n"

    user_turns = [message for message in messages if message.get("role") == "user"]
    user_message = user_turns[-1].get("content", "") if user_turns else ""

    try:
        async with workspace_chat_agent.iter(
            user_message,
            message_history=history,
            deps=deps,
            usage_limits=UsageLimits(request_limit=10),
        ) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as stream:
                        async for chunk in stream.stream_text(delta=True, debounce_by=0.01):
                            yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                elif Agent.is_call_tools_node(node):
                    for part in node.model_response.parts:
                        if not isinstance(part, ToolCallPart):
                            continue
                        if part.tool_name in _MUTATION_TOOLS:
                            payload = _extract_payload(part)
                            if payload is not None:
                                yield f"data: {json.dumps({'type': 'pending_action', 'action': _MUTATION_TOOLS[part.tool_name], 'payload': payload}, default=str)}\n\n"
                        elif part.tool_name in _RESEARCH_TOOLS:
                            payload = await _fetch_research_payload(
                                part.tool_name, part.args_as_dict()
                            )
                            if payload is not None:
                                yield f"data: {json.dumps({'type': 'show_research', 'tab': _RESEARCH_TOOLS[part.tool_name], 'data': payload}, default=str)}\n\n"
            new_messages_json = run.new_messages_json().decode()
            yield f"data: {json.dumps({'type': 'done', 'new_messages_json': new_messages_json})}\n\n"
    except Exception as exc:
        logger.exception("Error in feasibility chat stream")
        yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
