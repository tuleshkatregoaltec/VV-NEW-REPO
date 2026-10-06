"""Holocron entity alias admin dashboard.

Usage:
    uv run --extra admin streamlit run apps/entity_admin/app.py

Reads CLICKHOUSE_* and DAGSTER_WEBSERVER_URL from the environment.
If a .env file is present in the project root it is auto-loaded.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap — load .env so the app works when run directly (not via just env)
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

_ENTITIES_DIR = Path(__file__).parent.parent.parent / "holocron" / "lib" / "entities"
_AREA_ALIASES_FILE = _ENTITIES_DIR / "area_aliases.yaml"
_DEVELOPER_BRANDS_FILE = _ENTITIES_DIR / "developer_brands.yaml"

_CH_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
_CH_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
_CH_USER = os.getenv("CLICKHOUSE_USER", "default")
_CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
_CH_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "default")
_DAGSTER_URL = os.getenv("DAGSTER_WEBSERVER_URL", "http://localhost:3000")

# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------


@st.cache_resource
def _ch():
    import clickhouse_connect  # noqa: PLC0415

    return clickhouse_connect.get_client(
        host=_CH_HOST,
        port=_CH_PORT,
        username=_CH_USER,
        password=_CH_PASSWORD,
        database=_CH_DATABASE,
    )


@st.cache_data(ttl=300, show_spinner="Querying ClickHouse…")
def _query(sql: str) -> pd.DataFrame:
    result = _ch().query(sql)
    return pd.DataFrame(result.result_rows, columns=result.column_names)


def _ch_ok() -> bool:
    try:
        _ch().command("SELECT 1")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

_AREA_HEADER = """\
# Canonical area name aliases for Dubai real estate data.
#
# Keys are search terms (abbreviations, alternate spellings).
# Values are the canonical DLD English area names stored in silver tables.
#
# Used by the API layer to expand user search input.
# Managed via apps/entity_admin."""

_DEV_HEADER = """\
# Developer brand name mappings for Dubai real estate data.
#
# Keys are the raw legal entity names as they appear in DLD data.
# Values are the canonical brand names used for presentation.
#
# Managed via apps/entity_admin."""


def _load(path: Path) -> dict[str, str]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _save(path: Path, data: dict[str, str], header: str) -> None:
    with open(path, "w") as f:
        f.write(header + "\n\n")
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=True)


def _bust() -> None:
    """Clear query cache after a save so counts update immediately."""
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# Page: Review  (default landing page)
# ---------------------------------------------------------------------------


def _page_review() -> None:
    st.header("Review")
    st.caption(
        "This is your starting point. The table below shows developer names present in your "
        "bronze data that don't yet have a canonical brand mapping. Work through them top-to-bottom "
        "— highest project count first."
    )

    brands = _load(_DEVELOPER_BRANDS_FILE)
    aliases = _load(_AREA_ALIASES_FILE)

    # --- Summary metrics ---
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Area alias entries", len(aliases))
    col_b.metric("Developer brands mapped", len(set(brands.values())))

    try:
        dev_df = _query("""
            SELECT developer_en, count() AS projects
            FROM dld_od_projects_bronze
            WHERE developer_en != ''
            GROUP BY developer_en
            ORDER BY projects DESC
            LIMIT 500
        """)
        unmapped_df = dev_df[~dev_df["developer_en"].isin(set(brands.keys()))].reset_index(
            drop=True
        )
        col_c.metric(
            "Unmapped developers",
            len(unmapped_df),
            delta=f"-{len(unmapped_df)}" if unmapped_df.empty else None,
            delta_color="inverse",
        )
        ch_ok = True
    except Exception as exc:
        col_c.metric("Unmapped developers", "–")
        unmapped_df = pd.DataFrame()
        ch_ok = False
        _show_ch_error(exc)

    st.divider()

    # --- Unmapped developer workflow ---
    st.subheader("Unmapped developer names")

    if not ch_ok:
        return

    if unmapped_df.empty:
        st.success("Every developer name in bronze has a brand mapping. Nothing to do here.")
        return

    st.dataframe(
        unmapped_df.rename(columns={"developer_en": "DLD legal name", "projects": "projects"}),
        width="stretch",
        height=min(400, 35 + len(unmapped_df) * 35),
    )

    st.markdown("**Add a brand mapping**")
    st.caption(
        "Pick a name from the list above. If the entity is noise (a test record, "
        "a one-off developer with 1 project), you can map it to a placeholder like "
        "`'Other'` or just leave it."
    )

    with st.form("quick_map", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            dld_name = st.selectbox(
                "DLD legal name",
                options=unmapped_df["developer_en"].tolist(),
                help="Sorted by project count — work top-to-bottom.",
            )
        with col2:
            brand_name = st.text_input(
                "Canonical brand name",
                placeholder="e.g. Emaar",
                help="Use the publicly recognised brand name.",
            )
        if st.form_submit_button("Save mapping", type="primary"):
            if brand_name.strip():
                brands[dld_name] = brand_name.strip()
                _save(_DEVELOPER_BRANDS_FILE, brands, _DEV_HEADER)
                _bust()
                st.success(f"Saved: **{dld_name}** → **{brand_name.strip()}**")
                st.rerun()
            else:
                st.warning("Enter a brand name before saving.")


# ---------------------------------------------------------------------------
# Page: Aliases  (area aliases + developer brands in tabs)
# ---------------------------------------------------------------------------


def _page_aliases() -> None:
    st.header("Aliases")

    tab_area, tab_dev = st.tabs(["Area Aliases", "Developer Brands"])

    with tab_area:
        st.caption(
            "Keys are user search terms (JVC, downtown, etc.). "
            "Values are canonical DLD area names already stored in silver tables. "
            "Used by the API to expand user input — not part of the pipeline."
        )
        aliases = _load(_AREA_ALIASES_FILE)

        by_canonical: dict[str, list[str]] = {}
        for alias, canonical in aliases.items():
            by_canonical.setdefault(canonical, []).append(alias)

        df = pd.DataFrame(
            [
                {"Canonical name (DLD)": c, "Search terms": ", ".join(sorted(vs))}
                for c, vs in sorted(by_canonical.items())
            ]
        )

        q = st.text_input("Filter", placeholder="Search…", key="area_q")
        if q:
            mask = df["Canonical name (DLD)"].str.contains(q, case=False, na=False) | df[
                "Search terms"
            ].str.contains(q, case=False, na=False)
            df = df[mask]
        st.dataframe(df, width="stretch", height=320)
        st.caption(f"{len(aliases):,} alias entries across {len(by_canonical):,} canonical names")

        st.divider()
        col_add, col_del = st.columns(2)
        with col_add:
            st.markdown("**Add**")
            with st.form("add_area", clear_on_submit=True):
                new_alias = st.text_input("Search term", placeholder="e.g. jvc or JVC")
                new_canonical = st.text_input(
                    "Canonical DLD name", placeholder="e.g. Jumeirah Village Circle"
                )
                if st.form_submit_button("Add"):
                    a, c = new_alias.strip(), new_canonical.strip()
                    if a and c:
                        aliases[a] = c
                        _save(_AREA_ALIASES_FILE, aliases, _AREA_HEADER)
                        st.success(f"{a!r} → {c!r}")
                        st.rerun()
                    else:
                        st.warning("Both fields required.")

        with col_del:
            st.markdown("**Remove**")
            if aliases:
                to_del = st.selectbox(
                    "Alias to remove", sorted(aliases.keys()), key="area_del_sel"
                )
                st.caption(f"→ {aliases.get(to_del, '')}")
                if st.button("Remove", type="secondary", key="area_del_btn"):
                    del aliases[to_del]
                    _save(_AREA_ALIASES_FILE, aliases, _AREA_HEADER)
                    st.success(f"Removed {to_del!r}")
                    st.rerun()

    with tab_dev:
        st.caption(
            "Maps raw DLD legal entity names to canonical brand names. "
            "Add new mappings from the **Review** page — use this tab to browse or remove existing ones."
        )
        brands = _load(_DEVELOPER_BRANDS_FILE)

        by_brand: dict[str, list[str]] = {}
        for legal, brand in brands.items():
            by_brand.setdefault(brand, []).append(legal)

        df_b = pd.DataFrame(
            [
                {"Brand": b, "DLD legal names": ", ".join(sorted(ls))}
                for b, ls in sorted(by_brand.items())
            ]
        )

        q2 = st.text_input("Filter", placeholder="Search…", key="dev_q")
        if q2:
            mask2 = df_b["Brand"].str.contains(q2, case=False, na=False) | df_b[
                "DLD legal names"
            ].str.contains(q2, case=False, na=False)
            df_b = df_b[mask2]
        st.dataframe(df_b, width="stretch", height=320)
        st.caption(f"{len(brands):,} legal name entries across {len(by_brand):,} brands")

        st.divider()
        col_add2, col_del2 = st.columns(2)
        with col_add2:
            st.markdown("**Add**")
            with st.form("add_brand", clear_on_submit=True):
                dld_n = st.text_input(
                    "DLD legal name", placeholder="e.g. EMAAR DEVELOPMENT (P.J.S.C)"
                )
                brand_n = st.text_input("Brand name", placeholder="e.g. Emaar")
                if st.form_submit_button("Add"):
                    d, b = dld_n.strip(), brand_n.strip()
                    if d and b:
                        brands[d] = b
                        _save(_DEVELOPER_BRANDS_FILE, brands, _DEV_HEADER)
                        st.success(f"{d!r} → {b!r}")
                        st.rerun()
                    else:
                        st.warning("Both fields required.")

        with col_del2:
            st.markdown("**Remove**")
            if brands:
                to_del2 = st.selectbox(
                    "DLD name to remove", sorted(brands.keys()), key="dev_del_sel"
                )
                st.caption(f"→ {brands.get(to_del2, '')}")
                if st.button("Remove", type="secondary", key="dev_del_btn"):
                    del brands[to_del2]
                    _save(_DEVELOPER_BRANDS_FILE, brands, _DEV_HEADER)
                    st.success(f"Removed {to_del2!r}")
                    st.rerun()


# ---------------------------------------------------------------------------
# Page: Silver Quality
# ---------------------------------------------------------------------------


def _page_silver() -> None:
    st.header("Silver Quality")
    st.caption("Spot-check normalised data in the silver tables.")

    table = st.selectbox("Table", ["silver_transactions", "silver_rent_contracts"])

    col1, col2 = st.columns([3, 1])
    with col1:
        area_q = st.text_input("Filter by area_name_en", placeholder="e.g. Business Bay")
    with col2:
        limit = int(st.number_input("Limit", min_value=10, max_value=500, value=100, step=10))

    where = ""
    if area_q.strip():
        safe = area_q.replace("'", "''")
        where = f"WHERE lower(area_name_en) LIKE lower('%{safe}%')"

    sql = f"SELECT * FROM `{table}` {where} LIMIT {limit}"

    if st.button("Run query"):
        try:
            df = _query(sql)
            st.dataframe(df, width="stretch")
            st.caption(f"{len(df):,} rows")
        except Exception as exc:
            _show_ch_error(exc)

    with st.expander("SQL"):
        st.code(sql, language="sql")


# ---------------------------------------------------------------------------
# Page: Trigger
# ---------------------------------------------------------------------------


def _page_trigger() -> None:
    st.header("Trigger Silver Refresh")
    st.markdown(
        "Launches a Dagster job via the GraphQL API. "
        "Run this after saving new alias changes to rebuild the silver tables."
    )

    dagster_url = st.text_input("Dagster webserver URL", value=_DAGSTER_URL)
    job = st.selectbox(
        "Job",
        ["silver_refresh", "silver_transactions_refresh", "silver_rent_contracts_refresh"],
    )

    if st.button("Launch job", type="primary"):
        try:
            nodes = _gql(
                dagster_url,
                "{ repositoriesOrError { ... on RepositoryConnection { nodes { name location { name } } } } }",
            )["data"]["repositoriesOrError"]["nodes"]

            if not nodes:
                st.error("No repositories found — is the Dagster webserver running?")
                return

            node = nodes[0]
            result = _gql(
                dagster_url,
                """
                mutation L($p: ExecutionParams!) {
                  launchRun(executionParams: $p) {
                    __typename
                    ... on LaunchRunSuccess { run { runId } }
                    ... on PythonError { message }
                    ... on RunConfigValidationInvalid { errors { message } }
                  }
                }
                """,
                {
                    "p": {
                        "selector": {
                            "repositoryLocationName": node["location"]["name"],
                            "repositoryName": node["name"],
                            "jobName": job,
                        },
                        "runConfigData": {},
                    }
                },
            )
            launch = result["data"]["launchRun"]
            if launch["__typename"] == "LaunchRunSuccess":
                run_id = launch["run"]["runId"]
                st.success(f"Launched — run ID: `{run_id}`")
                st.link_button("Open in Dagster UI", f"{dagster_url}/runs/{run_id}")
            else:
                st.error(f"Launch failed: {launch.get('message', launch)}")
        except Exception as exc:
            st.error(f"Error communicating with Dagster: {exc}")

    with st.expander("Manual trigger (CLI)"):
        st.code(f"uv run dagster job execute -j {job}", language="bash")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _show_ch_error(exc: Exception) -> None:
    if "Connection refused" in str(exc) or "Max retries" in str(exc):
        st.error(
            f"Cannot reach ClickHouse at `{_CH_HOST}:{_CH_PORT}`. "
            "Make sure the stack is running and `CLICKHOUSE_*` env vars are set. "
            "If running locally, source your `.env` file first."
        )
    else:
        st.error(f"ClickHouse error: {exc}")


def _gql(url: str, query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        f"{url}/graphql",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

_PAGES = {
    "Review": _page_review,
    "Aliases": _page_aliases,
    "Silver Quality": _page_silver,
    "Trigger Refresh": _page_trigger,
}

st.set_page_config(page_title="Entity Admin — Holocron", layout="wide")

with st.sidebar:
    st.title("Entity Admin")
    st.caption("Holocron data quality dashboard")
    page = st.radio("Navigate", list(_PAGES.keys()), label_visibility="collapsed")
    st.divider()
    st.caption(f"ClickHouse: {_CH_HOST}:{_CH_PORT}/{_CH_DATABASE}")

_PAGES[page]()
