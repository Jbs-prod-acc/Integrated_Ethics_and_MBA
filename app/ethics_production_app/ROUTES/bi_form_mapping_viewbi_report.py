import json
import math
import re
from collections import OrderedDict
from datetime import date, datetime, timezone, time
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from uuid import UUID

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

SAVED_CONFIGURATION_TABLE = (
    "public.bi_dashboard_saved_configurations_dashbooards"
)

DEFAULT_SCHEMA = "public"
DEFAULT_TABLE_ROW_LIMIT = 200
MAX_FILTER_OPTIONS = 250



def build_page_links(
    current_page: int,
    total_pages: int,
    window: int = 7,
) -> List[Optional[int]]:
    """Build compact pagination links; None represents an ellipsis."""
    current_page = max(1, int(current_page or 1))
    total_pages = max(1, int(total_pages or 1))

    if total_pages <= window + 2:
        return list(range(1, total_pages + 1))

    half = max(1, window // 2)
    start = max(1, current_page - half)
    end = min(total_pages, start + window - 1)
    start = max(1, end - window + 1)

    pages: List[Optional[int]] = []

    if start > 1:
        pages.append(1)
        if start > 2:
            pages.append(None)

    pages.extend(range(start, end + 1))

    if end < total_pages:
        if end < total_pages - 1:
            pages.append(None)
        pages.append(total_pages)

    return pages


# ============================================================
# BASIC HELPERS
# ============================================================

def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    return str(value)


def _normalise_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    return {}


def _safe_integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)

def _mapping_value(
    values: Optional[Mapping[str, Any]],
    key: str,
    default: Any = "",
) -> Any:
    """
    Safely read a value from:

    - Flask request.args
    - Flask request.form
    - MultiDict
    - normal dictionaries
    """

    if not values:
        return default

    if hasattr(values, "getlist"):
        submitted_values = values.getlist(key)

        for submitted_value in submitted_values:
            if _clean_text(submitted_value):
                return submitted_value

    value = values.get(key, default)

    if isinstance(value, (list, tuple, set)):
        for item in value:
            if _clean_text(item):
                return item

        return default

    return value


def _safe_pagination_token(value: Any) -> str:
    """
    Convert dynamic page and visual IDs into safe URL parameter names.
    """

    cleaned = _clean_text(value)

    if not cleaned:
        cleaned = "table"

    cleaned = re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        cleaned,
    )

    cleaned = re.sub(
        r"_+",
        "_",
        cleaned,
    ).strip("_")

    return cleaned.lower() or "table"


def _normalise_json_array(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    return []


def _split_qualified_table_name(
    dynamic_table_name: str,
) -> Tuple[str, str]:
    cleaned = _clean_text(dynamic_table_name)

    if not cleaned:
        raise ValueError(
            "The selected form does not have a dynamic table configured."
        )

    parts = [part.strip() for part in cleaned.split(".") if part.strip()]

    if len(parts) == 1:
        schema_name = DEFAULT_SCHEMA
        table_name = parts[0]
    elif len(parts) == 2:
        schema_name, table_name = parts
    else:
        raise ValueError(
            f'Invalid dynamic table name "{cleaned}".'
        )

    identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

    if not identifier_pattern.fullmatch(schema_name):
        raise ValueError(
            f'Invalid dynamic table schema "{schema_name}".'
        )

    if not identifier_pattern.fullmatch(table_name):
        raise ValueError(
            f'Invalid dynamic table name "{table_name}".'
        )

    return schema_name, table_name


def _split_qualified_object_name(
    object_name: str,
) -> Tuple[str, str]:
    parts = object_name.split(".", 1)

    if len(parts) != 2:
        return DEFAULT_SCHEMA, object_name

    return parts[0], parts[1]


def _table_identifier(
    schema_name: str,
    table_name: str,
) -> sql.Composed:
    return sql.SQL("{}.{}").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )



def _month_order_from_expression(
    value_expression: sql.Composable,
) -> sql.Composable:
    """
    Return a PostgreSQL CASE expression that orders a text expression
    from January through December.

    Supported values:
    - January through December
    - Jan through Dec
    - 1 through 12
    - 01 through 12
    """
    normalised_value = sql.SQL(
        "LOWER(BTRIM(COALESCE(({})::text, '')))"
    ).format(value_expression)

    return sql.SQL(
        """
        CASE
            WHEN {value} IN ('january', 'jan', '1', '01') THEN 1
            WHEN {value} IN ('february', 'feb', '2', '02') THEN 2
            WHEN {value} IN ('march', 'mar', '3', '03') THEN 3
            WHEN {value} IN ('april', 'apr', '4', '04') THEN 4
            WHEN {value} IN ('may', '5', '05') THEN 5
            WHEN {value} IN ('june', 'jun', '6', '06') THEN 6
            WHEN {value} IN ('july', 'jul', '7', '07') THEN 7
            WHEN {value} IN ('august', 'aug', '8', '08') THEN 8
            WHEN {value} IN ('september', 'sep', 'sept', '9', '09') THEN 9
            WHEN {value} IN ('october', 'oct', '10') THEN 10
            WHEN {value} IN ('november', 'nov', '11') THEN 11
            WHEN {value} IN ('december', 'dec', '12') THEN 12
            ELSE 99
        END
        """
    ).format(value=normalised_value)


def _month_order_expression(
    column_name: str,
) -> sql.Composable:
    """
    Convenience wrapper for a physical table column.
    """
    return _month_order_from_expression(
        sql.Identifier(column_name)
    )


def _is_month_column(
    column_name: Any,
) -> bool:
    """
    Identify dynamic Month columns without depending on exact casing.
    """
    cleaned = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_text(column_name).lower(),
    ).strip("_")

    return cleaned in {
        "month",
        "months",
        "month_name",
        "monthname",
    }


# ============================================================
# SAVED VISUAL CONFIGURATION NORMALISATION
# ============================================================

def _first_configured_value(
    visual: Mapping[str, Any],
    *keys: str,
) -> Any:
    """
    Return the first non-empty value found under any supported key.

    This keeps older and newer saved dashboard configurations
    compatible with the result renderer.
    """
    for key in keys:
        if key not in visual:
            continue

        value = visual.get(key)

        if isinstance(value, str):
            if value.strip():
                return value
            continue

        if value not in (None, "", [], {}, ()):
            return value

    return ""


def _normalise_column_token(
    value: Any,
) -> str:
    """
    Convert saved labels and physical column names into a comparable
    token.

    Examples:
        Tenant Name -> tenantname
        tenant_name -> tenantname
        TENANTS     -> tenants
    """
    return re.sub(
        r"[^a-z0-9]+",
        "",
        _clean_text(value).lower(),
    )


def _singular_column_token(
    value: Any,
) -> str:
    """
    Apply a small singularisation rule used only for dynamic column
    matching.
    """
    token = _normalise_column_token(value)

    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"

    if token.endswith("ses") and len(token) > 3:
        return token[:-2]

    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]

    return token


def _resolve_column_name(
    configured_name: Any,
    valid_columns: Sequence[str],
) -> str:
    """
    Resolve a saved column reference to its actual physical database
    column.

    Matching supports:
    - exact names
    - case differences
    - spaces versus underscores
    - qualified names
    - singular/plural variants
    - labels such as Tenants matching tenant or tenant_name
    """
    cleaned = _clean_text(configured_name)

    if not cleaned:
        return ""

    if "::" in cleaned:
        cleaned = cleaned.split("::", 1)[-1].strip()

    if "." in cleaned:
        cleaned = cleaned.rsplit(".", 1)[-1].strip()

    if cleaned in valid_columns:
        return cleaned

    lowercase_lookup = {
        _clean_text(column).lower(): column
        for column in valid_columns
    }

    exact_case_insensitive = lowercase_lookup.get(
        cleaned.lower()
    )

    if exact_case_insensitive:
        return exact_case_insensitive

    configured_token = _normalise_column_token(cleaned)
    configured_singular = _singular_column_token(cleaned)

    token_lookup = {
        _normalise_column_token(column): column
        for column in valid_columns
    }

    singular_lookup = {
        _singular_column_token(column): column
        for column in valid_columns
    }

    if configured_token in token_lookup:
        return token_lookup[configured_token]

    if configured_singular in singular_lookup:
        return singular_lookup[configured_singular]

    # Prefer semantic prefix matches such as:
    # tenants -> tenant_name
    # company -> company_name
    # department -> department_name
    candidates = []

    for position, column in enumerate(valid_columns):
        column_token = _normalise_column_token(column)
        column_singular = _singular_column_token(column)

        score = 0

        if (
            configured_singular
            and column_singular.startswith(configured_singular)
        ):
            score = 100

        elif (
            configured_singular
            and configured_singular.startswith(column_singular)
        ):
            score = 90

        elif (
            configured_singular
            and configured_singular in column_singular
        ):
            score = 80

        elif (
            configured_token
            and configured_token in column_token
        ):
            score = 70

        if score:
            candidates.append(
                (
                    -score,
                    len(column_token),
                    position,
                    column,
                )
            )

    if candidates:
        candidates.sort()
        return candidates[0][3]

    return ""


def _normalise_visual_type(value: Any) -> str:
    """
    Convert all supported labels and historical values into the
    internal result-view visual type.
    """
    cleaned = _clean_text(value).lower()

    cleaned = re.sub(
        r"[^a-z0-9]+",
        "_",
        cleaned,
    ).strip("_")

    aliases = {
        "data_table": "table",
        "datatable": "table",
        "table_visual": "table",

        "table_total": "table_total",
        "tabletotal": "table_total",
        "matrix_table": "table_total",
        "pivot_table": "table_total",

        "split_data_table": "split_table",
        "splitdatatable": "split_table",
        "split_table_visual": "split_table",
        "splittable": "split_table",

        "split_table_tracking": "split_table_tracking",
        "split_table_with_tracking": "split_table_tracking",
        "split_data_table_tracking": "split_table_tracking",
        "splitdatatabletracking": "split_table_tracking",
        "splittabletracking": "split_table_tracking",

        "split_table_tracking_distinct": "split_table_tracking_distinct",
        "split_table_with_tracking_distinct": "split_table_tracking_distinct",
        "split_data_table_tracking_distinct": "split_table_tracking_distinct",
        "splitdatatabletrackingdistinct": "split_table_tracking_distinct",
        "splittabletrackingdistinct": "split_table_tracking_distinct",

        "split_table_tracking_distinct_graphics": "split_table_tracking_distinct_graphics",
        "split_table_with_tracking_distinct_graphics": "split_table_tracking_distinct_graphics",
        "split_data_table_tracking_distinct_graphics": "split_table_tracking_distinct_graphics",
        "splitdatatabletrackingdistinctgraphics": "split_table_tracking_distinct_graphics",
        "splittabletrackingdistinctgraphics": "split_table_tracking_distinct_graphics",

        "line_chart": "line",
        "linechart": "line",

        "area_chart": "area",
        "areachart": "area",

        "bar_chart": "bar",
        "barchart": "bar",

        "column_chart": "column",
        "columnchart": "column",

        "grouped_column_chart": "grouped_column",
        "groupedcolumnchart": "grouped_column",
        "clustered_column_chart": "grouped_column",
        "clusteredcolumnchart": "grouped_column",

        "stacked_bar_chart": "stacked_bar",
        "stackedbarchart": "stacked_bar",

        "stacked_column_chart": "stacked_column",
        "stackedcolumnchart": "stacked_column",

        "line_and_column_chart": "combo",
        "line_column_chart": "combo",
        "combo_chart": "combo",
        "combination_chart": "combo",

        "donut_chart": "donut",
        "doughnut": "donut",
        "doughnut_chart": "donut",

        "pie_chart": "pie",
        "funnel_chart": "funnel",
        "treemap_chart": "treemap",
        "heat_map": "heatmap",
        "heatmap_chart": "heatmap",
        "waterfall_chart": "waterfall",
        "radar_chart": "radar",
        "gauge_chart": "gauge",
        "kpi_card": "kpi",
    }

    return aliases.get(cleaned, cleaned)


def _resolve_split_column(
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
) -> str:
    """
    Resolve the configured Split Data Table column.

    An explicitly configured value always takes priority. Month is
    never substituted merely because another configured value was
    written differently.
    """
    configured_value = _first_configured_value(
        visual,
        "splitColumn",
        "split_column",
        "splitBy",
        "split_by",
        "splitField",
        "split_field",
        "splitOn",
        "split_on",
        "groupBy",
        "group_by",
        "partitionColumn",
        "partition_column",
    )

    if _clean_text(configured_value):
        resolved = _resolve_column_name(
            configured_value,
            valid_columns,
        )

        if resolved:
            return resolved

        # Keep looking in selected table columns for a semantic match,
        # but do not silently replace an explicit Tenant selection
        # with Month.
        configured_columns = _normalise_json_array(
            _first_configured_value(
                visual,
                "tableColumns",
                "table_columns",
                "columns",
                "selectedColumns",
                "selected_columns",
            )
        )

        for configured_column in configured_columns:
            resolved_column = _resolve_column_name(
                configured_column,
                valid_columns,
            )

            if not resolved_column:
                continue

            configured_split_token = _singular_column_token(
                configured_value
            )

            resolved_token = _singular_column_token(
                resolved_column
            )

            if (
                configured_split_token == resolved_token
                or configured_split_token in resolved_token
                or resolved_token in configured_split_token
            ):
                return resolved_column

        # Explicit but genuinely unresolved: return empty so the
        # visual reports the real configuration problem rather than
        # silently splitting by Month.
        return ""

    # Backward compatibility only for older saved configurations that
    # genuinely have no split field.
    configured_columns = _normalise_json_array(
        _first_configured_value(
            visual,
            "tableColumns",
            "table_columns",
            "columns",
            "selectedColumns",
            "selected_columns",
        )
    )

    resolved_configured_columns = []

    for column in configured_columns:
        resolved_column = _resolve_column_name(
            column,
            valid_columns,
        )

        if (
            resolved_column
            and resolved_column not in resolved_configured_columns
        ):
            resolved_configured_columns.append(
                resolved_column
            )

    # Use a configured table column before searching the entire table.
    if resolved_configured_columns:
        return resolved_configured_columns[0]

    # Final compatibility fallback for very old configurations.
    preferred_names = [
        "tenant",
        "tenants",
        "company",
        "company_name",
        "department",
        "site",
        "status",
        "category",
        "year",
        "month",
        "date",
    ]

    for preferred_name in preferred_names:
        resolved = _resolve_column_name(
            preferred_name,
            valid_columns,
        )

        if resolved:
            return resolved

    return valid_columns[0] if valid_columns else ""

def _normalise_aggregation_name(value: Any) -> str:
    cleaned = _clean_text(value).lower()

    aliases = {
        "avg": "average",
        "mean": "average",
        "distinct": "distinct_count",
        "distinctcount": "distinct_count",
        "distinct_count": "distinct_count",
        "percent": "percentage",
        "percentage_of_total": "percentage",
        "percentageoftotal": "percentage",
    }

    return aliases.get(cleaned, cleaned or "sum")


# ============================================================
# AXIS / AGGREGATION HELPERS
# ============================================================

_AXIS_AGGREGATION_RE = re.compile(
    r"^__aggregation_(sum|count|distinct_count|average|min|max|percentage)__$"
)


def _parse_axis_selection(value: Any) -> Dict[str, Any]:
    cleaned = _clean_text(value)

    if "::" in cleaned:
        option, column = cleaned.split("::", 1)
    else:
        option, column = cleaned, ""

    match = _AXIS_AGGREGATION_RE.fullmatch(option)

    return {
        "raw": cleaned,
        "option": option,
        "column": _clean_text(column),
        "is_aggregation": bool(match),
        "aggregation": match.group(1) if match else "",
    }


def _resolve_visual_mapping(
    visual: Mapping[str, Any],
    valid_columns: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    category = _parse_axis_selection(
        _first_configured_value(
            visual,
            "category",
            "xAxis",
            "x_axis",
            "groupField",
            "group_field",
        )
    )

    value = _parse_axis_selection(
        _first_configured_value(
            visual,
            "value",
            "yAxis",
            "y_axis",
            "measureField",
            "measure_field",
        )
    )

    configured_aggregation = _normalise_aggregation_name(
        _first_configured_value(
            visual,
            "aggregation",
            "aggregate",
            "aggregationType",
            "aggregation_type",
        )
    )

    if category["is_aggregation"]:
        group_field = value["column"] or value["option"]
        measure_field = category["column"]
        aggregation = (
            category["aggregation"]
            or configured_aggregation
        )
        aggregation_axis = "category"

    elif value["is_aggregation"]:
        group_field = category["column"] or category["option"]
        measure_field = value["column"]
        aggregation = (
            value["aggregation"]
            or configured_aggregation
        )
        aggregation_axis = "value"

    else:
        group_field = category["column"] or category["option"]
        measure_field = value["column"] or value["option"]
        aggregation = configured_aggregation
        aggregation_axis = ""

    if valid_columns is not None:
        group_field = _resolve_column_name(
            group_field,
            valid_columns,
        )

        measure_field = _resolve_column_name(
            measure_field,
            valid_columns,
        )

    return {
        "group_field": group_field,
        "measure_field": measure_field,
        "aggregation": _normalise_aggregation_name(
            aggregation
        ),
        "aggregation_axis": aggregation_axis,
    }



def _aggregation_expression(
    aggregation: str,
    measure_field: str,
    valid_columns: Sequence[str],
) -> sql.Composable:
    """
    Return the SQL aggregate used by a visual.

    Percentage uses SUM as its base value. Grouped percentage visuals
    are normalised against the complete filtered total inside
    _execute_grouped_visual().
    """
    aggregation = _clean_text(aggregation).lower()
    measure_field = _clean_text(measure_field)

    if aggregation in {"count", "distinct_count"} and not measure_field:
        return sql.SQL("COUNT(*)")

    if measure_field not in valid_columns:
        raise ValueError(
            f'Configured aggregation column "{measure_field}" '
            "does not exist in the selected form table."
        )

    measure_identifier = sql.Identifier(measure_field)

    if aggregation == "count":
        return sql.SQL("COUNT({})").format(measure_identifier)

    if aggregation == "distinct_count":
        return sql.SQL("COUNT(DISTINCT {})").format(
            measure_identifier
        )

    numeric_value = sql.SQL(
        """
        CASE
            WHEN BTRIM({column}::text)
                 ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
            THEN BTRIM({column}::text)::numeric
            ELSE NULL
        END
        """
    ).format(column=measure_identifier)

    if aggregation in {"sum", "percentage"}:
        return sql.SQL("COALESCE(SUM({}), 0)").format(
            numeric_value
        )

    if aggregation == "average":
        return sql.SQL("COALESCE(AVG({}), 0)").format(
            numeric_value
        )

    if aggregation == "min":
        return sql.SQL("COALESCE(MIN({}), 0)").format(
            numeric_value
        )

    if aggregation == "max":
        return sql.SQL("COALESCE(MAX({}), 0)").format(
            numeric_value
        )

    raise ValueError(
        f'Unsupported aggregation "{aggregation}".'
    )



def _fetch_form_definition(
    conn,
    bi_view_name: str,
    database_table: str,
) -> Dict[str, Any]:
    """
    Build the report definition from the values passed by the BI
    mapping page. The selected table is validated before any SQL is run.
    """
    cleaned_view_name = _clean_text(bi_view_name)
    cleaned_database_table = _clean_text(database_table)

    if not cleaned_view_name:
        raise ValueError("The BI view name is required.")

    if not cleaned_database_table:
        raise ValueError("The mapped database table is required.")

    schema_name, table_name = _split_qualified_table_name(
        cleaned_database_table
    )

    return {
        "bi_view_name": cleaned_view_name,
        "form_name": cleaned_view_name,
        "database_tables": cleaned_database_table,
        "dynamic_table_name": f"{schema_name}.{table_name}",
    }



def _fetch_saved_configuration(
    conn,
    bi_view_name: str,
) -> Dict[str, Any]:
    """
    Fetch the saved JSONB configuration using bi_view_name.

    bi_view_name is unique in
    public.bi_dashboard_saved_configurations_dashbooards.
    """
    cleaned_view_name = _clean_text(bi_view_name)

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            f"""
            SELECT
                bi_view_id,
                bi_view_name,
                database_tables,
                config_status,
                dashboard_pages,
                created_by,
                created_at,
                updated_by,
                updated_at
            FROM {SAVED_CONFIGURATION_TABLE}
            WHERE LOWER(BTRIM(bi_view_name)) =
                  LOWER(BTRIM(%s))
            LIMIT 1
            """,
            (cleaned_view_name,),
        )

        row = cursor.fetchone()

    if not row:
        return {
            "exists": False,
            "bi_view_id": None,
            "bi_view_name": cleaned_view_name,
            "database_tables": "",
            "config_status": "Draft",
            "dashboard_pages": {},
        }

    result = dict(row)
    result["exists"] = True
    result["dashboard_pages"] = _normalise_json_object(
        result.get("dashboard_pages")
    )
    return result


def _table_exists(
    conn,
    schema_name: str,
    table_name: str,
) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s
            )
            """,
            (schema_name, table_name),
        )

        return bool(cursor.fetchone()[0])


def _fetch_table_columns(
    conn,
    schema_name: str,
    table_name: str,
) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                ordinal_position,
                column_name,
                data_type,
                udt_name,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        )

        return [dict(row) for row in cursor.fetchall()]


# ============================================================
# PAGE NORMALISATION
# ============================================================

def _normalise_pages(
    dashboard_pages: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []

    for index, (page_name, raw_configuration) in enumerate(
        dashboard_pages.items(),
        start=1,
    ):
        configuration = (
            raw_configuration
            if isinstance(raw_configuration, dict)
            else {}
        )

        filter_columns = configuration.get(
            "filter_columns",
            configuration.get("filterColumns", []),
        )

        visuals = configuration.get("visuals", [])

        pages.append(
            {
                "id": (
                    _clean_text(configuration.get("id"))
                    or f"page_{index}"
                ),
                "name": _clean_text(page_name) or f"Page {index}",
                "description": _clean_text(
                    configuration.get("description")
                ),
                "page_order": _safe_integer(
                    configuration.get("page_order"),
                    index,
                ),
                "filter_columns": [
                    _clean_text(column)
                    for column in _normalise_json_array(filter_columns)
                    if _clean_text(column)
                ],
                "visuals": [
                    visual
                    for visual in _normalise_json_array(visuals)
                    if isinstance(visual, dict)
                ],
            }
        )

    pages.sort(
        key=lambda page: (
            page.get("page_order", 0),
            page.get("name", ""),
        )
    )

    return pages


# ============================================================
# FILTER HANDLING
# ============================================================

def _collect_filter_columns(
    pages: Sequence[Mapping[str, Any]],
    valid_columns: Sequence[str],
) -> List[str]:
    columns: List[str] = []

    for page in pages:
        for column in page.get("filter_columns", []):
            if (
                column in valid_columns
                and column not in columns
            ):
                columns.append(column)

    return columns


def _normalise_filter_values(
    filters: Optional[Mapping[str, Any]],
    allowed_columns: Sequence[str],
) -> Dict[str, str]:
    """
    Extract submitted report filters safely.

    Supports:
    - normal dictionaries
    - Flask request.args MultiDict
    - Flask request.form MultiDict
    - list or tuple values
    """

    result: Dict[str, str] = {}

    if not filters:
        return result

    for column in allowed_columns:
        raw_value = None

        # Flask MultiDict support.
        if hasattr(filters, "getlist"):
            submitted_values = filters.getlist(column)

            for submitted_value in submitted_values:
                cleaned_value = _clean_text(submitted_value)

                if cleaned_value:
                    raw_value = cleaned_value
                    break

        # Normal mapping support.
        if raw_value is None:
            raw_value = filters.get(column)

        if isinstance(raw_value, (list, tuple, set)):
            selected_value = ""

            for item in raw_value:
                cleaned_item = _clean_text(item)

                if cleaned_item:
                    selected_value = cleaned_item
                    break

            raw_value = selected_value

        value = _clean_text(raw_value)

        if value:
            result[column] = value

    return result


def _build_where_clause(
    filter_values: Mapping[str, str],
    valid_columns: Sequence[str],
) -> Tuple[sql.Composable, List[Any]]:
    """
    Build one global WHERE clause containing every selected filter.

    Example:
        WHERE LOWER(BTRIM(company::text)) = LOWER(BTRIM(%s))
          AND LOWER(BTRIM(year::text)) = LOWER(BTRIM(%s))
          AND LOWER(BTRIM(month::text)) = LOWER(BTRIM(%s))
    """

    clauses: List[sql.Composable] = []
    params: List[Any] = []

    for column, value in filter_values.items():
        cleaned_column = _clean_text(column)
        cleaned_value = _clean_text(value)

        if not cleaned_column:
            continue

        if not cleaned_value:
            continue

        if cleaned_column not in valid_columns:
            continue

        clauses.append(
            sql.SQL(
                """
                LOWER(
                    BTRIM(
                        COALESCE({column}::text, '')
                    )
                )
                =
                LOWER(
                    BTRIM(%s)
                )
                """
            ).format(
                column=sql.Identifier(cleaned_column)
            )
        )

        params.append(cleaned_value)

    if not clauses:
        return sql.SQL(""), params

    return (
        sql.SQL(" WHERE ")
        + sql.SQL(" AND ").join(clauses),
        params,
    )


def _fetch_filter_options(
    conn,
    schema_name: str,
    table_name: str,
    filter_columns: Sequence[str],
    valid_columns: Sequence[str],
) -> List[Dict[str, Any]]:
    """
    Fetch distinct filter values.

    Month values are returned in calendar order. The month sort
    expression is included in the SELECT list so PostgreSQL accepts
    the SELECT DISTINCT ... ORDER BY query.
    """
    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    result: List[Dict[str, Any]] = []

    for column in filter_columns:
        if column not in valid_columns:
            continue

        column_identifier = sql.Identifier(column)

        value_expression = sql.SQL(
            "BTRIM({column}::text)"
        ).format(
            column=column_identifier
        )

        if _is_month_column(column):
            month_order_expression = (
                _month_order_from_expression(
                    value_expression
                )
            )

            query = (
                sql.SQL("SELECT DISTINCT ")
                + value_expression
                + sql.SQL(" AS value, ")
                + month_order_expression
                + sql.SQL(" AS month_order FROM ")
                + table_identifier
                + sql.SQL(" WHERE ")
                + column_identifier
                + sql.SQL(" IS NOT NULL AND ")
                + value_expression
                + sql.SQL(" <> '' ")
                + sql.SQL(
                    "ORDER BY month_order ASC, value ASC LIMIT %s"
                )
            )
        else:
            query = (
                sql.SQL("SELECT DISTINCT ")
                + value_expression
                + sql.SQL(" AS value FROM ")
                + table_identifier
                + sql.SQL(" WHERE ")
                + column_identifier
                + sql.SQL(" IS NOT NULL AND ")
                + value_expression
                + sql.SQL(" <> '' ")
                + sql.SQL("ORDER BY value ASC LIMIT %s")
            )

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                query,
                (MAX_FILTER_OPTIONS,),
            )

            values = [
                _clean_text(row.get("value"))
                for row in cursor.fetchall()
                if _clean_text(row.get("value"))
            ]

        result.append(
            {
                "column": column,
                "label": (
                    column
                    .replace("_", " ")
                    .strip()
                    .title()
                ),
                "options": values,
            }
        )

    return result


# ============================================================
# SQL VISUAL EXECUTION
# ============================================================


def _execute_single_value_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
) -> Dict[str, Any]:
    mapping = _resolve_visual_mapping(visual, valid_columns)

    measure_field = mapping["measure_field"]
    aggregation = mapping["aggregation"]

    if not measure_field:
        if aggregation not in {"count", "distinct_count"}:
            measure_field = next(
                iter(valid_columns),
                "",
            )

    aggregate_expression = _aggregation_expression(
        aggregation,
        measure_field,
        valid_columns,
    )

    where_sql, params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    query = (
        sql.SQL("SELECT ")
        + aggregate_expression
        + sql.SQL(" AS value FROM ")
        + _table_identifier(schema_name, table_name)
        + where_sql
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone() or {}

    value = row.get("value") or 0

    # A single-value percentage represents the selected filtered
    # measure as a share of itself, therefore 100 when data exists
    # and 0 when no numeric value exists.
    if aggregation == "percentage":
        value = 100 if Decimal(str(value or 0)) != 0 else 0

    return {
        "value": _json_safe(value),
        "aggregation": aggregation,
        "measure_field": measure_field,
        "is_percentage": aggregation == "percentage",
    }



def _execute_grouped_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Execute every grouped dashboard visual.

    When the configured grouping field is Month, results are returned
    in calendar order:

        January, February, March ... December

    All other grouping fields retain value-descending ordering.
    """
    mapping = _resolve_visual_mapping(
        visual,
        valid_columns,
    )

    group_field = mapping["group_field"]
    measure_field = mapping["measure_field"]
    aggregation = mapping["aggregation"]

    if not group_field:
        group_field = next(
            (
                column
                for column in valid_columns
                if column != measure_field
            ),
            valid_columns[0] if valid_columns else "",
        )

    if group_field not in valid_columns:
        raise ValueError(
            f'Configured grouping column "{group_field}" '
            "does not exist in the selected form table."
        )

    if not measure_field:
        if aggregation in {
            "count",
            "distinct_count",
        }:
            measure_field = ""
        else:
            measure_field = next(
                (
                    column
                    for column in valid_columns
                    if column != group_field
                ),
                group_field,
            )

    aggregate_expression = (
        _aggregation_expression(
            aggregation,
            measure_field,
            valid_columns,
        )
    )

    where_sql, params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    group_expression = sql.SQL(
        """
        COALESCE(
            NULLIF(
                BTRIM({group_column}::text),
                ''
            ),
            'Unknown'
        )
        """
    ).format(
        group_column=sql.Identifier(
            group_field
        )
    )

    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    # ========================================================
    # MONTH GROUPING
    # ========================================================

    if _is_month_column(group_field):
        month_order_expression = (
            _month_order_from_expression(
                group_expression
            )
        )

        query = (
            sql.SQL("SELECT ")
            + group_expression
            + sql.SQL(" AS label, ")
            + aggregate_expression
            + sql.SQL(" AS value, ")
            + month_order_expression
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + group_expression
            + sql.SQL(", ")
            + month_order_expression
            + sql.SQL(
                """
                ORDER BY
                    calendar_order ASC,
                    label ASC
                LIMIT %s
                """
            )
        )

    # ========================================================
    # YEAR GROUPING
    # ========================================================

    elif _is_year_column(group_field):
        year_identifier = sql.Identifier(
            group_field
        )

        year_order_expression = sql.SQL(
            """
            CASE
                WHEN BTRIM(
                    COALESCE({year_column}::text, '')
                ) ~ '^[0-9]+$'
                THEN BTRIM({year_column}::text)::bigint
                ELSE NULL
            END
            """
        ).format(
            year_column=year_identifier
        )

        query = (
            sql.SQL("SELECT ")
            + group_expression
            + sql.SQL(" AS label, ")
            + aggregate_expression
            + sql.SQL(" AS value, ")
            + year_order_expression
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + group_expression
            + sql.SQL(", ")
            + year_order_expression
            + sql.SQL(
                """
                ORDER BY
                    calendar_order ASC NULLS LAST,
                    label ASC
                LIMIT %s
                """
            )
        )

    # ========================================================
    # NORMAL NON-CALENDAR GROUPING
    # ========================================================

    else:
        query = (
            sql.SQL("SELECT ")
            + group_expression
            + sql.SQL(" AS label, ")
            + aggregate_expression
            + sql.SQL(" AS value FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + group_expression
            + sql.SQL(
                """
                ORDER BY
                    value DESC NULLS LAST,
                    label ASC
                LIMIT %s
                """
            )
        )

    query_params = list(params) + [
        int(limit)
    ]

    with conn.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            query,
            query_params,
        )

        rows = [
            dict(row)
            for row in cursor.fetchall()
        ]

    if aggregation == "percentage":
        total_value = sum(
            Decimal(
                str(row.get("value") or 0)
            )
            for row in rows
        )

        for row in rows:
            raw_value = Decimal(
                str(row.get("value") or 0)
            )

            row["value"] = (
                float(
                    (
                        raw_value
                        / total_value
                    )
                    * Decimal("100")
                )
                if total_value
                else 0
            )

    return {
        "items": [
            {
                "label": (
                    _clean_text(
                        row.get("label")
                    )
                    or "Unknown"
                ),
                "value": _json_safe(
                    row.get("value") or 0
                ),
            }
            for row in rows
        ],
        "aggregation": aggregation,
        "group_field": group_field,
        "measure_field": measure_field,
        "is_percentage": (
            aggregation == "percentage"
        ),
        "calendar_order_applied": (
            _is_month_column(group_field)
            or _is_year_column(group_field)
        ),
    }



def _is_column_total_eligible(column_name: Any) -> bool:
    """
    Return True only for columns that should receive a column total.

    Calendar, time, identifier and descriptive columns are excluded so
    values such as Year=2026 or Day=10 are never added to operational
    measures such as number_of_trucks_in and number_of_trucks_out.
    """
    cleaned = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_text(column_name).lower(),
    ).strip("_")

    if not cleaned:
        return False

    exact_exclusions = {
        "year",
        "years",
        "month",
        "months",
        "month_name",
        "monthname",
        "day",
        "days",
        "date",
        "time",
        "hour",
        "minute",
        "second",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    }

    if cleaned in exact_exclusions:
        return False

    if cleaned == "id" or cleaned.endswith("_id"):
        return False

    if cleaned.endswith("_date") or cleaned.endswith("_time"):
        return False

    return True


def _fetch_column_totals(
    conn,
    schema_name: str,
    table_name: str,
    columns: Sequence[str],
    valid_columns: Sequence[str],
    where_sql: sql.Composable,
    where_params: Sequence[Any],
) -> Dict[str, Any]:
    """
    Calculate one total for each eligible selected column.

    Numeric database values and numeric text values are summed. Columns
    containing no numeric values, and dimension columns such as year,
    month, day and time, return None.
    """
    selected_columns = [
        column
        for column in columns
        if column in valid_columns
    ]

    totals: Dict[str, Any] = {
        column: None
        for column in selected_columns
    }

    eligible_columns = [
        column
        for column in selected_columns
        if _is_column_total_eligible(column)
    ]

    if not eligible_columns:
        return totals

    total_expressions: List[sql.Composable] = []

    for column in eligible_columns:
        column_identifier = sql.Identifier(column)

        numeric_expression = sql.SQL(
            """
            CASE
                WHEN BTRIM(COALESCE({column}::text, ''))
                     ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN BTRIM({column}::text)::numeric
                ELSE NULL
            END
            """
        ).format(column=column_identifier)

        total_expressions.append(
            sql.SQL(
                """
                CASE
                    WHEN COUNT({numeric_value}) > 0
                    THEN SUM({numeric_value})
                    ELSE NULL
                END AS {alias}
                """
            ).format(
                numeric_value=numeric_expression,
                alias=sql.Identifier(column),
            )
        )

    query = (
        sql.SQL("SELECT ")
        + sql.SQL(", ").join(total_expressions)
        + sql.SQL(" FROM ")
        + _table_identifier(schema_name, table_name)
        + where_sql
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, list(where_params))
        row = cursor.fetchone() or {}

    for column in eligible_columns:
        totals[column] = _json_safe(row.get(column))

    return totals


def _build_column_total_row(
    columns: Sequence[str],
    column_totals: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Build the final table row used by the existing template.

    The first selected column is labelled Total. Every eligible numeric
    column receives its own total directly beneath that column. No extra
    Total column is created.
    """
    total_row: Dict[str, Any] = {
        column: None
        for column in columns
    }

    if columns:
        total_row[columns[0]] = "Total"

    for column in columns:
        value = column_totals.get(column)

        if value is not None:
            total_row[column] = value

    total_row["__is_total_row"] = True
    return total_row


def _resolve_table_columns(
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
) -> List[str]:
    configured_columns = _normalise_json_array(
        _first_configured_value(
            visual,
            "tableColumns",
            "table_columns",
            "columns",
            "selectedColumns",
            "selected_columns",
        )
    )

    columns: List[str] = []

    for configured_column in configured_columns:
        resolved_column = _resolve_column_name(
            configured_column,
            valid_columns,
        )

        if (
            resolved_column
            and resolved_column not in columns
        ):
            columns.append(resolved_column)

    return columns or list(valid_columns[:8])



def _resolve_distinct_based_on_column(
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    table_columns: Sequence[str],
) -> str:
    """
    Resolve the selected Table Column used to de-duplicate only the
    table portion of Split Table with Tracking Distinct.

    Tracking remains unchanged and continues to use all matching rows.
    Older saved configurations fall back to the first selected table
    column so they remain loadable.
    """
    configured_value = _first_configured_value(
        visual,
        "distinctBasedOn",
        "distinct_based_on",
        "distinctColumn",
        "distinct_column",
    )

    resolved = _resolve_column_name(
        configured_value,
        valid_columns,
    )

    if resolved and resolved in table_columns:
        return resolved

    return next(
        (
            column
            for column in table_columns
            if column in valid_columns
        ),
        "",
    )


def _execute_table_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    *,
    table_page: int = 1,
    table_per_page: int = 10,
    table_page_parameter: str = "",
    table_per_page_parameter: str = "",
    request_values: Optional[Mapping[str, Any]] = None,
    pagination_token: str = "visual",
) -> Dict[str, Any]:
    """
    Execute a configured Data Table with independent server-side
    pagination.

    Each eligible numeric column receives its own total in a final
    totals row. The totals are calculated from every filtered record,
    not only the current pagination page.
    """
    allowed_per_page = [10, 25, 50, 100]

    columns = _resolve_table_columns(
        visual,
        valid_columns,
    )

    if not columns:
        return {
            "columns": [],
            "source_columns": [],
            "rows": [],
            "column_totals": {},
            "total_records": 0,
            "total_pages": 1,
            "page": 1,
            "per_page": 10,
            "showing_from": 0,
            "showing_to": 0,
            "page_links": [1],
            "allowed_per_page": allowed_per_page,
            "page_parameter": table_page_parameter,
            "per_page_parameter": table_per_page_parameter,
            "has_column_totals": True,
            "has_total_column": False,
        }

    table_page = max(1, _safe_integer(table_page, 1))
    table_per_page = _safe_integer(table_per_page, 10)

    if table_per_page not in allowed_per_page:
        table_per_page = 10

    where_sql, where_params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    count_query = (
        sql.SQL("SELECT COUNT(*) AS total_records FROM ")
        + table_identifier
        + where_sql
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(count_query, list(where_params))
        count_row = cursor.fetchone() or {}

    total_records = _safe_integer(
        count_row.get("total_records"),
        0,
    )

    total_pages = (
        math.ceil(total_records / table_per_page)
        if total_records
        else 1
    )

    table_page = min(table_page, total_pages)
    offset = (table_page - 1) * table_per_page

    preferred_order_columns = [
        "id",
        "record_id",
        "submission_id",
        "transaction_id",
        "created_at",
    ]

    fallback_order_column = next(
        (
            column
            for column in preferred_order_columns
            if column in valid_columns
        ),
        columns[0],
    )

    order_clause = _build_table_order_clause(
        columns,
        valid_columns,
        fallback_order_column,
    )

    data_query = (
        sql.SQL("SELECT ")
        + sql.SQL(", ").join(
            sql.Identifier(column)
            for column in columns
        )
        + sql.SQL(" FROM ")
        + table_identifier
        + where_sql
        + order_clause
        + sql.SQL(" LIMIT %s OFFSET %s")
    )

    data_params = list(where_params) + [
        table_per_page,
        offset,
    ]

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(data_query, data_params)
        database_rows = [
            dict(row)
            for row in cursor.fetchall()
        ]

    output_rows = [
        {
            column: _json_safe(row.get(column))
            for column in columns
        }
        for row in database_rows
    ]

    column_totals = _fetch_column_totals(
        conn=conn,
        schema_name=schema_name,
        table_name=table_name,
        columns=columns,
        valid_columns=valid_columns,
        where_sql=where_sql,
        where_params=where_params,
    )

    if total_records > 0:
        output_rows.append(
            _build_column_total_row(
                columns,
                column_totals,
            )
        )

    showing_from = offset + 1 if total_records else 0

    showing_to = (
        min(offset + len(database_rows), total_records)
        if total_records
        else 0
    )

    month_column = _find_month_column(columns)
    year_column = _find_year_column(columns)

    return {
        "columns": columns,
        "source_columns": columns,
        "rows": output_rows,
        "column_totals": column_totals,
        "total_returned": len(database_rows),
        "total_records": total_records,
        "page": table_page,
        "per_page": table_per_page,
        "total_pages": total_pages,
        "showing_from": showing_from,
        "showing_to": showing_to,
        "page_links": build_page_links(
            table_page,
            total_pages,
        ),
        "allowed_per_page": allowed_per_page,
        "page_parameter": table_page_parameter,
        "per_page_parameter": table_per_page_parameter,
        "order_column": fallback_order_column,
        "year_order_column": year_column,
        "month_order_column": month_column,
        "calendar_order_applied": bool(month_column),
        "has_column_totals": True,
        "has_total_column": False,
    }


def _execute_split_table_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    *,
    request_values: Optional[Mapping[str, Any]] = None,
    pagination_token: str = "split_table",
) -> Dict[str, Any]:
    """
    Split the filtered result set into a separate table for every
    distinct split value.

    Calendar ordering is applied in two places:

    1. When splitting by Month, group headings are returned from
       January through December.
    2. When Month is one of the displayed table columns, rows inside
       every split group are ordered by Year and Month.
    """
    allowed_per_page = [
        10,
        25,
        50,
        100,
    ]

    columns = _resolve_table_columns(
        visual,
        valid_columns,
    )

    split_column = _resolve_split_column(
        visual,
        valid_columns,
    )

    if not split_column:
        configured_split_value = _clean_text(
            _first_configured_value(
                visual,
                "splitColumn",
                "split_column",
                "splitBy",
                "split_by",
                "splitField",
                "split_field",
                "splitOn",
                "split_on",
                "groupBy",
                "group_by",
                "partitionColumn",
                "partition_column",
            )
        )

        return {
            "columns": columns,
            "source_columns": columns,
            "split_column": "",
            "groups": [],
            "group_count": 0,
            "allowed_per_page": allowed_per_page,
            "has_column_totals": True,
            "has_total_column": False,
            "configuration_warning": (
                f'The configured split column '
                f'"{configured_split_value}" could not be matched '
                "to a physical form-table column."
                if configured_split_value
                else (
                    "No split column was stored in this saved "
                    "Split Data Table configuration."
                )
            ),
        }

    selected_columns = list(
        columns
    )

    if split_column not in selected_columns:
        selected_columns.append(
            split_column
        )

    where_sql, where_params = (
        _build_where_clause(
            filter_values,
            valid_columns,
        )
    )

    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    split_value_expression = sql.SQL(
        """
        COALESCE(
            NULLIF(
                BTRIM({split_column}::text),
                ''
            ),
            'Unknown'
        )
        """
    ).format(
        split_column=sql.Identifier(
            split_column
        )
    )

    # ========================================================
    # FETCH SPLIT GROUPS
    # ========================================================

    if _is_month_column(split_column):
        split_month_order = (
            _month_order_from_expression(
                split_value_expression
            )
        )

        split_values_query = (
            sql.SQL("SELECT ")
            + split_value_expression
            + sql.SQL(" AS split_value, ")
            + sql.SQL(
                "COUNT(*) AS total_records, "
            )
            + split_month_order
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + split_value_expression
            + sql.SQL(", ")
            + split_month_order
            + sql.SQL(
                """
                ORDER BY
                    calendar_order ASC,
                    split_value ASC
                """
            )
        )

    elif _is_year_column(split_column):
        split_identifier = sql.Identifier(
            split_column
        )

        split_year_order = sql.SQL(
            """
            CASE
                WHEN BTRIM(
                    COALESCE({split_column}::text, '')
                ) ~ '^[0-9]+$'
                THEN BTRIM({split_column}::text)::bigint
                ELSE NULL
            END
            """
        ).format(
            split_column=split_identifier
        )

        split_values_query = (
            sql.SQL("SELECT ")
            + split_value_expression
            + sql.SQL(" AS split_value, ")
            + sql.SQL(
                "COUNT(*) AS total_records, "
            )
            + split_year_order
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + split_value_expression
            + sql.SQL(", ")
            + split_year_order
            + sql.SQL(
                """
                ORDER BY
                    calendar_order ASC NULLS LAST,
                    split_value ASC
                """
            )
        )

    else:
        split_values_query = (
            sql.SQL("SELECT ")
            + split_value_expression
            + sql.SQL(" AS split_value, ")
            + sql.SQL(
                "COUNT(*) AS total_records FROM "
            )
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + split_value_expression
            + sql.SQL(
                """
                ORDER BY
                    split_value ASC
                """
            )
        )

    with conn.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            split_values_query,
            list(where_params),
        )

        split_value_rows = [
            dict(row)
            for row in cursor.fetchall()
        ]

    groups: List[Dict[str, Any]] = []

    # ========================================================
    # BUILD EACH SPLIT TABLE
    # ========================================================

    for group_index, split_value_row in enumerate(
        split_value_rows,
        start=1,
    ):
        split_value = (
            _clean_text(
                split_value_row.get(
                    "split_value"
                )
            )
            or "Unknown"
        )

        total_records = _safe_integer(
            split_value_row.get(
                "total_records"
            ),
            0,
        )

        group_token = _safe_pagination_token(
            (
                f"{pagination_token}_"
                f"{group_index}_"
                f"{split_value}"
            )
        )

        page_parameter = (
            f"split_page_{group_token}"
        )

        per_page_parameter = (
            f"split_per_page_{group_token}"
        )

        current_page = max(
            1,
            _safe_integer(
                _mapping_value(
                    request_values,
                    page_parameter,
                    1,
                ),
                1,
            ),
        )

        per_page = _safe_integer(
            _mapping_value(
                request_values,
                per_page_parameter,
                10,
            ),
            10,
        )

        if per_page not in allowed_per_page:
            per_page = 10

        total_pages = (
            math.ceil(
                total_records
                / per_page
            )
            if total_records > 0
            else 1
        )

        current_page = min(
            current_page,
            total_pages,
        )

        offset = (
            current_page - 1
        ) * per_page

        split_condition = (
            split_value_expression
            + sql.SQL(" = %s")
        )

        group_where_sql = (
            where_sql
            + (
                sql.SQL(" AND ")
                if where_params
                else sql.SQL(" WHERE ")
            )
            + split_condition
        )

        preferred_order_columns = [
            "id",
            "record_id",
            "submission_id",
            "transaction_id",
            "created_at",
        ]

        fallback_order_column = next(
            (
                column
                for column in preferred_order_columns
                if column in valid_columns
            ),
            (
                columns[0]
                if columns
                else split_column
            ),
        )

        order_clause = _build_table_order_clause(
            columns,
            valid_columns,
            fallback_order_column,
        )

        data_query = (
            sql.SQL("SELECT ")
            + sql.SQL(", ").join(
                sql.Identifier(column)
                for column in selected_columns
            )
            + sql.SQL(" FROM ")
            + table_identifier
            + group_where_sql
            + order_clause
            + sql.SQL(
                " LIMIT %s OFFSET %s"
            )
        )

        group_params = list(
            where_params
        ) + [
            split_value,
            per_page,
            offset,
        ]

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                data_query,
                group_params,
            )

            database_rows = [
                dict(row)
                for row in cursor.fetchall()
            ]

        group_rows = [
            {
                column: _json_safe(
                    row.get(column)
                )
                for column in columns
            }
            for row in database_rows
        ]

        group_column_totals = _fetch_column_totals(
            conn=conn,
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
            valid_columns=valid_columns,
            where_sql=group_where_sql,
            where_params=list(where_params) + [
                split_value
            ],
        )

        if total_records > 0:
            group_rows.append(
                _build_column_total_row(
                    columns,
                    group_column_totals,
                )
            )

        showing_from = (
            offset + 1
            if total_records > 0
            else 0
        )

        showing_to = (
            min(
                offset + len(group_rows),
                total_records,
            )
            if total_records > 0
            else 0
        )

        groups.append(
            {
                "title": split_value,
                "split_value": split_value,
                "rows": group_rows,
                "column_totals": group_column_totals,
                "total_returned": len(
                    database_rows
                ),
                "total_records": total_records,
                "page": current_page,
                "per_page": per_page,
                "total_pages": total_pages,
                "showing_from": showing_from,
                "showing_to": showing_to,
                "page_links": build_page_links(
                    current_page,
                    total_pages,
                ),
                "allowed_per_page": (
                    allowed_per_page
                ),
                "page_parameter": (
                    page_parameter
                ),
                "per_page_parameter": (
                    per_page_parameter
                ),
                "order_column": (
                    fallback_order_column
                ),
                "month_order_column": (
                    _find_month_column(
                        columns
                    )
                ),
                "calendar_order_applied": bool(
                    _find_month_column(
                        columns
                    )
                ),
            }
        )

    return {
        "columns": columns,
        "source_columns": columns,
        "split_column": split_column,
        "groups": groups,
        "group_count": len(groups),
        "allowed_per_page": allowed_per_page,
        "has_column_totals": True,
        "has_total_column": False,
        "split_group_calendar_order": (
            _is_month_column(split_column)
            or _is_year_column(split_column)
        ),
        "configuration_warning": (
            ""
            if _clean_text(
                _first_configured_value(
                    visual,
                    "splitColumn",
                    "split_column",
                    "splitBy",
                    "split_by",
                    "splitField",
                    "split_field",
                )
            )
            else (
                f'No split column was stored; '
                f'"{split_column}" was selected automatically.'
            )
        ),
    }






def _resolve_distinct_latest_column(
    valid_columns: Sequence[str],
    selected_columns: Sequence[str],
) -> str:
    """
    Resolve the column used to decide which duplicate table row is the
    most recent.

    The new Split Table with Tracking Distinct visual does not require
    another configuration field. It prefers conventional update,
    submission and creation timestamp columns. When none exists, it
    uses a selected date/time column, then a conventional identifier.
    """
    valid_lookup = {
        _clean_text(column).lower(): column
        for column in valid_columns
    }

    preferred_names = [
        "updated_at",
        "updatedat",
        "last_updated_at",
        "last_modified_at",
        "modified_at",
        "submitted_at",
        "submission_date",
        "submission_datetime",
        "recorded_at",
        "gps_recorded_at",
        "captured_at",
        "created_at",
        "createdat",
        "date_created",
        "created_date",
    ]

    for preferred_name in preferred_names:
        matched = valid_lookup.get(preferred_name)
        if matched:
            return matched

    selected_set = {
        column
        for column in selected_columns
        if column in valid_columns
    }

    def looks_like_recency_column(column: str) -> bool:
        token = re.sub(
            r"[^a-z0-9]+",
            "_",
            _clean_text(column).lower(),
        ).strip("_")

        has_time_word = any(
            word in token
            for word in (
                "date",
                "time",
                "timestamp",
                "created",
                "updated",
                "submitted",
                "recorded",
                "captured",
                "modified",
            )
        )

        return has_time_word

    for column in valid_columns:
        if column in selected_set and looks_like_recency_column(column):
            return column

    for column in valid_columns:
        if looks_like_recency_column(column):
            return column

    for identifier_name in (
        "id",
        "record_id",
        "submission_id",
        "transaction_id",
    ):
        matched = valid_lookup.get(identifier_name)
        if matched:
            return matched

    return ""


def _distinct_table_cte(
    schema_name: str,
    table_name: str,
    selected_columns: Sequence[str],
    distinct_columns: Sequence[str],
    latest_column: str,
    where_sql: sql.Composable,
) -> sql.Composable:
    """Build the ranked CTE used by distinct tracking table rows."""
    selected_sql = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in selected_columns
    )

    distinct_sql = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in distinct_columns
    )

    if latest_column:
        latest_order = sql.SQL(
            "{} DESC NULLS LAST, ctid DESC"
        ).format(
            sql.Identifier(latest_column)
        )
    else:
        latest_order = sql.SQL("ctid DESC")

    return sql.SQL(
        """
        WITH ranked_distinct_rows AS (
            SELECT
                {selected_columns},
                ROW_NUMBER() OVER (
                    PARTITION BY {distinct_columns}
                    ORDER BY {latest_order}
                ) AS __distinct_row_number
            FROM {table_identifier}
            {where_clause}
        ),
        distinct_rows AS (
            SELECT {selected_columns}
            FROM ranked_distinct_rows
            WHERE __distinct_row_number = 1
        )
        """
    ).format(
        selected_columns=selected_sql,
        distinct_columns=distinct_sql,
        latest_order=latest_order,
        table_identifier=_table_identifier(
            schema_name,
            table_name,
        ),
        where_clause=where_sql,
    )


def _fetch_distinct_column_totals(
    conn,
    cte_sql: sql.Composable,
    cte_params: Sequence[Any],
    columns: Sequence[str],
) -> Dict[str, Any]:
    """Calculate totals from the de-duplicated result, not raw rows."""
    totals: Dict[str, Any] = {
        column: None
        for column in columns
    }

    eligible_columns = [
        column
        for column in columns
        if _is_column_total_eligible(column)
    ]

    if not eligible_columns:
        return totals

    total_expressions: List[sql.Composable] = []

    for column in eligible_columns:
        column_identifier = sql.Identifier(column)

        numeric_expression = sql.SQL(
            """
            CASE
                WHEN BTRIM(COALESCE({column}::text, ''))
                     ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$'
                THEN BTRIM({column}::text)::numeric
                ELSE NULL
            END
            """
        ).format(column=column_identifier)

        total_expressions.append(
            sql.SQL(
                """
                CASE
                    WHEN COUNT({numeric_value}) > 0
                    THEN SUM({numeric_value})
                    ELSE NULL
                END AS {alias}
                """
            ).format(
                numeric_value=numeric_expression,
                alias=sql.Identifier(column),
            )
        )

    query = (
        cte_sql
        + sql.SQL(" SELECT ")
        + sql.SQL(", ").join(total_expressions)
        + sql.SQL(" FROM distinct_rows")
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, list(cte_params))
        row = cursor.fetchone() or {}

    for column in eligible_columns:
        totals[column] = _json_safe(row.get(column))

    return totals


def _execute_split_table_distinct_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    *,
    request_values: Optional[Mapping[str, Any]] = None,
    pagination_token: str = "split_table_tracking_distinct",
) -> Dict[str, Any]:
    """
    Render the table portion of Split Table with Tracking Distinct.

    Tracking is intentionally not handled here. For each split group,
    table rows are de-duplicated by the configured Distinct Based on
    column. The newest row in each duplicate set is retained. The tracking section
    continues to read every matching source record through the existing
    tracking enrichment logic.
    """
    allowed_per_page = [10, 25, 50, 100]

    columns = _resolve_table_columns(
        visual,
        valid_columns,
    )

    split_column = _resolve_split_column(
        visual,
        valid_columns,
    )

    if not split_column:
        return {
            "columns": columns,
            "source_columns": columns,
            "split_column": "",
            "groups": [],
            "group_count": 0,
            "allowed_per_page": allowed_per_page,
            "has_column_totals": True,
            "has_total_column": False,
            "distinct_table_rows": True,
            "configuration_warning": (
                "No valid split column was stored for this "
                "Split Table with Tracking Distinct visual."
            ),
        }

    selected_columns = list(columns)
    if split_column not in selected_columns:
        selected_columns.append(split_column)

    distinct_based_on = _resolve_distinct_based_on_column(
        visual,
        valid_columns,
        columns,
    )

    if not distinct_based_on:
        return {
            "columns": columns,
            "source_columns": columns,
            "split_column": split_column,
            "groups": [],
            "group_count": 0,
            "allowed_per_page": allowed_per_page,
            "has_column_totals": True,
            "has_total_column": False,
            "distinct_table_rows": True,
            "distinct_based_on": "",
            "configuration_warning": (
                "No valid Distinct Based on column was stored for this "
                "Split Table with Tracking Distinct visual."
            ),
        }

    latest_column = _resolve_distinct_latest_column(
        valid_columns,
        columns,
    )

    if latest_column and latest_column not in selected_columns:
        selected_columns.append(latest_column)

    # Only the selected Distinct Based on column defines duplicates.
    distinct_columns = [distinct_based_on]

    where_sql, where_params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    split_value_expression = sql.SQL(
        """
        COALESCE(
            NULLIF(BTRIM({split_column}::text), ''),
            'Unknown'
        )
        """
    ).format(
        split_column=sql.Identifier(split_column)
    )

    if _is_month_column(split_column):
        split_order = _month_order_from_expression(
            split_value_expression
        )
        split_values_query = (
            sql.SQL("SELECT ")
            + split_value_expression
            + sql.SQL(" AS split_value, ")
            + split_order
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + split_value_expression
            + sql.SQL(", ")
            + split_order
            + sql.SQL(
                " ORDER BY calendar_order ASC, split_value ASC"
            )
        )
    elif _is_year_column(split_column):
        split_identifier = sql.Identifier(split_column)
        split_order = sql.SQL(
            """
            CASE
                WHEN BTRIM(COALESCE({column}::text, '')) ~ '^[0-9]+$'
                THEN BTRIM({column}::text)::bigint
                ELSE NULL
            END
            """
        ).format(column=split_identifier)
        split_values_query = (
            sql.SQL("SELECT ")
            + split_value_expression
            + sql.SQL(" AS split_value, ")
            + split_order
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + split_value_expression
            + sql.SQL(", ")
            + split_order
            + sql.SQL(
                " ORDER BY calendar_order ASC NULLS LAST, split_value ASC"
            )
        )
    else:
        split_values_query = (
            sql.SQL("SELECT DISTINCT ")
            + split_value_expression
            + sql.SQL(" AS split_value FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" ORDER BY split_value ASC")
        )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(split_values_query, list(where_params))
        split_value_rows = [dict(row) for row in cursor.fetchall()]

    groups: List[Dict[str, Any]] = []

    for group_index, split_value_row in enumerate(
        split_value_rows,
        start=1,
    ):
        split_value = (
            _clean_text(split_value_row.get("split_value"))
            or "Unknown"
        )

        group_token = _safe_pagination_token(
            f"{pagination_token}_{group_index}_{split_value}"
        )
        page_parameter = f"split_page_{group_token}"
        per_page_parameter = f"split_per_page_{group_token}"

        current_page = max(
            1,
            _safe_integer(
                _mapping_value(request_values, page_parameter, 1),
                1,
            ),
        )
        per_page = _safe_integer(
            _mapping_value(request_values, per_page_parameter, 10),
            10,
        )
        if per_page not in allowed_per_page:
            per_page = 10

        group_where_sql = (
            where_sql
            + (sql.SQL(" AND ") if where_params else sql.SQL(" WHERE "))
            + split_value_expression
            + sql.SQL(" = %s")
        )
        group_params = list(where_params) + [split_value]

        cte_sql = _distinct_table_cte(
            schema_name=schema_name,
            table_name=table_name,
            selected_columns=selected_columns,
            distinct_columns=distinct_columns,
            latest_column=latest_column,
            where_sql=group_where_sql,
        )

        count_query = (
            cte_sql
            + sql.SQL(" SELECT COUNT(*) AS total_records FROM distinct_rows")
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(count_query, group_params)
            count_row = cursor.fetchone() or {}

        total_records = _safe_integer(
            count_row.get("total_records"),
            0,
        )
        total_pages = (
            math.ceil(total_records / per_page)
            if total_records
            else 1
        )
        current_page = min(current_page, total_pages)
        offset = (current_page - 1) * per_page

        preferred_order_columns = [
            latest_column,
            "updated_at",
            "submitted_at",
            "created_at",
            "id",
            "record_id",
        ]
        fallback_order_column = next(
            (
                column
                for column in preferred_order_columns
                if column and column in selected_columns
            ),
            columns[0],
        )

        if latest_column and latest_column in selected_columns:
            order_clause = sql.SQL(" ORDER BY {} DESC NULLS LAST").format(
                sql.Identifier(latest_column)
            )
        else:
            order_clause = _build_table_order_clause(
                columns,
                valid_columns,
                fallback_order_column,
            )

        data_query = (
            cte_sql
            + sql.SQL(" SELECT ")
            + sql.SQL(", ").join(
                sql.Identifier(column)
                for column in columns
            )
            + sql.SQL(" FROM distinct_rows")
            + order_clause
            + sql.SQL(" LIMIT %s OFFSET %s")
        )

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                data_query,
                group_params + [per_page, offset],
            )
            database_rows = [dict(row) for row in cursor.fetchall()]

        group_rows = [
            {
                column: _json_safe(row.get(column))
                for column in columns
            }
            for row in database_rows
        ]

        group_column_totals = _fetch_distinct_column_totals(
            conn=conn,
            cte_sql=cte_sql,
            cte_params=group_params,
            columns=columns,
        )

        if total_records > 0:
            group_rows.append(
                _build_column_total_row(
                    columns,
                    group_column_totals,
                )
            )

        groups.append(
            {
                "title": split_value,
                "split_value": split_value,
                "rows": group_rows,
                "column_totals": group_column_totals,
                "total_returned": len(database_rows),
                "total_records": total_records,
                "page": current_page,
                "per_page": per_page,
                "total_pages": total_pages,
                "showing_from": offset + 1 if total_records else 0,
                "showing_to": (
                    min(offset + len(database_rows), total_records)
                    if total_records
                    else 0
                ),
                "page_links": build_page_links(
                    current_page,
                    total_pages,
                ),
                "allowed_per_page": allowed_per_page,
                "page_parameter": page_parameter,
                "per_page_parameter": per_page_parameter,
                "order_column": fallback_order_column,
                "latest_record_column": latest_column,
                "distinct_columns": list(distinct_columns),
                "distinct_table_rows": True,
                "month_order_column": _find_month_column(columns),
                "calendar_order_applied": bool(
                    _find_month_column(columns)
                ),
            }
        )

    return {
        "columns": columns,
        "source_columns": columns,
        "split_column": split_column,
        "groups": groups,
        "group_count": len(groups),
        "allowed_per_page": allowed_per_page,
        "has_column_totals": True,
        "has_total_column": False,
        "distinct_table_rows": True,
        "latest_record_column": latest_column,
        "distinct_columns": list(distinct_columns),
        "split_group_calendar_order": (
            _is_month_column(split_column)
            or _is_year_column(split_column)
        ),
        "configuration_warning": "",
    }

def _resolve_tracking_columns(
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
) -> List[str]:
    """Resolve configured tracking fields to physical table columns."""
    configured_columns = _normalise_json_array(
        _first_configured_value(
            visual,
            "trackingColumns",
            "tracking_columns",
            "trackingFields",
            "tracking_fields",
            "timelineColumns",
            "timeline_columns",
        )
    )

    resolved_columns: List[str] = []

    for configured_column in configured_columns:
        resolved_column = _resolve_column_name(
            configured_column,
            valid_columns,
        )

        if (
            resolved_column
            and resolved_column not in resolved_columns
        ):
            resolved_columns.append(resolved_column)

    return resolved_columns


def _execute_split_table_tracking_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    *,
    request_values: Optional[Mapping[str, Any]] = None,
    pagination_token: str = "split_table_tracking",
    distinct_table_rows: bool = False,
) -> Dict[str, Any]:
    """
    Reuse the working Split Data Table and enrich each split group with
    professional date/time tracking.

    Each configured tracking column remains one milestone. When the split
    group contains multiple records, every distinct non-empty value for that
    tracking column is returned in chronological order. The first value is
    used as the milestone's primary date and the full list is available to
    the frontend through ``values``.
    """
    table_executor = (
        _execute_split_table_distinct_visual
        if distinct_table_rows
        else _execute_split_table_visual
    )

    result = table_executor(
        conn=conn,
        schema_name=schema_name,
        table_name=table_name,
        visual=visual,
        valid_columns=valid_columns,
        filter_values=filter_values,
        request_values=request_values,
        pagination_token=pagination_token,
    )

    result["distinct_table_rows"] = bool(
        distinct_table_rows
    )

    tracking_columns = _resolve_tracking_columns(
        visual,
        valid_columns,
    )

    result["tracking_columns"] = tracking_columns
    result["has_tracking"] = bool(tracking_columns)
    result["tracking_mode"] = "date_time_progress"

    if not tracking_columns:
        result["configuration_warning"] = (
            result.get("configuration_warning")
            or "No valid Tracking Columns were saved for this visual."
        )
        return result

    split_column = _clean_text(result.get("split_column"))

    if not split_column:
        return result

    where_sql, where_params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    split_value_expression = sql.SQL(
        """
        COALESCE(
            NULLIF(BTRIM({split_column}::text), ''),
            'Unknown'
        )
        """
    ).format(
        split_column=sql.Identifier(split_column)
    )

    tracking_select_columns = sql.SQL(", ").join(
        sql.SQL("NULLIF(BTRIM({column}::text), '') AS {alias}").format(
            column=sql.Identifier(column),
            alias=sql.Identifier(f"tracking_value_{index}"),
        )
        for index, column in enumerate(tracking_columns)
    )

    def _tracking_sort_key(value: Any) -> tuple:
        """Sort valid dates first, then keep non-date text stable."""
        cleaned = _clean_text(value)

        if not cleaned:
            return (2, datetime.max, "")

        normalised = cleaned.replace("Z", "+00:00")

        try:
            parsed = datetime.fromisoformat(normalised)
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return (0, parsed, cleaned.lower())
        except (TypeError, ValueError):
            pass

        supported_formats = (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y",
        )

        for date_format in supported_formats:
            try:
                return (
                    0,
                    datetime.strptime(cleaned, date_format),
                    cleaned.lower(),
                )
            except ValueError:
                continue

        return (1, datetime.max, cleaned.lower())

    for group in result.get("groups", []):
        split_value = (
            _clean_text(group.get("split_value"))
            or "Unknown"
        )

        group_where_sql = (
            where_sql
            + (
                sql.SQL(" AND ")
                if where_params
                else sql.SQL(" WHERE ")
            )
            + split_value_expression
            + sql.SQL(" = %s")
        )

        query = (
            sql.SQL("SELECT ")
            + tracking_select_columns
            + sql.SQL(" FROM ")
            + table_identifier
            + group_where_sql
        )

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                query,
                list(where_params) + [split_value],
            )
            tracking_rows = cursor.fetchall() or []

        tracking_steps: List[Dict[str, Any]] = []
        completed_steps = 0

        for index, column in enumerate(tracking_columns):
            alias = f"tracking_value_{index}"
            distinct_values: List[str] = []
            seen_values = set()

            for tracking_row in tracking_rows:
                cleaned_value = _clean_text(
                    tracking_row.get(alias)
                )

                if not cleaned_value:
                    continue

                duplicate_key = cleaned_value.casefold()

                if duplicate_key in seen_values:
                    continue

                seen_values.add(duplicate_key)
                distinct_values.append(cleaned_value)

            distinct_values.sort(key=_tracking_sort_key)

            completed = bool(distinct_values)

            if completed:
                completed_steps += 1

            primary_value = (
                distinct_values[0]
                if distinct_values
                else None
            )

            tracking_steps.append(
                {
                    "column": column,
                    "label": (
                        column
                        .replace("_", " ")
                        .strip()
                        .title()
                    ),
                    "value": (
                        _json_safe(primary_value)
                        if primary_value is not None
                        else None
                    ),
                    "primary_value": (
                        _json_safe(primary_value)
                        if primary_value is not None
                        else None
                    ),
                    "values": [
                        _json_safe(value)
                        for value in distinct_values
                    ],
                    "occurrence_count": len(distinct_values),
                    "status": (
                        "completed"
                        if completed
                        else "pending"
                    ),
                    "completed": completed,
                    "position": index + 1,
                }
            )

        total_steps = len(tracking_steps)

        group["tracking"] = tracking_steps
        group["tracking_completed"] = completed_steps
        group["tracking_total"] = total_steps
        group["tracking_progress"] = (
            round(
                completed_steps / total_steps * 100,
                2,
            )
            if total_steps
            else 0
        )

    return result


def _parse_tracking_datetime(value: Any) -> Optional[datetime]:
    """
    Parse tracking timestamps using the PostgreSQL timestamp structure
    used by the application, for example:

        2026-01-30 18:51:46.748926+02

    The value is interpreted strictly as YEAR-MONTH-DAY. Timezone-aware
    timestamps are normalised to UTC before durations are calculated so
    that offsets such as +02, +02:00 and Z are handled consistently.
    """
    if value is None:
        return None

    # psycopg2 may already return a Python datetime object. Preserve the
    # actual year/month/day fields instead of converting it through a
    # locale-sensitive display string.
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        cleaned = _clean_text(value)

        if not cleaned:
            return None

        # PostgreSQL may emit offsets as +02 or -05. Python's ISO parser
        # is most reliable with the explicit +02:00 / -05:00 form.
        normalised = cleaned.strip().replace("Z", "+00:00")
        normalised = re.sub(
            r"([+-]\d{2})$",
            r"\1:00",
            normalised,
        )

        # Accept a space or T between the date and time, while always
        # retaining the ISO YEAR-MONTH-DAY interpretation.
        try:
            parsed = datetime.fromisoformat(normalised)
        except (TypeError, ValueError):
            parsed = None

        if parsed is None:
            for date_format in (
                "%Y-%m-%d %H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    parsed = datetime.strptime(normalised, date_format)
                    break
                except ValueError:
                    continue

        if parsed is None:
            return None

    # Compare all timezone-aware values at the same instant. Naive
    # values remain naive because PostgreSQL timestamp-without-time-zone
    # values do not carry an offset.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def _enrich_split_tracking_distinct_graphics(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the categorical tracking-line payload used by
    Split Table with Tracking Distinct Graphics.

    Axis contract:
    - X-axis: the configured Tracking Columns, in the saved order.
    - Y-axis: every distinct value from Distinct Based On.
    - One separate line: one distinct value, for example one student.
    - Point label: average elapsed days from the immediately previous
      tracking column to the current tracking column.

    When more than one source row exists for the same distinct value,
    each transition is averaged across all valid non-negative date pairs.
    """
    tracking_columns = _resolve_tracking_columns(
        visual,
        valid_columns,
    )

    configured_order = _normalise_json_array(
        _first_configured_value(
            visual,
            "trackingOrder",
            "tracking_order",
        )
    )

    tracking_order: List[str] = []

    for candidate in configured_order:
        resolved = _resolve_column_name(
            candidate,
            valid_columns,
        )

        if (
            resolved
            and resolved in tracking_columns
            and resolved not in tracking_order
        ):
            tracking_order.append(resolved)

    for column in tracking_columns:
        if column not in tracking_order:
            tracking_order.append(column)

    distinct_based_on = _resolve_distinct_based_on_column(
        visual,
        valid_columns,
        _resolve_table_columns(visual, valid_columns),
    )

    result["tracking_order"] = tracking_order
    result["tracking_graphics_enabled"] = True
    result["tracking_graphics_distinct_column"] = distinct_based_on
    result["tracking_axis_mode"] = "distinct_y_tracking_x"

    if len(tracking_order) < 2 or not distinct_based_on:
        result["configuration_warning"] = (
            result.get("configuration_warning")
            or (
                "Tracking graphics requires a Distinct Based on "
                "column and at least two ordered Tracking Columns."
            )
        )
        return result

    split_column = _clean_text(result.get("split_column"))

    if not split_column:
        return result

    where_sql, where_params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    table_identifier = _table_identifier(
        schema_name,
        table_name,
    )

    split_expression = sql.SQL(
        "COALESCE(NULLIF(BTRIM({column}::text), ''), 'Unknown')"
    ).format(
        column=sql.Identifier(split_column)
    )

    selected_parts = [
        sql.SQL(
            "COALESCE(NULLIF(BTRIM({column}::text), ''), "
            "'Unknown') AS __distinct_value"
        ).format(
            column=sql.Identifier(distinct_based_on)
        )
    ]

    for index, column in enumerate(tracking_order):
        selected_parts.append(
            sql.SQL(
                "NULLIF(BTRIM({column}::text), '') AS {alias}"
            ).format(
                column=sql.Identifier(column),
                alias=sql.Identifier(f"__tracking_{index}"),
            )
        )

    x_categories = [
        column.replace("_", " ").strip().title()
        for column in tracking_order
    ]

    for group in result.get("groups", []):
        split_value = (
            _clean_text(group.get("split_value"))
            or "Unknown"
        )

        group_where = (
            where_sql
            + (
                sql.SQL(" AND ")
                if where_params
                else sql.SQL(" WHERE ")
            )
            + split_expression
            + sql.SQL(" = %s")
        )

        query = (
            sql.SQL("SELECT ")
            + sql.SQL(", ").join(selected_parts)
            + sql.SQL(" FROM ")
            + table_identifier
            + group_where
        )

        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                query,
                list(where_params) + [split_value],
            )

            rows = [
                dict(row)
                for row in cursor.fetchall()
            ]

        by_distinct: Dict[str, List[Dict[str, Any]]] = {}

        for row in rows:
            distinct_value = (
                _clean_text(row.get("__distinct_value"))
                or "Unknown"
            )

            by_distinct.setdefault(
                distinct_value,
                [],
            ).append(row)

        y_categories = sorted(
            by_distinct.keys(),
            key=lambda value: value.casefold(),
        )

        series: List[Dict[str, Any]] = []

        for y_index, distinct_value in enumerate(y_categories):
            distinct_rows = by_distinct.get(
                distinct_value,
                [],
            )

            points: List[Dict[str, Any]] = []

            first_available = any(
                _parse_tracking_datetime(
                    row.get("__tracking_0")
                )
                for row in distinct_rows
            )

            if first_available:
                points.append(
                    {
                        "x_index": 0,
                        "y_index": y_index,
                        "tracking_column": tracking_order[0],
                        "tracking_label": x_categories[0],
                        "elapsed_days": 0,
                        "sample_count": sum(
                            1
                            for row in distinct_rows
                            if _parse_tracking_datetime(
                                row.get("__tracking_0")
                            )
                        ),
                        "is_start": True,
                    }
                )

            for tracking_index in range(1, len(tracking_order)):
                durations_days: List[float] = []

                for row in distinct_rows:
                    previous_date = _parse_tracking_datetime(
                        row.get(
                            f"__tracking_{tracking_index - 1}"
                        )
                    )

                    current_date = _parse_tracking_datetime(
                        row.get(
                            f"__tracking_{tracking_index}"
                        )
                    )

                    if not previous_date or not current_date:
                        continue

                    elapsed_days = (
                        current_date - previous_date
                    ).total_seconds() / 86400.0

                    if elapsed_days >= 0:
                        durations_days.append(elapsed_days)

                if not durations_days:
                    continue

                average_days = round(
                    sum(durations_days) / len(durations_days),
                    2,
                )

                points.append(
                    {
                        "x_index": tracking_index,
                        "y_index": y_index,
                        "tracking_column": tracking_order[
                            tracking_index
                        ],
                        "tracking_label": x_categories[
                            tracking_index
                        ],
                        "from_column": tracking_order[
                            tracking_index - 1
                        ],
                        "from_label": x_categories[
                            tracking_index - 1
                        ],
                        "elapsed_days": average_days,
                        "sample_count": len(durations_days),
                        "is_start": False,
                    }
                )

            if points:
                series.append(
                    {
                        "name": distinct_value,
                        "distinct_value": distinct_value,
                        "y_index": y_index,
                        "points": points,
                    }
                )

        group["tracking_graphics"] = {
            "x_categories": x_categories,
            "y_categories": y_categories,
            "categories": x_categories,
            "series": series,
            "unit": "days",
            "distinct_column": distinct_based_on,
            "tracking_order": tracking_order,
            "axis_mode": "distinct_y_tracking_x",
            "x_axis_title": "Tracking Columns",
            "y_axis_title": (
                distinct_based_on
                .replace("_", " ")
                .strip()
                .title()
            ),
        }

    return result

def _dimension_text_expression(column_name: str) -> sql.Composable:
    """Return the common non-empty text expression used by matrix visuals."""
    return sql.SQL(
        """
        COALESCE(
            NULLIF(BTRIM({column}::text), ''),
            'Unknown'
        )
        """
    ).format(column=sql.Identifier(column_name))


def _ordered_distinct_dimension_values(
    conn,
    schema_name: str,
    table_name: str,
    column_name: str,
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
) -> List[str]:
    """Fetch distinct dimension values, applying calendar ordering where relevant."""
    if column_name not in valid_columns:
        raise ValueError(
            f'Configured column "{column_name}" does not exist in the selected form table.'
        )

    expression = _dimension_text_expression(column_name)
    where_sql, where_params = _build_where_clause(filter_values, valid_columns)
    table_identifier = _table_identifier(schema_name, table_name)

    if _is_month_column(column_name):
        order_expression = _month_order_from_expression(expression)
        query = (
            sql.SQL("SELECT ")
            + expression
            + sql.SQL(" AS label, ")
            + order_expression
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + expression
            + sql.SQL(", ")
            + order_expression
            + sql.SQL(" ORDER BY calendar_order ASC, label ASC")
        )
    elif _is_year_column(column_name):
        identifier = sql.Identifier(column_name)
        order_expression = sql.SQL(
            """
            CASE
                WHEN BTRIM(COALESCE({column}::text, '')) ~ '^[0-9]+$'
                THEN BTRIM({column}::text)::bigint
                ELSE NULL
            END
            """
        ).format(column=identifier)
        query = (
            sql.SQL("SELECT ")
            + expression
            + sql.SQL(" AS label, ")
            + order_expression
            + sql.SQL(" AS calendar_order FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" GROUP BY ")
            + expression
            + sql.SQL(", ")
            + order_expression
            + sql.SQL(" ORDER BY calendar_order ASC NULLS LAST, label ASC")
        )
    else:
        query = (
            sql.SQL("SELECT DISTINCT ")
            + expression
            + sql.SQL(" AS label FROM ")
            + table_identifier
            + where_sql
            + sql.SQL(" ORDER BY label ASC")
        )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, list(where_params))
        return [
            _clean_text(row.get("label")) or "Unknown"
            for row in cursor.fetchall()
        ]


def _execute_grouped_column_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
) -> Dict[str, Any]:
    """
    Execute the dedicated Grouped Column Chart.

    The saved Category / X-Axis column supplies the chart categories.

    Every column saved in ``yValues`` is aggregated independently and
    returned as one side-by-side series. The old Group / Series column
    is not required.

    Older saved configurations remain compatible:
    - If ``yValues`` is unavailable, the existing single ``value``
      column is used as a one-item Y-value list.
    """
    mapping = _resolve_visual_mapping(
        visual,
        valid_columns,
    )

    category_field = mapping["group_field"]
    aggregation = mapping["aggregation"]

    if not category_field:
        raise ValueError(
            "No Category / X Axis column was saved for the "
            "Grouped Column Chart."
        )

    # ========================================================
    # MULTIPLE Y-VALUE COLUMNS
    # ========================================================

    configured_y_values = _first_configured_value(
        visual,
        "yValues",
        "y_values",
        "valueColumns",
        "value_columns",
        "measureColumns",
        "measure_columns",
        "selectedYValues",
        "selected_y_values",
    )

    y_value_candidates = _normalise_json_array(
        configured_y_values
    )

    # Backward compatibility for a configuration saved before
    # multiple Y-values were introduced.
    if not y_value_candidates:
        old_single_value = _first_configured_value(
            visual,
            "value",
            "yAxis",
            "y_axis",
            "measureField",
            "measure_field",
        )

        parsed_old_value = _parse_axis_selection(
            old_single_value
        )

        old_single_value = (
            parsed_old_value.get("column")
            or parsed_old_value.get("option")
            or ""
        )

        if _clean_text(old_single_value):
            y_value_candidates = [
                old_single_value
            ]

    y_value_fields: List[str] = []

    for configured_column in y_value_candidates:
        resolved_column = _resolve_column_name(
            configured_column,
            valid_columns,
        )

        if (
            resolved_column
            and resolved_column not in y_value_fields
        ):
            y_value_fields.append(
                resolved_column
            )

    if not y_value_fields:
        raise ValueError(
            "No Y-Value columns were saved for the "
            "Grouped Column Chart."
        )

    category_expression = _dimension_text_expression(
        category_field
    )

    where_sql, params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    # Build one aggregate expression for every selected Y-value
    # column. Each expression is assigned a safe generated alias.
    aggregate_select_parts: List[sql.Composable] = []

    for index, y_value_field in enumerate(
        y_value_fields
    ):
        aggregate_select_parts.append(
            _aggregation_expression(
                aggregation,
                y_value_field,
                valid_columns,
            )
            + sql.SQL(" AS ")
            + sql.Identifier(
                f"series_value_{index}"
            )
        )

    query = (
        sql.SQL("SELECT ")
        + category_expression
        + sql.SQL(" AS category, ")
        + sql.SQL(", ").join(
            aggregate_select_parts
        )
        + sql.SQL(" FROM ")
        + _table_identifier(
            schema_name,
            table_name,
        )
        + where_sql
        + sql.SQL(" GROUP BY ")
        + category_expression
    )

    with conn.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            query,
            list(params),
        )

        grouped_rows = [
            dict(row)
            for row in cursor.fetchall()
        ]

    category_order = (
        _ordered_distinct_dimension_values(
            conn,
            schema_name,
            table_name,
            category_field,
            valid_columns,
            filter_values,
        )
    )

    category_rank = {
        value: index
        for index, value in enumerate(
            category_order
        )
    }

    grouped_rows.sort(
        key=lambda row: category_rank.get(
            _clean_text(
                row.get("category")
            ) or "Unknown",
            10**9,
        )
    )

    items: List[Dict[str, Any]] = []

    for row in grouped_rows:
        category_value = (
            _clean_text(
                row.get("category")
            )
            or "Unknown"
        )

        for index, y_value_field in enumerate(
            y_value_fields
        ):
            items.append(
                {
                    "category": category_value,
                    "series": y_value_field,
                    "value": _json_safe(
                        row.get(
                            f"series_value_{index}"
                        )
                        or 0
                    ),
                }
            )

    # For percentage, calculate each selected Y-value column as
    # its own series percentage across the returned X categories.
    if aggregation == "percentage":
        series_totals: Dict[str, Decimal] = {
            y_value_field: Decimal("0")
            for y_value_field in y_value_fields
        }

        for item in items:
            series_name = _clean_text(
                item.get("series")
            )

            series_totals[series_name] = (
                series_totals.get(
                    series_name,
                    Decimal("0"),
                )
                + Decimal(
                    str(
                        item.get("value")
                        or 0
                    )
                )
            )

        for item in items:
            series_name = _clean_text(
                item.get("series")
            )

            total_value = series_totals.get(
                series_name,
                Decimal("0"),
            )

            raw_value = Decimal(
                str(
                    item.get("value")
                    or 0
                )
            )

            item["value"] = (
                float(
                    raw_value
                    / total_value
                    * Decimal("100")
                )
                if total_value
                else 0
            )

    return {
        "categories": category_order,

        # Each selected Y-value column is now a chart series.
        "series": y_value_fields,
        "y_values": y_value_fields,

        "items": items,
        "aggregation": aggregation,
        "category_field": category_field,

        # Kept as an empty value for compatibility with templates
        # or consumers that still inspect this property.
        "series_field": "",

        # The chart now has multiple measure fields.
        "measure_field": (
            y_value_fields[0]
            if y_value_fields
            else ""
        ),
        "measure_fields": y_value_fields,
        "is_percentage": (
            aggregation == "percentage"
        ),
        "calendar_order_applied": (
            _is_month_column(
                category_field
            )
            or _is_year_column(
                category_field
            )
        ),
    }


def _execute_table_total_visual(
    conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    *,
    table_page: int = 1,
    table_per_page: int = 10,
    table_page_parameter: str = "",
    table_per_page_parameter: str = "",
) -> Dict[str, Any]:
    """
    Execute the Table Total matrix with server-side pagination.

    The distinct First Column values form the paginated table rows. The
    distinct Second Column values become dynamic headers, without adding
    the physical Second Column name as an extra heading.
    """
    allowed_per_page = [10, 25, 50, 100]

    first_column = _resolve_column_name(
        _first_configured_value(
            visual,
            "tableTotalFirstColumn",
            "table_total_first_column",
            "firstColumn",
            "first_column",
            "rowColumn",
            "row_column",
        ),
        valid_columns,
    )
    second_column = _resolve_column_name(
        _first_configured_value(
            visual,
            "tableTotalSecondColumn",
            "table_total_second_column",
            "secondColumn",
            "second_column",
            "headerColumn",
            "header_column",
        ),
        valid_columns,
    )
    value_column = _resolve_column_name(
        _first_configured_value(
            visual,
            "tableTotalValueColumn",
            "table_total_value_column",
            "totalValueColumn",
            "total_value_column",
            "measureColumn",
            "measure_column",
            "value",
        ),
        valid_columns,
    )
    aggregation = _normalise_aggregation_name(
        _first_configured_value(visual, "aggregation", "aggregate", "summary")
    )

    if not first_column:
        raise ValueError("No First Column was saved for the Table Total.")
    if not second_column:
        raise ValueError("No Second Column was saved for the Table Total.")
    if first_column == second_column:
        raise ValueError("The Table Total First Column and Second Column must be different.")
    if not value_column and aggregation not in {"count", "distinct_count"}:
        raise ValueError("No Total Value Column was saved for the Table Total.")

    table_page = max(1, _safe_integer(table_page, 1))
    table_per_page = _safe_integer(table_per_page, 10)
    if table_per_page not in allowed_per_page:
        table_per_page = 10

    row_values = _ordered_distinct_dimension_values(
        conn, schema_name, table_name, first_column, valid_columns, filter_values
    )
    header_values = _ordered_distinct_dimension_values(
        conn, schema_name, table_name, second_column, valid_columns, filter_values
    )

    total_records = len(row_values)
    total_pages = math.ceil(total_records / table_per_page) if total_records else 1
    table_page = min(table_page, total_pages)
    offset = (table_page - 1) * table_per_page
    page_row_values = row_values[offset: offset + table_per_page]

    first_expression = _dimension_text_expression(first_column)
    second_expression = _dimension_text_expression(second_column)
    aggregate_expression = _aggregation_expression(
        aggregation,
        value_column,
        valid_columns,
    )
    where_sql, where_params = _build_where_clause(filter_values, valid_columns)

    rows = []
    if page_row_values:
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in page_row_values)
        query = (
            sql.SQL("SELECT ")
            + first_expression
            + sql.SQL(" AS row_label, ")
            + second_expression
            + sql.SQL(" AS header_label, ")
            + aggregate_expression
            + sql.SQL(" AS value FROM ")
            + _table_identifier(schema_name, table_name)
            + where_sql
            + (sql.SQL(" AND ") if where_params else sql.SQL(" WHERE "))
            + first_expression
            + sql.SQL(" IN (")
            + placeholders
            + sql.SQL(") GROUP BY ")
            + first_expression
            + sql.SQL(", ")
            + second_expression
        )

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, list(where_params) + list(page_row_values))
            rows = [dict(row) for row in cursor.fetchall()]

    if aggregation == "percentage":
        total_value = sum(Decimal(str(row.get("value") or 0)) for row in rows)
        for row in rows:
            raw_value = Decimal(str(row.get("value") or 0))
            row["value"] = float(raw_value / total_value * Decimal("100")) if total_value else 0

    lookup = {
        (
            _clean_text(row.get("row_label")) or "Unknown",
            _clean_text(row.get("header_label")) or "Unknown",
        ): _json_safe(row.get("value") or 0)
        for row in rows
    }

    matrix_rows = []
    for row_label in page_row_values:
        cells = {
            header: lookup.get((row_label, header), 0)
            for header in header_values
        }
        matrix_rows.append(
            {
                "label": row_label,
                "cells": cells,
                "row_total": _json_safe(
                    sum(Decimal(str(value or 0)) for value in cells.values())
                ),
            }
        )

    column_totals = {
        header: _json_safe(
            sum(
                Decimal(str(row["cells"].get(header) or 0))
                for row in matrix_rows
            )
        )
        for header in header_values
    }
    grand_total = _json_safe(
        sum(Decimal(str(row.get("row_total") or 0)) for row in matrix_rows)
    )

    showing_from = offset + 1 if total_records else 0
    showing_to = min(offset + len(page_row_values), total_records) if total_records else 0

    return {
        "first_column": first_column,
        "second_column": second_column,
        "value_column": value_column,
        "row_header": first_column,
        "headers": header_values,
        "rows": matrix_rows,
        "column_totals": column_totals,
        "grand_total": grand_total,
        "aggregation": aggregation,
        "total_records": total_records,
        "page": table_page,
        "per_page": table_per_page,
        "total_pages": total_pages,
        "showing_from": showing_from,
        "showing_to": showing_to,
        "page_links": build_page_links(table_page, total_pages),
        "allowed_per_page": allowed_per_page,
        "page_parameter": table_page_parameter,
        "per_page_parameter": table_per_page_parameter,
        "calendar_order_applied": (
            _is_month_column(second_column)
            or _is_year_column(second_column)
        ),
    }


def _build_visual_result(
        conn,
    schema_name: str,
    table_name: str,
    visual: Mapping[str, Any],
    valid_columns: Sequence[str],
    filter_values: Mapping[str, str],
    *,
    table_page: int = 1,
    table_per_page: int = 10,
    table_page_parameter: str = "",
    table_per_page_parameter: str = "",
    request_values: Optional[Mapping[str, Any]] = None,
    pagination_token: str = "",
) -> Dict[str, Any]:
    """
    Execute one configured visual.

    Newly configured chart types use the same grouped dataset contract
    as the existing bar, column and line charts.
    """
    visual_type = _normalise_visual_type(
        _first_configured_value(
            visual,
            "type",
            "visualType",
            "visual_type",
            "chartType",
            "chart_type",
        )
    )

    result = {
        "id": _clean_text(visual.get("id")),
        "title": (
            _clean_text(visual.get("title"))
            or "Untitled Visual"
        ),
        "type": visual_type,
        "note": _clean_text(visual.get("note")),
        "target": _json_safe(visual.get("target")),
        "legend": _clean_text(visual.get("legend")),
        "category": _clean_text(visual.get("category")),
        "value": _clean_text(visual.get("value")),
        "aggregation": (
            _clean_text(visual.get("aggregation"))
            or "sum"
        ),
        "tableColumns": _normalise_json_array(
            visual.get(
                "tableColumns",
                visual.get("table_columns", []),
            )
        ),
        "trackingColumns": _normalise_json_array(
            _first_configured_value(
                visual,
                "trackingColumns",
                "tracking_columns",
                "trackingFields",
                "tracking_fields",
            )
        ),
        "splitColumn": _resolve_split_column(
            visual,
            valid_columns,
        ),
        "tableTotalFirstColumn": _clean_text(
            _first_configured_value(
                visual,
                "tableTotalFirstColumn",
                "table_total_first_column",
                "firstColumn",
                "first_column",
            )
        ),
        "tableTotalSecondColumn": _clean_text(
            _first_configured_value(
                visual,
                "tableTotalSecondColumn",
                "table_total_second_column",
                "secondColumn",
                "second_column",
            )
        ),
        "tableTotalValueColumn": _clean_text(
            _first_configured_value(
                visual,
                "tableTotalValueColumn",
                "table_total_value_column",
                "totalValueColumn",
                "total_value_column",
            )
        ),
        "error": "",
        "data": {},
    }

    try:
        if visual_type in {"kpi", "gauge"}:
            result["data"] = _execute_single_value_visual(
                conn,
                schema_name,
                table_name,
                visual,
                valid_columns,
                filter_values,
            )

        elif visual_type == "table":
            result["data"] = _execute_table_visual(
                conn,
                schema_name,
                table_name,
                visual,
                valid_columns,
                filter_values,
                table_page=table_page,
                table_per_page=table_per_page,
                table_page_parameter=table_page_parameter,
                table_per_page_parameter=table_per_page_parameter,
            )

        elif visual_type == "split_table":
            normalised_split_visual = dict(visual)
            normalised_split_visual["splitColumn"] = (
                result["splitColumn"]
            )

            result["data"] = _execute_split_table_visual(
                conn,
                schema_name,
                table_name,
                normalised_split_visual,
                valid_columns,
                filter_values,
                request_values=request_values,
                pagination_token=pagination_token,
            )

        elif visual_type == "split_table_tracking":
            normalised_tracking_visual = dict(visual)
            normalised_tracking_visual["splitColumn"] = (
                result["splitColumn"]
            )
            normalised_tracking_visual["trackingColumns"] = (
                result["trackingColumns"]
            )

            result["data"] = (
                _execute_split_table_tracking_visual(
                    conn,
                    schema_name,
                    table_name,
                    normalised_tracking_visual,
                    valid_columns,
                    filter_values,
                    request_values=request_values,
                    pagination_token=pagination_token,
                )
            )

        elif visual_type == "split_table_tracking_distinct":
            normalised_tracking_visual = dict(visual)
            normalised_tracking_visual["splitColumn"] = (
                result["splitColumn"]
            )
            normalised_tracking_visual["trackingColumns"] = (
                result["trackingColumns"]
            )

            result["data"] = (
                _execute_split_table_tracking_visual(
                    conn,
                    schema_name,
                    table_name,
                    normalised_tracking_visual,
                    valid_columns,
                    filter_values,
                    request_values=request_values,
                    pagination_token=pagination_token,
                    distinct_table_rows=True,
                )
            )


        elif visual_type == "split_table_tracking_distinct_graphics":
            normalised_tracking_visual = dict(visual)
            normalised_tracking_visual["splitColumn"] = result["splitColumn"]
            normalised_tracking_visual["trackingColumns"] = result["trackingColumns"]
            configured_tracking_order = _normalise_json_array(
                _first_configured_value(
                    visual,
                    "trackingOrder",
                    "tracking_order",
                )
            )

            normalised_tracking_visual["trackingOrder"] = (
                configured_tracking_order
            )
            normalised_tracking_visual["tracking_order"] = (
                configured_tracking_order
            )

            result["data"] = _execute_split_table_tracking_visual(
                conn,
                schema_name,
                table_name,
                normalised_tracking_visual,
                valid_columns,
                filter_values,
                request_values=request_values,
                pagination_token=pagination_token,
                distinct_table_rows=True,
            )

            result["data"] = _enrich_split_tracking_distinct_graphics(
                conn,
                schema_name,
                table_name,
                normalised_tracking_visual,
                valid_columns,
                filter_values,
                result["data"],
            )

        elif visual_type == "table_total":
            result["data"] = _execute_table_total_visual(
                conn,
                schema_name,
                table_name,
                visual,
                valid_columns,
                filter_values,
                table_page=table_page,
                table_per_page=table_per_page,
                table_page_parameter=table_page_parameter,
                table_per_page_parameter=table_per_page_parameter,
            )

        elif visual_type == "grouped_column":
            result["data"] = _execute_grouped_column_visual(
                conn,
                schema_name,
                table_name,
                visual,
                valid_columns,
                filter_values,
            )

        elif visual_type in {
            "bar",
            "stacked_bar",
            "column",
            "stacked_column",
            "line",
            "area",
            "combo",
            "donut",
            "pie",
            "funnel",
            "treemap",
            "heatmap",
            "waterfall",
            "radar",
        }:
            result["data"] = _execute_grouped_visual(
                conn,
                schema_name,
                table_name,
                visual,
                valid_columns,
                filter_values,
            )

        else:
            result["error"] = (
                f'Unsupported visual type "{visual_type}".'
            )

    except Exception as exc:
        result["error"] = str(exc)

    return result


def _count_matching_rows(
    conn,
    schema_name: str,
    table_name: str,
    filter_values: Mapping[str, str],
    valid_columns: Sequence[str],
) -> int:
    """
    Count all records matching the currently selected report filters.
    """

    where_sql, params = _build_where_clause(
        filter_values,
        valid_columns,
    )

    query = (
        sql.SQL("SELECT COUNT(*) AS matching_row_count FROM ")
        + _table_identifier(schema_name, table_name)
        + where_sql
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone() or {}

    return _safe_integer(
        row.get("matching_row_count"),
        0,
    )

# Normalizing the months
def _is_year_column(
    column_name: Any,
) -> bool:
    """
    Identify dynamic Year columns without depending on casing,
    spaces, underscores, or plural naming.
    """
    cleaned = re.sub(
        r"[^a-z0-9]+",
        "_",
        _clean_text(column_name).lower(),
    ).strip("_")

    return cleaned in {
        "year",
        "years",
        "calendar_year",
        "reporting_year",
    }


def _find_month_column(
    columns: Sequence[str],
) -> str:
    """
    Return the first configured physical Month column.
    """
    return next(
        (
            column
            for column in columns
            if _is_month_column(column)
        ),
        "",
    )


def _find_year_column(
    columns: Sequence[str],
) -> str:
    """
    Return the first configured physical Year column.
    """
    return next(
        (
            column
            for column in columns
            if _is_year_column(column)
        ),
        "",
    )


def _year_order_expression(
    column_name: str,
) -> sql.Composable:
    """
    Order a Year column numerically where possible.

    Non-numeric values are placed after valid numeric years.
    """
    column_identifier = sql.Identifier(
        column_name
    )

    return sql.SQL(
        """
        CASE
            WHEN BTRIM(COALESCE({column}::text, ''))
                 ~ '^[0-9]+$'
            THEN BTRIM({column}::text)::bigint
            ELSE NULL
        END
        """
    ).format(
        column=column_identifier
    )


def _build_table_order_clause(
    selected_columns: Sequence[str],
    valid_columns: Sequence[str],
    fallback_column: str,
) -> sql.Composable:
    """
    Build a consistent ORDER BY clause for normal and split tables.

    Priority:

    1. Year ascending, when selected.
    2. Month in January-to-December order, when selected.
    3. Stable fallback column such as ID or created_at.

    This means table records do not depend on the physical insertion
    order in PostgreSQL.
    """
    order_expressions: List[sql.Composable] = []
    used_columns = set()

    selected_columns = [
        column
        for column in selected_columns
        if column in valid_columns
    ]

    year_column = _find_year_column(
        selected_columns
    )

    month_column = _find_month_column(
        selected_columns
    )

    if year_column:
        order_expressions.append(
            _year_order_expression(
                year_column
            )
            + sql.SQL(" ASC NULLS LAST")
        )

        used_columns.add(
            year_column
        )

    if month_column:
        order_expressions.append(
            _month_order_expression(
                month_column
            )
            + sql.SQL(" ASC")
        )

        order_expressions.append(
            sql.Identifier(month_column)
            + sql.SQL(" ASC NULLS LAST")
        )

        used_columns.add(
            month_column
        )

    if (
        fallback_column
        and fallback_column in valid_columns
        and fallback_column not in used_columns
    ):
        order_expressions.append(
            sql.Identifier(fallback_column)
            + sql.SQL(" ASC NULLS LAST")
        )

    if not order_expressions:
        fallback = next(
            iter(valid_columns),
            "",
        )

        if fallback:
            order_expressions.append(
                sql.Identifier(fallback)
                + sql.SQL(" ASC NULLS LAST")
            )

    if not order_expressions:
        return sql.SQL("")

    return (
        sql.SQL(" ORDER BY ")
        + sql.SQL(", ").join(
            order_expressions
        )
    )

# ============================================================
# PUBLIC FUNCTION CALLED BY THE ENDPOINT
# ============================================================



def get_bi_form_mapping_view_report_context(
    conn,
    *,
    bi_view_name: str,
    database_table: str,
    filters: Optional[Mapping[str, Any]] = None,
    execute_visuals: bool = True,
) -> Dict[str, Any]:
    """
    Fetch one saved BI configuration, execute every configured visual,
    build dynamic KPI cards and filters, and return ordered report pages.

    Page names are returned as clickable tabs by the template.
    """

    cleaned_view_name = _clean_text(bi_view_name)
    cleaned_database_table = _clean_text(database_table)

    if not cleaned_view_name:
        raise ValueError("The BI view name is required.")

    if not cleaned_database_table:
        raise ValueError("The mapped database table is required.")

    form_definition = _fetch_form_definition(
        conn,
        cleaned_view_name,
        cleaned_database_table,
    )

    schema_name, table_name = _split_qualified_table_name(
        form_definition["dynamic_table_name"]
    )

    if not _table_exists(conn, schema_name, table_name):
        raise ValueError(
            f'The mapped table "{schema_name}.{table_name}" does not exist.'
        )

    table_columns = _fetch_table_columns(
        conn,
        schema_name,
        table_name,
    )

    valid_columns = [
        row["column_name"]
        for row in table_columns
    ]

    saved_configuration = _fetch_saved_configuration(
        conn,
        cleaned_view_name,
    )

    pages = _normalise_pages(
        saved_configuration.get("dashboard_pages", {})
    )

    filter_columns = _collect_filter_columns(
        pages,
        valid_columns,
    )

    selected_filters = _normalise_filter_values(
        filters,
        filter_columns,
    )

    filter_definitions = _fetch_filter_options(
        conn,
        schema_name,
        table_name,
        filter_columns,
        valid_columns,
    )

    matching_row_count = _count_matching_rows(
        conn,
        schema_name,
        table_name,
        selected_filters,
        valid_columns,
    ) if execute_visuals else 0

    page_results: List[Dict[str, Any]] = []
    all_kpi_visuals: List[Dict[str, Any]] = []

    for page_index, page in enumerate(pages, start=1):
        visual_results: List[Dict[str, Any]] = []

        if execute_visuals:
            for visual_index, visual in enumerate(
                page.get("visuals", []),
                start=1,
            ):
                visual_id = (
                    _clean_text(visual.get("id"))
                    or f"visual_{visual_index}"
                )

                pagination_token = _safe_pagination_token(
                    f"{page.get('id', page_index)}_"
                    f"{visual_id}_{visual_index}"
                )

                table_page_parameter = (
                    f"table_page_{pagination_token}"
                )
                table_per_page_parameter = (
                    f"table_per_page_{pagination_token}"
                )

                visual_result = _build_visual_result(
                    conn=conn,
                    schema_name=schema_name,
                    table_name=table_name,
                    visual=visual,
                    valid_columns=valid_columns,
                    filter_values=dict(selected_filters),
                    table_page=_safe_integer(
                        _mapping_value(
                            filters,
                            table_page_parameter,
                            1,
                        ),
                        1,
                    ),
                    table_per_page=_safe_integer(
                        _mapping_value(
                            filters,
                            table_per_page_parameter,
                            10,
                        ),
                        10,
                    ),
                    table_page_parameter=table_page_parameter,
                    table_per_page_parameter=table_per_page_parameter,
                    request_values=filters,
                    pagination_token=pagination_token,
                )

                visual_results.append(visual_result)

        kpi_visuals = [
            visual
            for visual in visual_results
            if visual.get("type") == "kpi"
        ]

        non_kpi_visuals = [
            visual
            for visual in visual_results
            if visual.get("type") != "kpi"
        ]

        all_kpi_visuals.extend(
            {
                **visual,
                "page_id": page["id"],
                "page_name": page["name"],
            }
            for visual in kpi_visuals
        )

        page_results.append(
            {
                **page,
                "selected_filters": dict(selected_filters),
                "kpi_visuals": kpi_visuals,
                "visuals": non_kpi_visuals,
                "all_visuals": visual_results,
            }
        )

    return {
        "bi_view_id": saved_configuration.get("bi_view_id"),
        "bi_view_name": cleaned_view_name,
        "form_name": cleaned_view_name,
        "database_table": cleaned_database_table,
        "database_tables": cleaned_database_table,
        "dynamic_table_name": f"{schema_name}.{table_name}",
        "config_status": (
            saved_configuration.get("config_status") or "Draft"
        ),
        "configuration_exists": bool(
            saved_configuration.get("exists")
        ),
        "report_pages": page_results,
        "report_filter_definitions": filter_definitions,
        "selected_report_filters": selected_filters,
        "report_kpi_visuals": all_kpi_visuals,
        "report_columns": table_columns,
        "report_has_pages": bool(page_results),
        "report_filters_applied": bool(execute_visuals),
        "report_matching_row_count": matching_row_count,
    }