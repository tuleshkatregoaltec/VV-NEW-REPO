import logging
from typing import Any

from pydantic_ai import Agent, RunContext

from app.clickhouse import query
from app.core.openrouter import create_openrouter_model

logger = logging.getLogger(__name__)

model = create_openrouter_model()

# Define agent
agent = Agent(
    model,
    system_prompt=(
        "You are Vitevue AI, an expert Real Estate Analyst specializing in Dubai real estate markets. "
        "You have access to predefined database queries that can retrieve comprehensive real estate data.\n\n"
        "## Available Data and Tools\n\n"
        "You have access to predefined, parameterized database queries that can retrieve information from these data categories:\n"
        "- Transaction records (sales data, prices, locations, dates)\n"
        "- Rental contracts (rental prices, terms, locations)\n"
        "- Development projects (new construction, developers, timelines)\n"
        "- Developer information (company profiles, track records)\n\n"
        "Important: You work with a set of predefined queries with specific parameters. You select the appropriate queries "
        "and provide the necessary parameters (such as date ranges, location filters, price ranges, etc.) based on the user's question. "
        "You cannot construct arbitrary SQL queries, but you have access to a comprehensive set of query templates designed to answer real estate questions.\n\n"
        "## Core Principles\n\n"
        "**Scope Restriction**: You are specifically designed to answer questions about the Dubai real estate market. "
        "If a user asks about topics outside of this market (questions about other markets, general non-real-estate topics, or unrelated subjects), "
        "politely decline and redirect them to ask about real estate in Dubai.\n\n"
        "**Data Analysis Philosophy**: Always prefer aggregate analysis over fetching raw data records. When you use your database tools, "
        "select queries that return summary statistics, rankings, trends, and calculated metrics rather than individual records.\n\n"
        "**Query Strategy for Complex Questions**: When questions require multiple data points, you may need to chain together multiple query calls. "
        "Use the results from one query to inform the parameters of the next. For example, you might first query to identify the top performing neighborhoods, "
        "then query again for detailed metrics on those specific neighborhoods.\n\n"
        "**Tool Usage in Responses**: Focus on what insights the data reveals, not on the mechanics of how you retrieved it. "
        "In your final response to the user, avoid explicitly naming tool functions, describing technical query details, or explaining which queries you selected. "
        "Simply present the insights as if you have natural expertise in this market.\n\n"
        "## Formatting Rules\n\n"
        "Use only these markdown elements — nothing else:\n"
        "- **Bold** for key metrics and numbers\n"
        "- *Italic* for area names or secondary emphasis\n"
        "- Bullet lists and numbered lists for multiple data points or rankings\n"
        "- Blockquotes for notable highlights or important caveats\n\n"
        "Do NOT use headers (#, ##, ###), tables, horizontal rules, or any other markdown. "
        "Keep responses flowing and conversational.\n\n"
        "## Response Format\n\n"
        "Your response should be concise, professional, and data-focused. Structure it to include:\n\n"
        '- **Specific numbers** from your analysis with clear units (e.g., "Average sale price of AED 1.2M", "15% year-over-year increase")\n'
        '- **Context** for those numbers (e.g., "based on 347 transactions in Q1 2024", "across Dubai Marina")\n'
        '- **Trends and patterns** with supporting data (e.g., "Prices have been rising steadily since...", "Premium developments are concentrated in...")\n'
        '- **Data-driven recommendations** when appropriate (e.g., "Based on rental yields of X%, consider areas like...")\n\n'
        "Example response structure:\n\n"
        "Based on analysis of [X] transactions over [time period], the average price in [area] is [number] [currency] per square foot. "
        "This represents a [percentage] change compared to [comparison period].\n\n"
        "Key trends include [trend description with supporting numbers]. [Area A] shows particularly strong performance with [specific metric], "
        "while [Area B] demonstrates [different pattern] with [supporting data].\n\n"
        "For investors seeking [criteria mentioned in query], I recommend focusing on [areas/property types] because [data-driven reasoning with specific numbers]."
    ),
)


@agent.tool
async def get_market_pulse(
    ctx: RunContext[None], area: str, period_days: int = 90
) -> dict[str, Any]:
    """Get vital market statistics for a specific area.

    Returns aggregate metrics including median price, average yield, transaction volume,
    and price trends for the specified area and time period.

    Args:
        ctx: Runtime context (unused)
        area: Area name (e.g., "Dubai Marina", "Downtown Dubai")
        period_days: Analysis period in days (default: 90)

    Returns:
        Dictionary with price, yield, volume, and trend data
    """
    sql = """
    SELECT
        count(*) as transaction_count,
        round(median(actual_worth), 0) as median_price,
        round(avg(actual_worth), 0) as avg_price,
        round(median(actual_area), 1) as median_area_sqft,
        round(median(actual_worth / actual_area), 0) as median_price_per_sqft,
        min(instance_date) as period_start,
        max(instance_date) as period_end
    FROM ch_transactions
    WHERE
        area_name_en = {area:String}
        AND instance_date >= today() - {period_days:Int32}
        AND actual_worth > 0
        AND actual_area > 0
    """

    try:
        rows = await query(sql, {"area": area, "period_days": period_days})

        if not rows:
            return {
                "success": False,
                "error": f"No data found for area '{area}' in the last {period_days} days",
            }

        row = rows[0]
        return {
            "success": True,
            "area": area,
            "period_days": period_days,
            "transaction_count": row["transaction_count"],
            "median_price_aed": row["median_price"],
            "avg_price_aed": row["avg_price"],
            "median_area_sqft": row["median_area_sqft"],
            "median_price_per_sqft_aed": row["median_price_per_sqft"],
            "period_start": str(row["period_start"]),
            "period_end": str(row["period_end"]),
        }
    except Exception as e:
        logger.exception(f"Error executing get_market_pulse for area {area}")
        return {"success": False, "error": str(e)}


@agent.tool
async def rank_areas(
    ctx: RunContext[None],
    metric: str = "volume",
    limit: int = 5,
    period_days: int = 90,
) -> dict[str, Any]:
    """Rank top areas by a specific metric.

    Args:
        ctx: Runtime context (unused)
        metric: Ranking metric - "volume" (transaction count), "price" (median price),
                or "growth" (price change percentage)
        limit: Number of top areas to return (default: 5)
        period_days: Analysis period in days (default: 90)

    Returns:
        List of top areas with their respective metrics
    """
    if metric == "volume":
        sql = """
        SELECT
            area_name_en as area,
            count(*) as transaction_count,
            round(median(actual_worth), 0) as median_price
        FROM ch_transactions
        WHERE
            instance_date >= today() - {period_days:Int32}
            AND actual_worth > 0
            AND area_name_en != ''
        GROUP BY area_name_en
        ORDER BY transaction_count DESC
        LIMIT {limit:Int32}
        """
    elif metric == "price":
        sql = """
        SELECT
            area_name_en as area,
            round(median(actual_worth), 0) as median_price,
            count(*) as transaction_count
        FROM ch_transactions
        WHERE
            instance_date >= today() - {period_days:Int32}
            AND actual_worth > 0
            AND area_name_en != ''
        GROUP BY area_name_en
        HAVING transaction_count >= 10
        ORDER BY median_price DESC
        LIMIT {limit:Int32}
        """
    elif metric == "growth":
        # Compare current period vs previous period
        sql = """
        WITH
            current_period AS (
                SELECT
                    area_name_en as area,
                    median(actual_worth) as current_median
                FROM ch_transactions
                WHERE
                    instance_date >= today() - {period_days:Int32}
                    AND actual_worth > 0
                    AND area_name_en != ''
                GROUP BY area_name_en
                HAVING count(*) >= 10
            ),
            previous_period AS (
                SELECT
                    area_name_en as area,
                    median(actual_worth) as previous_median
                FROM ch_transactions
                WHERE
                    instance_date >= today() - {period_days:Int32} * 2
                    AND instance_date < today() - {period_days:Int32}
                    AND actual_worth > 0
                    AND area_name_en != ''
                GROUP BY area_name_en
                HAVING count(*) >= 10
            )
        SELECT
            c.area,
            round(c.current_median, 0) as current_median_price,
            round(p.previous_median, 0) as previous_median_price,
            round(((c.current_median - p.previous_median) / p.previous_median) * 100, 2) as growth_percentage
        FROM current_period c
        INNER JOIN previous_period p ON c.area = p.area
        ORDER BY growth_percentage DESC
        LIMIT {limit:Int32}
        """
    else:
        return {
            "success": False,
            "error": f"Invalid metric '{metric}'. Use 'volume', 'price', or 'growth'",
        }

    try:
        rows = await query(sql, {"period_days": period_days, "limit": limit})

        if not rows:
            return {
                "success": False,
                "error": f"No data found for metric '{metric}' in the last {period_days} days",
            }

        areas = []
        for row in rows:
            if metric == "volume":
                areas.append(
                    {
                        "area": row["area"],
                        "transaction_count": row["transaction_count"],
                        "median_price_aed": row["median_price"],
                    }
                )
            elif metric == "price":
                areas.append(
                    {
                        "area": row["area"],
                        "median_price_aed": row["median_price"],
                        "transaction_count": row["transaction_count"],
                    }
                )
            elif metric == "growth":
                areas.append(
                    {
                        "area": row["area"],
                        "current_median_price_aed": row["current_median_price"],
                        "previous_median_price_aed": row["previous_median_price"],
                        "growth_percentage": row["growth_percentage"],
                    }
                )

        return {
            "success": True,
            "metric": metric,
            "period_days": period_days,
            "top_areas": areas,
        }
    except Exception as e:
        logger.exception(f"Error executing rank_areas for metric {metric}")
        return {"success": False, "error": str(e)}


@agent.tool
async def get_similar_projects(
    ctx: RunContext[None], project_name: str, limit: int = 5
) -> dict[str, Any]:
    """Find similar projects based on attributes.

    Uses ClickHouse projections to efficiently search for comparable projects
    based on property characteristics, location, and developer.

    Args:
        ctx: Runtime context (unused)
        project_name: Name of the reference project
        limit: Number of similar projects to return (default: 5)

    Returns:
        List of similar projects with comparison metrics
    """
    # First, get the reference project details
    ref_sql = """
    SELECT
        master_project_en,
        area_name_en,
        property_type_en,
        round(median(actual_worth), 0) as median_price,
        round(median(actual_area), 1) as median_area,
        count(*) as transaction_count
    FROM ch_transactions
    WHERE
        master_project_en ILIKE {project_name:String}
        AND actual_worth > 0
        AND actual_area > 0
        AND instance_date >= today() - 365
    GROUP BY master_project_en, area_name_en, property_type_en
    LIMIT 1
    """

    try:
        ref_rows = await query(ref_sql, {"project_name": f"%{project_name}%"})

        if not ref_rows:
            return {
                "success": False,
                "error": f"No data found for project '{project_name}'",
            }

        ref_row = ref_rows[0]
        ref_project = ref_row["master_project_en"]
        ref_area = ref_row["area_name_en"]
        ref_type = ref_row["property_type_en"]
        ref_price = ref_row["median_price"]
        ref_area_sqft = ref_row["median_area"]

        # Find similar projects
        similar_sql = """
        SELECT
            master_project_en,
            area_name_en,
            property_type_en,
            round(median(actual_worth), 0) as median_price,
            round(median(actual_area), 1) as median_area,
            count(*) as transaction_count,
            abs(median(actual_worth) - {ref_price:Float64}) as price_diff
        FROM ch_transactions
        WHERE
            master_project_en != {ref_project:String}
            AND property_type_en = {ref_type:String}
            AND actual_worth > 0
            AND actual_area > 0
            AND instance_date >= today() - 365
            AND master_project_en != ''
        GROUP BY master_project_en, area_name_en, property_type_en
        HAVING transaction_count >= 5
        ORDER BY price_diff ASC
        LIMIT {limit:Int32}
        """

        similar_rows = await query(
            similar_sql,
            {
                "ref_price": ref_price,
                "ref_project": ref_project,
                "ref_type": ref_type,
                "limit": limit,
            },
        )

        similar_projects = []
        for row in similar_rows:
            similar_projects.append(
                {
                    "project": row["master_project_en"],
                    "area": row["area_name_en"],
                    "property_type": row["property_type_en"],
                    "median_price_aed": row["median_price"],
                    "median_area_sqft": row["median_area"],
                    "transaction_count": row["transaction_count"],
                    "price_difference_aed": row["price_diff"],
                }
            )

        return {
            "success": True,
            "reference_project": {
                "name": ref_project,
                "area": ref_area,
                "property_type": ref_type,
                "median_price_aed": ref_price,
                "median_area_sqft": ref_area_sqft,
            },
            "similar_projects": similar_projects,
        }
    except Exception as e:
        logger.exception(f"Error executing get_similar_projects for {project_name}")
        return {"success": False, "error": str(e)}
