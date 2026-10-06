import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.feasibility.chat_agent import stream_feasibility_response
from app.feasibility.hbu_agent import generate_hbu_study
from app.feasibility.models import (
    ComparableData,
    DevelopmentModel,
    FeasibilityChatRequest,
    FeasibilityChatState,
    FeasibilitySavedStudy,
    FeasibilitySavedStudyListItem,
    FeasibilitySavedStudyResponse,
    FeasibilityStudyCreateRequest,
    FeasibilityStudyUpdateRequest,
    GenerateStudyRequest,
    GenerateStudyResponse,
    LandSaleEvidence,
    Plot,
    PlotDetails,
    PlotResearch,
    StudyContext,
    Usage,
)
from app.feasibility.queries import (
    get_areas,
    get_comparable_data,
    get_land_plots,
    get_land_sale_evidence,
    get_plot_details,
    list_communities,
    search_land_plots,
    search_plots,
)

logger = logging.getLogger(__name__)
VALID_DEVELOPMENT_MODELS: set[str] = {
    "build_to_sell_residential",
    "build_to_rent_residential",
    "build_to_lease_commercial",
}


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def _build_study_context(research: PlotResearch) -> StudyContext:
    return StudyContext(
        headline=research.headline,
        project_tier="premium",
        summary_points=list(research.summary),
        market_summary=", ".join(research.constraints) if research.constraints else "",
    )


def _parse_project_ids(project_ids: str) -> list[int]:
    return [int(value.strip()) for value in project_ids.split(",") if value.strip().isdigit()]


def _dump_model(model) -> dict:
    return model.model_dump(mode="json")


def _dump_json_object(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _development_model_from_assumptions(assumptions: dict[str, Any]) -> str | None:
    development_model = assumptions.get("developmentModel")
    if isinstance(development_model, str) and development_model in VALID_DEVELOPMENT_MODELS:
        return development_model
    return None


def _empty_chat_state() -> dict:
    return FeasibilityChatState().model_dump(mode="json")


def _study_response(study: FeasibilitySavedStudy) -> FeasibilitySavedStudyResponse:
    if study.id is None:
        raise HTTPException(status_code=500, detail="Saved study is missing an id")
    return FeasibilitySavedStudyResponse(
        id=study.id,
        name=study.name,
        plot_number=study.plot_number,
        development_model=study.development_model,
        assumptions=study.assumptions,
        plot_data=PlotDetails.model_validate(study.plot_data),
        research=PlotResearch.model_validate(study.research),
        study_context=StudyContext.model_validate(study.study_context),
        chat_state=FeasibilityChatState.model_validate(study.chat_state or _empty_chat_state()),
        created_at=study.created_at,
        updated_at=study.updated_at,
    )


def _study_list_item(study: FeasibilitySavedStudy) -> FeasibilitySavedStudyListItem:
    if study.id is None:
        raise HTTPException(status_code=500, detail="Saved study is missing an id")
    return FeasibilitySavedStudyListItem(
        id=study.id,
        name=study.name,
        plot_number=study.plot_number,
        development_model=study.development_model,
        plot_data=PlotDetails.model_validate(study.plot_data),
        created_at=study.created_at,
        updated_at=study.updated_at,
    )


async def _get_saved_study_or_404(
    db: AsyncSession,
    *,
    study_id: int,
    user_id: str,
    organization_id: str,
) -> FeasibilitySavedStudy:
    stmt = select(FeasibilitySavedStudy).where(
        FeasibilitySavedStudy.id == study_id,
        FeasibilitySavedStudy.user_id == user_id,
        FeasibilitySavedStudy.organization_id == organization_id,
    )
    result = await db.exec(stmt)
    study = result.first()
    if study is None:
        raise _not_found("Feasibility study not found")
    return study


async def list_transaction_areas() -> list[str]:
    return await get_areas()


async def list_plot_communities() -> list[str]:
    return await list_communities()


async def search_gis_plots(
    *,
    q: str,
    community: str,
    min_plot_area_sqm: float | None,
    max_plot_area_sqm: float | None,
    offset: int,
    limit: int,
) -> list[Plot]:
    return await search_plots(
        q=q,
        community=community,
        min_plot_area_sqm=min_plot_area_sqm,
        max_plot_area_sqm=max_plot_area_sqm,
        offset=offset,
        limit=limit,
    )


async def get_plot_details_or_404(plot_number: str) -> PlotDetails:
    plot = await get_plot_details(plot_number)
    if plot is None:
        raise _not_found("GIS plot not found")
    return plot


async def generate_hbu_for_plot(
    plot_number: str,
    usage_override: Usage | None = None,
    development_model: DevelopmentModel | None = None,
) -> PlotResearch:
    study = await generate_hbu_study(
        plot_number,
        usage_override=usage_override,
        development_model=development_model,
    )
    if study is None:
        raise _not_found("GIS plot not found")
    return study


async def get_plot_land_sales_or_404(
    *,
    plot_number: str,
    days: int,
    limit: int,
) -> list[LandSaleEvidence]:
    plot = await get_plot_details_or_404(plot_number)
    return await get_land_sale_evidence(
        area_name=plot.community_name,
        plot_area_sqm=plot.plot_area_sqm,
        days=days,
        limit=limit,
    )


async def list_nearby_land_plots(area: str, size_sqm: float, tolerance: float) -> list[Plot]:
    return await get_land_plots(area, size_sqm, tolerance)


async def search_nearby_land_plots(area: str, q: str) -> list[Plot]:
    return await search_land_plots(area, q)


async def get_comparable_or_404(project_ids: str) -> ComparableData:
    comparable = await get_comparable_data(_parse_project_ids(project_ids))
    if comparable is None:
        raise _not_found("No data found for given project IDs")
    return comparable


async def generate_seeded_study(request: GenerateStudyRequest) -> GenerateStudyResponse:
    try:
        research = await generate_hbu_for_plot(
            request.plot_number,
            usage_override=request.usage_override,
            development_model=request.development_model,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_hbu_study failed for plot %s: %s", request.plot_number, e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    plot = await get_plot_details_or_404(request.plot_number)
    return GenerateStudyResponse(
        plot_data=plot,
        assumptions=research.assumptions,
        research=research,
        study_context=_build_study_context(research),
    )


async def list_saved_studies(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str,
) -> list[FeasibilitySavedStudyListItem]:
    stmt = (
        select(FeasibilitySavedStudy)
        .where(
            FeasibilitySavedStudy.user_id == user_id,
            FeasibilitySavedStudy.organization_id == organization_id,
        )
        .order_by(FeasibilitySavedStudy.updated_at.desc())
    )
    result = await db.exec(stmt)
    return [_study_list_item(study) for study in result.all()]


async def create_saved_study(
    db: AsyncSession,
    *,
    request: FeasibilityStudyCreateRequest,
    user_id: str,
    organization_id: str,
) -> FeasibilitySavedStudyResponse:
    generated = await generate_seeded_study(
        GenerateStudyRequest(
            plot_number=request.plot_number,
            usage_override=request.usage_override,
            development_model=request.development_model,
        )
    )
    assumptions = generated.assumptions.model_copy(
        update={"developmentModel": request.development_model}
    )
    now = datetime.now(timezone.utc)
    study = FeasibilitySavedStudy(
        user_id=user_id,
        organization_id=organization_id,
        name=request.name.strip(),
        plot_number=generated.plot_data.plot_number,
        development_model=request.development_model,
        assumptions=_dump_model(assumptions),
        plot_data=_dump_model(generated.plot_data),
        research=_dump_model(generated.research),
        study_context=_dump_model(generated.study_context),
        chat_state=_empty_chat_state(),
        created_at=now,
        updated_at=now,
    )
    db.add(study)
    await db.commit()
    await db.refresh(study)
    return _study_response(study)


async def get_saved_study(
    db: AsyncSession,
    *,
    study_id: int,
    user_id: str,
    organization_id: str,
) -> FeasibilitySavedStudyResponse:
    return _study_response(
        await _get_saved_study_or_404(
            db,
            study_id=study_id,
            user_id=user_id,
            organization_id=organization_id,
        )
    )


async def update_saved_study(
    db: AsyncSession,
    *,
    study_id: int,
    request: FeasibilityStudyUpdateRequest,
    user_id: str,
    organization_id: str,
) -> FeasibilitySavedStudyResponse:
    study = await _get_saved_study_or_404(
        db,
        study_id=study_id,
        user_id=user_id,
        organization_id=organization_id,
    )
    if request.name is not None:
        study.name = request.name.strip()
    if request.development_model is not None:
        study.development_model = request.development_model
    if request.assumptions is not None:
        study.assumptions = _dump_json_object(request.assumptions)
        assumed_development_model = _development_model_from_assumptions(request.assumptions)
        if request.development_model is None and assumed_development_model is not None:
            study.development_model = assumed_development_model
    if request.plot_data is not None:
        study.plot_data = _dump_model(request.plot_data)
        study.plot_number = request.plot_data.plot_number
    if request.research is not None:
        study.research = _dump_model(request.research)
    if request.study_context is not None:
        study.study_context = _dump_model(request.study_context)
    if request.chat_state is not None:
        study.chat_state = _dump_model(request.chat_state)
    study.updated_at = datetime.now(timezone.utc)
    db.add(study)
    await db.commit()
    await db.refresh(study)
    return _study_response(study)


async def delete_saved_study(
    db: AsyncSession,
    *,
    study_id: int,
    user_id: str,
    organization_id: str,
) -> None:
    study = await _get_saved_study_or_404(
        db,
        study_id=study_id,
        user_id=user_id,
        organization_id=organization_id,
    )
    await db.delete(study)
    await db.commit()


async def stream_chat_events(request: FeasibilityChatRequest) -> AsyncGenerator[str, None]:
    try:
        async for chunk in stream_feasibility_response(
            request.messages,
            request.plot_data,
            request.assumptions,
            request.research,
            request.history_json,
        ):
            yield chunk
    except Exception:
        logger.exception("Error in feasibility chat stream service")
        yield f"data: {json.dumps({'type': 'error', 'error': 'Internal server error'})}\n\n"
