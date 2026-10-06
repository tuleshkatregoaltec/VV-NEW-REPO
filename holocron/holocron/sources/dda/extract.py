"""DDA planning map extraction logic."""

from __future__ import annotations

import csv
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from holocron.contracts import RawFile, RawRelease
from holocron.platform.execution import build_raw_release, new_run_id, utc_now
from holocron.platform.metadata import safe_config_metadata
from holocron.platform.raw_files import build_raw_file_from_path, count_csv_rows
from holocron.sources.dda.parse import (
    BUILDING_LIMIT_CSV_FIELDS,
    FROZEN_PLOT_CSV_FIELDS,
    LANDUSE_SYMBOL_CSV_FIELDS,
    PLOT_ARCADE_CSV_FIELDS,
    PLOT_BUILT_TO_LINE_CSV_FIELDS,
    PLOT_CSV_FIELDS,
    PLOT_FEATURE_CSV_FIELDS,
    PLOT_RETAIL_CSV_FIELDS,
    PODIUM_LIMIT_CSV_FIELDS,
    PROJECT_CSV_FIELDS,
    SUBPROJECT_CSV_FIELDS,
    arcade_row,
    building_limit_row,
    built_to_line_row,
    frozen_plot_row,
    landuse_symbol_row,
    parse_plot_info,
    plot_feature_row,
    podium_limit_row,
    project_area_row,
    retail_row,
    subproject_area_row,
)
from holocron.sources.dda.source import DdaConfig, SOURCE

logger = logging.getLogger(__name__)

_BASE_URL = "https://gis.dda.gov.ae"
_PAGE_SIZE = 2000
_MAX_RETRIES = 3
_PLOTS_FILE = "dda_plots.csv"
_PLOTS_LAYER_ID = 13

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": f"{_BASE_URL}/DIS",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True, slots=True)
class LayerSpec:
    file_name: str
    layer_id: int
    out_fields: str
    csv_fields: list[str]
    row_builder: Callable[[dict], dict]
    label: str


_LAYER_SPECS = (
    LayerSpec(
        file_name="dda_project_areas.csv",
        layer_id=10,
        out_fields="OBJECTID,ProjectName",
        csv_fields=PROJECT_CSV_FIELDS,
        row_builder=project_area_row,
        label="project_areas",
    ),
    LayerSpec(
        file_name="dda_subproject_areas.csv",
        layer_id=11,
        out_fields="*",
        csv_fields=SUBPROJECT_CSV_FIELDS,
        row_builder=subproject_area_row,
        label="subproject_areas",
    ),
    LayerSpec(
        file_name="dda_plot_building_limits.csv",
        layer_id=8,
        out_fields="OBJECTID,PlotNumber",
        csv_fields=BUILDING_LIMIT_CSV_FIELDS,
        row_builder=building_limit_row,
        label="plot_building_limits",
    ),
    LayerSpec(
        file_name="dda_plot_podium_limits.csv",
        layer_id=9,
        out_fields="OBJECTID,PlotNumber,MaxHeight",
        csv_fields=PODIUM_LIMIT_CSV_FIELDS,
        row_builder=podium_limit_row,
        label="plot_podium_limits",
    ),
    LayerSpec(
        file_name="dda_plot_features.csv",
        layer_id=7,
        out_fields="OBJECTID,FeatureType,PlotNumber,SHAPE.STArea(),SHAPE.STLength()",
        csv_fields=PLOT_FEATURE_CSV_FIELDS,
        row_builder=plot_feature_row,
        label="plot_features",
    ),
    LayerSpec(
        file_name="dda_frozen_plots.csv",
        layer_id=16,
        out_fields=(
            "OBJECTID,PLOT_NUMBER,OLD_PLOT_NUMBERS,IS_FROZEN,"
            "SHAPE.STArea(),SHAPE.STLength(),GFA_TYPE,GFA_SQM_T,GFA_SQFT_T"
        ),
        csv_fields=FROZEN_PLOT_CSV_FIELDS,
        row_builder=frozen_plot_row,
        label="frozen_plots",
    ),
    LayerSpec(
        file_name="dda_landuse_symbols.csv",
        layer_id=15,
        out_fields="OBJECTID,LANDUSE,LANDUSE_CHARACTER,LANDUSE_ID",
        csv_fields=LANDUSE_SYMBOL_CSV_FIELDS,
        row_builder=landuse_symbol_row,
        label="landuse_symbols",
    ),
    LayerSpec(
        file_name="dda_plot_built_to_lines.csv",
        layer_id=4,
        out_fields="OBJECTID,PlotNumber",
        csv_fields=PLOT_BUILT_TO_LINE_CSV_FIELDS,
        row_builder=built_to_line_row,
        label="plot_built_to_lines",
    ),
    LayerSpec(
        file_name="dda_plot_arcades.csv",
        layer_id=5,
        out_fields="OBJECTID,PlotNumber",
        csv_fields=PLOT_ARCADE_CSV_FIELDS,
        row_builder=arcade_row,
        label="plot_arcades",
    ),
    LayerSpec(
        file_name="dda_plot_retail.csv",
        layer_id=6,
        out_fields="OBJECTID,PlotNumber",
        csv_fields=PLOT_RETAIL_CSV_FIELDS,
        row_builder=retail_row,
        label="plot_retail",
    ),
)


def _fetch_token(client: httpx.Client) -> str:
    logger.info("dda: fetching planning map token")
    response = client.get(f"{_BASE_URL}/DIS", headers=_HEADERS)
    response.raise_for_status()
    match = re.search(r'"AGSToken"\s*:\s*"([^"]+)"', response.text)
    if match is None:
        raise RuntimeError("Could not extract AGSToken from DIS page HTML")
    return match.group(1)


def _is_token_error(data: dict) -> bool:
    error = data.get("error") or {}
    return error.get("code") in {498, 499}


def _fetch_plot_info(client: httpx.Client, plot: dict) -> dict:
    plot_number = plot["PLOT_NUMBER"]
    base = {
        "plot_number": plot_number,
        "old_numbers": plot.get("OLD_PLOT_NUMBERS") or "",
        "landuse_symbols": plot.get("LANDUSE_SYMBOLS") or "",
        "gfa_type": plot.get("GFA_TYPE") or "",
        "is_verified": str(plot.get("IS_VERIFIED") or ""),
        "verify_comments": plot.get("VERIFY_COMMENTS") or "",
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.get(
                f"{_BASE_URL}/DIS",
                params={"handler": "PlotInfo", "plotNumber": plot_number},
                headers=_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            if "form-info-dda" not in response.text:
                raise ValueError("Unexpected response (possible WAF block)")
            return {**base, **parse_plot_info(response.text, plot_number)}
        except (httpx.HTTPError, ValueError) as exc:
            if attempt == _MAX_RETRIES:
                logger.warning(
                    "dda: plot %s failed after %s attempts: %r",
                    plot_number,
                    _MAX_RETRIES,
                    exc,
                )
                return base
            time.sleep(2**attempt)
    return base


def _fetch_all_layer_features(
    client: httpx.Client,
    token: str,
    layer_id: int,
    *,
    out_fields: str = "*",
    out_sr: int | None = 4326,
    where: str = "1=1",
    return_geometry: bool = True,
    limit: int | None = None,
    label: str | None = None,
) -> list[dict]:
    features: list[dict] = []
    offset = 0
    current_token = token
    token_refreshes = 0
    layer_label = label or f"layer {layer_id}"
    logger.info("dda: starting %s fetch (layer_id=%s)", layer_label, layer_id)

    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "resultRecordCount": _PAGE_SIZE,
            "resultOffset": offset,
            "f": "json",
            "token": current_token,
        }
        if out_sr is not None:
            params["outSR"] = str(out_sr)

        response = client.get(
            f"{_BASE_URL}/server/rest/services/DIS/MAIN_MAP/MapServer/{layer_id}/query",
            params=params,
            headers=_HEADERS,
        )
        response.raise_for_status()
        data = response.json()
        if _is_token_error(data):
            token_refreshes += 1
            if token_refreshes > _MAX_RETRIES:
                raise RuntimeError(
                    f"ArcGIS token refresh failed {token_refreshes} times for layer {layer_id}"
                )
            logger.info(
                "dda: token expired while fetching %s; refreshing (%s/%s)",
                layer_label,
                token_refreshes,
                _MAX_RETRIES,
            )
            current_token = _fetch_token(client)
            continue
        token_refreshes = 0
        if "error" in data:
            raise RuntimeError(f"ArcGIS error for layer {layer_id}: {data['error']}")

        batch = data.get("features", [])
        if not batch:
            break
        features.extend(batch)
        logger.info(
            "dda: %s fetched offset=%s batch=%s total=%s",
            layer_label,
            offset,
            len(batch),
            len(features),
        )
        if limit is not None and len(features) >= limit:
            features = features[:limit]
            break
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    logger.info("dda: completed %s fetch with %s features", layer_label, len(features))
    return features


def _write_csv(path: Path, *, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_raw_file(path: Path) -> RawFile:
    return build_raw_file_from_path(
        path=path,
        row_count=count_csv_rows(path),
        content_type="text/csv",
    )


def _skip_if_done(output: Path, label: str) -> bool:
    if output.exists() and output.stat().st_size > 0:
        logger.info("dda: skipping %s (already complete at %s)", label, output)
        return True
    return False


def _scrape_plots(output: Path, *, concurrency: int, max_plots: int | None) -> None:
    done_plots: set[str] = set()
    if output.exists():
        with output.open(encoding="utf-8") as handle:
            done_plots = {
                row["plot_number"] for row in csv.DictReader(handle) if row.get("plot_number")
            }

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        token = _fetch_token(client)
        fetch_limit = None if max_plots is None else len(done_plots) + max_plots
        raw = _fetch_all_layer_features(
            client,
            token,
            _PLOTS_LAYER_ID,
            out_fields="PLOT_NUMBER,OLD_PLOT_NUMBERS,LANDUSE_SYMBOLS,GFA_TYPE,IS_VERIFIED,VERIFY_COMMENTS",
            out_sr=None,
            return_geometry=False,
            limit=fetch_limit,
            label="plots",
        )
        all_plots = [feature["attributes"] for feature in raw]
        pending = [plot for plot in all_plots if plot["PLOT_NUMBER"] not in done_plots]
        if max_plots is not None:
            pending = pending[:max_plots]

        write_mode = "a" if done_plots else "w"
        worker_count = max(1, concurrency)
        with output.open(write_mode, newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PLOT_CSV_FIELDS, extrasaction="ignore")
            if not done_plots:
                writer.writeheader()

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [executor.submit(_fetch_plot_info, client, plot) for plot in pending]
                for future in as_completed(futures):
                    writer.writerow(future.result())
                    handle.flush()


def _scrape_layer(client: httpx.Client, token: str, output: Path, spec: LayerSpec) -> None:
    features = _fetch_all_layer_features(
        client,
        token,
        spec.layer_id,
        out_fields=spec.out_fields,
        label=spec.label,
    )
    rows = [spec.row_builder(feature) for feature in features]
    _write_csv(output, fieldnames=spec.csv_fields, rows=rows)
    logger.info("dda: wrote %s %s rows to %s", len(rows), spec.label, output)


def scrape_all_layers(output_dir: Path, *, concurrency: int, max_plots: int | None) -> None:
    logger.info("dda: starting full scrape into %s", output_dir)
    _scrape_plots(output=output_dir / _PLOTS_FILE, concurrency=concurrency, max_plots=max_plots)

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        token = _fetch_token(client)
        for spec in _LAYER_SPECS:
            output = output_dir / spec.file_name
            if _skip_if_done(output, spec.label):
                continue
            _scrape_layer(client, token, output, spec)

    logger.info("dda: completed full scrape")


def extract_release(
    output_dir: str | Path,
    *,
    config: DdaConfig | dict,
    now: datetime | None = None,
    scrape_runner: Callable[..., None] | None = None,
) -> RawRelease:
    parsed_config = config if isinstance(config, DdaConfig) else DdaConfig.model_validate(config)
    current_time = now or utc_now()
    run_id = new_run_id(current_time)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    runner = scrape_runner or scrape_all_layers
    runner(
        output_path,
        concurrency=parsed_config.concurrency,
        max_plots=parsed_config.max_plots,
    )

    files = tuple(
        _build_raw_file(output_path / file_name)
        for file_name in (_PLOTS_FILE, *(spec.file_name for spec in _LAYER_SPECS))
        if (output_path / file_name).exists()
    )

    if not files:
        raise RuntimeError("DDA extraction produced no raw files")

    return build_raw_release(
        source=SOURCE,
        files=files,
        run_id=run_id,
        now=current_time,
        metadata={"config": safe_config_metadata(parsed_config)},
    )
