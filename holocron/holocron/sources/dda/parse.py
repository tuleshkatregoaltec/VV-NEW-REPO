"""DDA planning-layer parsing helpers kept local to the source package."""

from __future__ import annotations

import html as html_lib
import json
import re

PLOT_CSV_FIELDS = [
    "plot_number",
    "old_numbers",
    "project_name",
    "community_name",
    "master_developer",
    "plot_area_sqm",
    "plot_area_sqft",
    "max_gfa_sqm",
    "max_gfa_sqft",
    "max_height",
    "max_coverage",
    "site_plan_issue_date",
    "site_plan_expiry_date",
    "side1_building",
    "side1_podium",
    "side2_building",
    "side2_podium",
    "side3_building",
    "side3_podium",
    "side4_building",
    "side4_podium",
    "land_use",
    "general_notes",
    "coordinates",
    "landuse_symbols",
    "gfa_type",
    "is_verified",
    "verify_comments",
]

PROJECT_CSV_FIELDS = ["object_id", "project_name", "rings"]
SUBPROJECT_CSV_FIELDS = [
    "object_id",
    "project_id",
    "project_name",
    "entity_name",
    "developer_name",
    "master_project_name",
    "original_plot_number",
    "project_logo",
    "rings",
]
BUILDING_LIMIT_CSV_FIELDS = ["object_id", "plot_number", "rings"]
PODIUM_LIMIT_CSV_FIELDS = ["object_id", "plot_number", "max_height", "rings"]
PLOT_FEATURE_CSV_FIELDS = [
    "object_id",
    "plot_number",
    "feature_type_code",
    "feature_type_label",
    "feature_area_sqm",
    "feature_perimeter_m",
    "rings",
]
FROZEN_PLOT_CSV_FIELDS = [
    "object_id",
    "plot_number",
    "old_plot_numbers",
    "is_frozen",
    "plot_area_sqm",
    "plot_perimeter_m",
    "gfa_type",
    "gfa_sqm_t",
    "gfa_sqft_t",
    "rings",
]
LANDUSE_SYMBOL_CSV_FIELDS = [
    "object_id",
    "landuse",
    "landuse_character",
    "landuse_id",
    "lat",
    "lng",
]
PLOT_BUILT_TO_LINE_CSV_FIELDS = ["object_id", "plot_number", "paths"]
PLOT_ARCADE_CSV_FIELDS = ["object_id", "plot_number", "rings"]
PLOT_RETAIL_CSV_FIELDS = ["object_id", "plot_number", "rings"]

PLOT_FEATURE_LABELS = {
    1: "No Construction Allowed",
    2: "Affected Area",
    3: "Basement Limit",
    4: "Frozen Area",
    5: "Reserved Corridor",
    6: "Easement Limit",
    7: "Pedestrian Interface",
    8: "Walkway",
    9: "Loading Area",
    10: "Landscape",
    11: "Optional Podium",
    12: "Low Rise Zone",
    13: "Restricted Build Zone",
    14: "Parking Structure",
    15: "Parking Area",
    16: "Structure Limit",
    17: "Allocated Underground Parking",
}


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def strip_tags(text: str) -> str:
    return html_lib.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def parse_area(text: str) -> tuple[str, str]:
    sqm_match = re.search(r"([\d,]+\.?\d*)\s*M", text)
    sqm = sqm_match.group(1).replace(",", "") if sqm_match else ""
    sqft_match = re.search(r"\(([\d,]+\.?\d*)\s*Ft", text)
    sqft = sqft_match.group(1).replace(",", "") if sqft_match else ""
    return sqm, sqft


def parse_plot_info(html: str, plot_number: str) -> dict:
    row: dict = {"plot_number": plot_number}
    for match in re.finditer(
        r"<label[^>]*>([^<]+)</label>\s*<div[^>]*form-info-dda[^>]*>(.*?)</div>",
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        label = match.group(1).strip()
        value = strip_tags(match.group(2)).replace("\xa0", " ")

        if label == "Old Numbers":
            row["old_numbers"] = value
        elif label == "Project Name":
            row["project_name"] = value
        elif label == "Community Name":
            row["community_name"] = value
        elif label == "Master Developer":
            row["master_developer"] = value
        elif label == "Plot Area":
            row["plot_area_sqm"], row["plot_area_sqft"] = parse_area(value)
        elif label == "Maximum GFA":
            row["max_gfa_sqm"], row["max_gfa_sqft"] = parse_area(value)
        elif label == "Maximum Height":
            row["max_height"] = value
        elif label == "Maximum Coverage":
            row["max_coverage"] = value
        elif label == "Site Plan Issue Date":
            row["site_plan_issue_date"] = value
        elif label == "Site Plan Expiry Date":
            row["site_plan_expiry_date"] = value

    for match in re.finditer(
        r"<td[^>]*>Side (\d+)</td>\s*<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>",
        html,
        re.IGNORECASE,
    ):
        side = match.group(1)
        row[f"side{side}_building"] = match.group(2).strip()
        row[f"side{side}_podium"] = match.group(3).strip()

    land_use = [
        {"type": land_type.strip(), "use": land_use_text.strip()}
        for land_type, land_use_text in re.findall(
            r"<li>\s*<b>([^<]+)</b>:\s*([^<]+)</li>", html, re.IGNORECASE
        )
    ]
    row["land_use"] = json.dumps(land_use)

    notes_match = re.search(
        (
            r"General Notes</div>(.*?)(?:<div class=\"section-header|"
            r"<div class=\"w-100 overflow-auto)"
        ),
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if notes_match:
        row["general_notes"] = " | ".join(
            note.strip() for note in re.findall(r"<li[^>]*>([^<]+)</li>", notes_match.group(1))
        )
    else:
        row["general_notes"] = ""

    coords = [
        [float(east), float(north)]
        for east, north in re.findall(
            r"<td[^>]*>\d+</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>",
            html,
            re.IGNORECASE,
        )
    ]
    row["coordinates"] = json.dumps(coords)
    return row


def project_area_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "project_name": attrs.get("ProjectName", ""),
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def subproject_area_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "project_id": attrs.get("ProjectID") or "",
        "project_name": attrs.get("ProjectName") or "",
        "entity_name": attrs.get("EntityName") or "",
        "developer_name": attrs.get("DeveloperName") or "",
        "master_project_name": attrs.get("MasterProjectName") or "",
        "original_plot_number": attrs.get("OriginalPlotNumber") or "",
        "project_logo": attrs.get("ProjectLogo") or "",
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def building_limit_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PlotNumber") or "",
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def podium_limit_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PlotNumber") or "",
        "max_height": attrs.get("MaxHeight") or "",
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def plot_feature_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    feature_type = attrs.get("FeatureType")
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PlotNumber") or "",
        "feature_type_code": feature_type if feature_type is not None else "",
        "feature_type_label": PLOT_FEATURE_LABELS.get(feature_type, ""),
        "feature_area_sqm": attrs.get("SHAPE.STArea()") or 0,
        "feature_perimeter_m": attrs.get("SHAPE.STLength()") or 0,
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def frozen_plot_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PLOT_NUMBER") or "",
        "old_plot_numbers": attrs.get("OLD_PLOT_NUMBERS") or "",
        "is_frozen": attrs.get("IS_FROZEN") or 0,
        "plot_area_sqm": attrs.get("SHAPE.STArea()") or 0,
        "plot_perimeter_m": attrs.get("SHAPE.STLength()") or 0,
        "gfa_type": attrs.get("GFA_TYPE") or "",
        "gfa_sqm_t": attrs.get("GFA_SQM_T") or "",
        "gfa_sqft_t": attrs.get("GFA_SQFT_T") or "",
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def landuse_symbol_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    geom = feature.get("geometry", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "landuse": attrs.get("LANDUSE") or "",
        "landuse_character": attrs.get("LANDUSE_CHARACTER") or "",
        "landuse_id": attrs.get("LANDUSE_ID") or "",
        "lat": geom.get("y") or 0,
        "lng": geom.get("x") or 0,
    }


def built_to_line_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PlotNumber") or "",
        "paths": json_dumps(feature.get("geometry", {}).get("paths", [])),
    }


def arcade_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PlotNumber") or "",
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }


def retail_row(feature: dict) -> dict:
    attrs = feature.get("attributes", {})
    return {
        "object_id": attrs.get("OBJECTID", ""),
        "plot_number": attrs.get("PlotNumber") or "",
        "rings": json_dumps(feature.get("geometry", {}).get("rings", [])),
    }
