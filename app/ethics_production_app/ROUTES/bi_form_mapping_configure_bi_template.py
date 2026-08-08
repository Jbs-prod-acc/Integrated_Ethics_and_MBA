from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ROUTES.bi_form_mapping import BI_FORM_MAPPING


CONFIGURATION_TABLE = "public.bi_dashboard_saved_configurations_dashbooards"
ALLOWED_CONFIG_STATUSES = {
    "draft",
    "active",
    "inactive",
    "archived",
    "not configured",
}


def _normalise_json_object(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    return {}


def _normalise_json_array(value: Any) -> List[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    return []


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalise_visual_type(value: Any) -> str:
    """Normalise visual labels while preserving every supported/new type."""
    cleaned = _clean_text(value).lower().replace("&", "and")
    cleaned = "_".join(part for part in __import__("re").split(r"[^a-z0-9]+", cleaned) if part)

    aliases = {
        "basic_line_chart": "basic_line",
        "smoothed_line_chart": "smoothed_line",
        "basic_area_chart": "basic_area",
        "stacked_line_chart": "stacked_line",
        "stacked_area_chart": "stacked_area",
        "gradient_stacked_area_chart": "gradient_stacked_area",
        "bump_chart_ranking": "bump_chart",
        "temperature_change_in_the_coming_week": "temperature_change",
        "large_scale_area_chart": "large_scale_area",
        "area_chart_with_time_axis": "area_time_axis",
        "dynamic_data_time_axis": "dynamic_time_axis",
        "bar_chart_with_negative_value": "negative_bar",
        "radial_polar_bar_label_position": "radial_polar_bar",
        "tangential_polar_bar_label_position": "tangential_polar_bar",
        "polar_endangle": "polar_end_angle",
        "mixed_line_and_bar": "mixed_line_bar",
        "bar_chart_on_polar": "bar_polar",
        "stacked_bar_chart_on_polar": "stacked_bar_polar",
        "stacked_bar_chart_on_polar_radial": "stacked_bar_polar_radial",
        "rounded_bar_on_polar": "rounded_bar_polar",
        "bar_chart_with_axis_breaks": "bar_axis_breaks",
        "basic_radar_chart": "basic_radar",
        "hide_overlapped_label": "network_graph",
    }
    return aliases.get(cleaned, cleaned)


def _clean_optional_integer(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _make_json_safe(value: Any) -> Any:
    """Convert database values recursively into JSON-safe values."""

    if value is None:
        return None

    if isinstance(value, memoryview):
        return value.tobytes().hex()

    if isinstance(value, bytes):
        return value.hex()

    if isinstance(value, bytearray):
        return bytes(value).hex()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_make_json_safe(item) for item in value]

    return value


def validate_dashboard_pages(
    dashboard_pages: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Validate and normalise all dashboard pages.

    Preserves the complete original visual configuration.

    Canonical fields are validated and normalised, but unknown or
    visual-specific fields are retained. This prevents already-working
    settings such as KPI batches and future visual properties from
    being deleted when dashboard_pages is saved.

    Explicitly supports:

    - tableColumns
    - splitColumn
    - trackingColumns
    - grouped-column category and multiple Y-value fields
    - tableTotalFirstColumn
    - tableTotalSecondColumn
    - tableTotalValueColumn

    Older Split Data Table configurations that do not yet contain a
    splitColumn are allowed through so that the user can open, edit,
    and save them again with the correct split selection.
    """

    if not isinstance(dashboard_pages, dict):
        raise ValueError(
            "Dashboard pages must be supplied as a JSON object."
        )

    if not dashboard_pages:
        raise ValueError(
            "At least one dashboard page is required."
        )

    cleaned_pages: Dict[str, Dict[str, Any]] = {}

    for page_index, page_entry in enumerate(
        dashboard_pages.items(),
        start=1,
    ):
        page_name, page_configuration = page_entry

        cleaned_page_name = _clean_text(
            page_name
        )

        if not cleaned_page_name:
            raise ValueError(
                f"Dashboard page {page_index} has no page name."
            )

        if not isinstance(page_configuration, dict):
            raise ValueError(
                f'The configuration for page '
                f'"{cleaned_page_name}" must be a JSON object.'
            )

        # ========================================================
        # PAGE FILTER COLUMNS
        # ========================================================

        filter_columns = page_configuration.get(
            "filter_columns",
            page_configuration.get(
                "filterColumns",
                [],
            ),
        )

        if not isinstance(filter_columns, list):
            filter_columns = []

        cleaned_filter_columns = []

        for column in filter_columns:
            cleaned_column = _clean_text(
                column
            )

            if (
                cleaned_column
                and cleaned_column not in cleaned_filter_columns
            ):
                cleaned_filter_columns.append(
                    cleaned_column
                )

        # ========================================================
        # PAGE VISUALS
        # ========================================================

        visuals = page_configuration.get(
            "visuals",
            [],
        )

        if not isinstance(visuals, list):
            visuals = []

        cleaned_visuals: List[Dict[str, Any]] = []

        for visual_index, visual in enumerate(
            visuals,
            start=1,
        ):
            if not isinstance(visual, dict):
                continue

            # ====================================================
            # VISUAL TYPE
            # ====================================================

            visual_type = _normalise_visual_type(
                visual.get(
                    "type",
                    visual.get(
                        "visualType",
                        visual.get(
                            "visual_type",
                            visual.get(
                                "chartType",
                                visual.get(
                                    "chart_type",
                                    "",
                                ),
                            ),
                        ),
                    ),
                )
            )

            # ====================================================
            # TABLE COLUMNS
            # ====================================================

            table_columns = visual.get(
                "tableColumns",
                visual.get(
                    "table_columns",
                    visual.get(
                        "columns",
                        visual.get(
                            "selectedColumns",
                            visual.get(
                                "selected_columns",
                                [],
                            ),
                        ),
                    ),
                ),
            )

            if not isinstance(table_columns, list):
                table_columns = []

            cleaned_table_columns: List[str] = []

            for column in table_columns:
                cleaned_column = _clean_text(
                    column
                )

                if (
                    cleaned_column
                    and cleaned_column not in cleaned_table_columns
                ):
                    cleaned_table_columns.append(
                        cleaned_column
                    )

            # ====================================================
            # SPLIT TABLE WITH TRACKING COLUMNS
            # ====================================================

            tracking_columns = visual.get(
                "trackingColumns",
                visual.get(
                    "tracking_columns",
                    visual.get(
                        "trackingFields",
                        visual.get(
                            "tracking_fields",
                            [],
                        ),
                    ),
                ),
            )

            if not isinstance(tracking_columns, list):
                tracking_columns = []

            cleaned_tracking_columns: List[str] = []

            for column in tracking_columns:
                cleaned_column = _clean_text(column)

                if (
                    cleaned_column
                    and cleaned_column
                    not in cleaned_tracking_columns
                ):
                    cleaned_tracking_columns.append(
                        cleaned_column
                    )


            tracking_order = visual.get(
                "trackingOrder",
                visual.get("tracking_order", []),
            )

            if not isinstance(tracking_order, list):
                tracking_order = []

            cleaned_tracking_order: List[str] = []

            for column in tracking_order:
                cleaned_column = _clean_text(column)

                if (
                    cleaned_column
                    and cleaned_column in cleaned_tracking_columns
                    and cleaned_column not in cleaned_tracking_order
                ):
                    cleaned_tracking_order.append(cleaned_column)

            for column in cleaned_tracking_columns:
                if column not in cleaned_tracking_order:
                    cleaned_tracking_order.append(column)

            if (
                visual_type == "split_table_tracking_distinct_graphics"
                and len(cleaned_tracking_order) < 2
            ):
                raise ValueError(
                    f'Split Table with Tracking Distinct and Graphics "'
                    f'{_clean_text(visual.get("title"))}" '
                    "requires at least two ordered Tracking Columns."
                )

            # ====================================================
            # GROUPED COLUMN MULTIPLE Y-VALUES
            # ====================================================

            grouped_y_values = visual.get(
                "yValues",
                visual.get(
                    "y_values",
                    [],
                ),
            )

            if not isinstance(grouped_y_values, list):
                grouped_y_values = []

            cleaned_grouped_y_values: List[str] = []

            for column in grouped_y_values:
                cleaned_column = _clean_text(column)

                if (
                    cleaned_column
                    and cleaned_column
                    not in cleaned_grouped_y_values
                ):
                    cleaned_grouped_y_values.append(
                        cleaned_column
                    )

            # Backward compatibility for older Grouped Column Chart
            # configurations that stored only one value column.
            if (
                visual_type == "grouped_column"
                and not cleaned_grouped_y_values
            ):
                old_grouped_value = _clean_text(
                    visual.get(
                        "value",
                        visual.get(
                            "yAxis",
                            visual.get(
                                "y_axis",
                                "",
                            ),
                        ),
                    )
                )

                if old_grouped_value:
                    cleaned_grouped_y_values.append(
                        old_grouped_value
                    )

            # ====================================================
            # SPLIT COLUMN
            # ====================================================

            split_column = _clean_text(
                visual.get(
                    "splitColumn",
                    visual.get(
                        "split_column",
                        visual.get(
                            "splitBy",
                            visual.get(
                                "split_by",
                                visual.get(
                                    "splitField",
                                    visual.get(
                                        "split_field",
                                        visual.get(
                                            "splitOn",
                                            visual.get(
                                                "split_on",
                                                visual.get(
                                                    "groupBy",
                                                    visual.get(
                                                        "group_by",
                                                        visual.get(
                                                            "partitionColumn",
                                                            visual.get(
                                                                "partition_column",
                                                                "",
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            )

            # Do not raise an exception when splitColumn is empty.
            #
            # Older saved configurations may not contain splitColumn
            # because the previous validation function removed it.
            # They must be allowed to load and save so the user can
            # edit the affected visual and select the correct field.
            if visual_type in {
                "split_table",
                "split_data_table",
                "splittable",
                "splitdatatable",
                "split_table_tracking",
                "split_table_with_tracking",
                "split_table_tracking_distinct",
                "split_table_tracking_distinct_graphics",
                "split_table_with_tracking_distinct",
                "split_table_with_tracking_distinct_graphics",
            }:
                split_column = split_column or ""

            if visual_type in {
                "split_table_tracking",
                "split_table_with_tracking",
                "split_table_tracking_distinct",
                "split_table_tracking_distinct_graphics",
                "split_table_with_tracking_distinct",
                "split_table_with_tracking_distinct_graphics",
            } and not cleaned_tracking_columns:
                raise ValueError(
                    f'Split Table with Tracking "'
                    f'{_clean_text(visual.get("title"))}" '
                    "requires at least one Tracking Column."
                )

            # ====================================================
            # DISTINCT BASED ON COLUMN
            # ====================================================

            distinct_based_on = _clean_text(
                visual.get(
                    "distinctBasedOn",
                    visual.get(
                        "distinct_based_on",
                        visual.get(
                            "distinctColumn",
                            visual.get("distinct_column", ""),
                        ),
                    ),
                )
            )

            if visual_type in {
                "split_table_tracking_distinct",
                "split_table_tracking_distinct_graphics",
                "split_table_with_tracking_distinct",
                "split_table_with_tracking_distinct_graphics",
            }:
                if not distinct_based_on:
                    raise ValueError(
                        f'Split Table with Tracking Distinct "'
                        f'{_clean_text(visual.get("title"))}" '
                        "requires a Distinct Based on column."
                    )

                if distinct_based_on not in cleaned_table_columns:
                    raise ValueError(
                        f'The Distinct Based on column "{distinct_based_on}" '
                        "must also be selected under Table Columns."
                    )
            else:
                distinct_based_on = ""

            # ====================================================
            # TABLE TOTAL COLUMNS
            # ====================================================
            #
            # These values must be preserved in dashboard_pages.
            # The report execution backend reads them later when it
            # builds the cross-tab / pivot-style Table Total.
            #
            # Several aliases are accepted so older templates and
            # future snake_case payloads remain compatible.

            table_total_first_column = _clean_text(
                visual.get(
                    "tableTotalFirstColumn",
                    visual.get(
                        "table_total_first_column",
                        visual.get(
                            "firstColumn",
                            visual.get(
                                "first_column",
                                visual.get(
                                    "rowColumn",
                                    visual.get(
                                        "row_column",
                                        visual.get(
                                            "rowField",
                                            visual.get(
                                                "row_field",
                                                "",
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            )

            table_total_second_column = _clean_text(
                visual.get(
                    "tableTotalSecondColumn",
                    visual.get(
                        "table_total_second_column",
                        visual.get(
                            "secondColumn",
                            visual.get(
                                "second_column",
                                visual.get(
                                    "headerColumn",
                                    visual.get(
                                        "header_column",
                                        visual.get(
                                            "columnHeaderField",
                                            visual.get(
                                                "column_header_field",
                                                visual.get(
                                                    "columnField",
                                                    visual.get(
                                                        "column_field",
                                                        "",
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            )

            table_total_value_column = _clean_text(
                visual.get(
                    "tableTotalValueColumn",
                    visual.get(
                        "table_total_value_column",
                        visual.get(
                            "totalValueColumn",
                            visual.get(
                                "total_value_column",
                                visual.get(
                                    "measureColumn",
                                    visual.get(
                                        "measure_column",
                                        visual.get(
                                            "valueColumn",
                                            visual.get(
                                                "value_column",
                                                "",
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            )

            # For a Table Total, retain the canonical generic fields too.
            # This is useful for report code that falls back to category,
            # legend and value when reading older configurations.
            if visual_type in {
                "table_total",
                "tabletotal",
                "total_table",
                "pivot_table",
                "pivot",
            }:
                table_total_first_column = (
                    table_total_first_column
                    or _clean_text(
                        visual.get(
                            "category",
                            visual.get(
                                "xAxis",
                                visual.get("x_axis", ""),
                            ),
                        )
                    )
                )

                table_total_second_column = (
                    table_total_second_column
                    or _clean_text(
                        visual.get(
                            "legend",
                            visual.get(
                                "groupColumn",
                                visual.get("group_column", ""),
                            ),
                        )
                    )
                )

                table_total_value_column = (
                    table_total_value_column
                    or _clean_text(
                        visual.get(
                            "value",
                            visual.get(
                                "yAxis",
                                visual.get("y_axis", ""),
                            ),
                        )
                    )
                )

            # ====================================================
            # GROUPED COLUMN VALIDATION
            # ====================================================

            grouped_category = _clean_text(
                visual.get(
                    "category",
                    visual.get(
                        "xAxis",
                        visual.get(
                            "x_axis",
                            "",
                        ),
                    ),
                )
            )

            if visual_type == "grouped_column":
                if not grouped_category:
                    raise ValueError(
                        f'Grouped Column Chart "{_clean_text(visual.get("title"))}" '
                        "requires a Category / X-Axis column."
                    )

                if not cleaned_grouped_y_values:
                    raise ValueError(
                        f'Grouped Column Chart "{_clean_text(visual.get("title"))}" '
                        "requires at least one Y-Value column."
                    )

            # ====================================================
            # CLEANED VISUAL
            # ====================================================

            # ====================================================
            # NON-DESTRUCTIVE VISUAL PRESERVATION
            # ====================================================
            #
            # Start with the complete original visual configuration.
            # Do not rebuild it from a small whitelist because that
            # removes existing fields used by KPI batches and other
            # already-working visual types.
            cleaned_visual = {
                str(key): _make_json_safe(value)
                for key, value in visual.items()
            }

            cleaned_visual.update({
                "id": (
                    _clean_text(
                        visual.get("id")
                    )
                    or (
                        f"visual_"
                        f"{page_index}_"
                        f"{visual_index}"
                    )
                ),

                "title": _clean_text(
                    visual.get("title")
                ),

                "type": visual_type,

                "category": grouped_category,

                "value": (
                    cleaned_grouped_y_values[0]
                    if (
                        visual_type == "grouped_column"
                        and cleaned_grouped_y_values
                    )
                    else _clean_text(
                        visual.get(
                            "value",
                            visual.get(
                                "yAxis",
                                visual.get(
                                    "y_axis",
                                    "",
                                ),
                            ),
                        )
                    )
                ),

                # Multiple Y-value columns used only by the
                # Grouped Column Chart. Other visual types retain
                # an empty list and are otherwise unchanged.
                "yValues": (
                    cleaned_grouped_y_values
                    if visual_type == "grouped_column"
                    else []
                ),

                "aggregation": _clean_text(
                    visual.get(
                        "aggregation",
                        visual.get(
                            "aggregate",
                            visual.get(
                                "aggregationType",
                                visual.get(
                                    "aggregation_type",
                                    "",
                                ),
                            ),
                        ),
                    )
                ),

                "legend": (
                    ""
                    if visual_type == "grouped_column"
                    else _clean_text(
                        visual.get(
                            "legend",
                            visual.get(
                                "groupColumn",
                                visual.get(
                                    "group_column",
                                    visual.get(
                                        "seriesColumn",
                                        visual.get(
                                            "series_column",
                                            visual.get(
                                                "groupSeriesColumn",
                                                visual.get(
                                                    "group_series_column",
                                                    "",
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        )
                    )
                ),

                "target": visual.get(
                    "target",
                    "",
                ),

                "note": _clean_text(
                    visual.get("note")
                ),

                # Preserve tracking fields separately from the
                # ordinary Split Table display columns.
                "trackingOrder": (
                    cleaned_tracking_order
                    if visual_type == "split_table_tracking_distinct_graphics"
                    else []
                ),
                "tracking_order": (
                    cleaned_tracking_order
                    if visual_type == "split_table_tracking_distinct_graphics"
                    else []
                ),

                # This visual deliberately uses the selected distinct
                # column on the vertical categorical axis and the ordered
                # tracking columns on the horizontal axis.
                "trackingAxisMode": (
                    "distinct_y_tracking_x"
                    if visual_type == "split_table_tracking_distinct_graphics"
                    else ""
                ),
                "tracking_axis_mode": (
                    "distinct_y_tracking_x"
                    if visual_type == "split_table_tracking_distinct_graphics"
                    else ""
                ),

                "trackingColumns": (
                    cleaned_tracking_columns
                    if visual_type in {
                        "split_table_tracking",
                        "split_table_with_tracking",
                        "split_table_tracking_distinct",
                "split_table_tracking_distinct_graphics",
                        "split_table_with_tracking_distinct",
                "split_table_with_tracking_distinct_graphics",
                    }
                    else []
                ),

                # Preserve the selected Data Table columns.
                "tableColumns": cleaned_table_columns,

                # Preserve the Split Data Table field during save.
                "splitColumn": split_column,

                # Preserve the de-duplication key for
                # Split Table with Tracking Distinct.
                "distinctBasedOn": distinct_based_on,

                # Preserve all Table Total selections during save.
                # These are the exact canonical keys used by the
                # builder template and the report execution backend.
                "tableTotalFirstColumn":
                    table_total_first_column,

                "tableTotalSecondColumn":
                    table_total_second_column,

                "tableTotalValueColumn":
                    table_total_value_column,
            })

            cleaned_visuals.append(
                cleaned_visual
            )

        # ========================================================
        # CLEANED PAGE
        # ========================================================

        cleaned_pages[cleaned_page_name] = {
            "id": (
                _clean_text(
                    page_configuration.get("id")
                )
                or f"page_{page_index}"
            ),

            "page_order": (
                _clean_optional_integer(
                    page_configuration.get(
                        "page_order",
                        page_configuration.get(
                            "pageOrder",
                            page_index,
                        ),
                    )
                )
                or page_index
            ),

            "description": _clean_text(
                page_configuration.get(
                    "description"
                )
            ),

            "filter_columns": cleaned_filter_columns,

            "visuals": cleaned_visuals,
        }

    return cleaned_pages


def _mapping_records() -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []

    for item in BI_FORM_MAPPING:
        if not isinstance(item, dict):
            continue

        bi_view_name = _clean_text(item.get("bi_view_name"))
        database_table = _clean_text(item.get("database_table"))

        if bi_view_name and database_table:
            records.append(
                {
                    "bi_view_name": bi_view_name,
                    "database_table": database_table,
                }
            )

    return records


def resolve_bi_mapping(
    *,
    bi_view_name: str,
    database_table: str,
) -> Optional[Dict[str, str]]:
    cleaned_view = _clean_text(bi_view_name)
    cleaned_table = _clean_text(database_table)

    for item in _mapping_records():
        same_view = item["bi_view_name"].lower() == cleaned_view.lower()
        same_table = item["database_table"].lower() == cleaned_table.lower()

        if same_view and same_table:
            return item

    return None


def _split_table_name(database_table: str) -> tuple[str, str]:
    cleaned = _clean_text(database_table)

    if "." in cleaned:
        schema_name, table_name = cleaned.split(".", 1)
    else:
        schema_name, table_name = "public", cleaned

    return schema_name.strip(), table_name.strip()


def fetch_database_table_columns(
    db_session,
    *,
    database_table: str,
) -> List[str]:
    schema_name, table_name = _split_table_name(database_table)
    columns = db_session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            ORDER BY ordinal_position
            """
        ),
        {
            "schema_name": schema_name,
            "table_name": table_name,
        },
    ).scalars().all()

    return [str(column_name) for column_name in columns if column_name]


def fetch_database_table_preview_rows(
    db_session,
    *,
    database_table: str,
    limit: int = 250,
) -> List[Dict[str, Any]]:
    schema_name, table_name = _split_table_name(database_table)
    engine = db_session.get_bind()
    preparer = engine.dialect.identifier_preparer

    quoted_schema = preparer.quote_schema(schema_name)
    quoted_table = preparer.quote(table_name)

    safe_limit = max(1, min(int(limit or 250), 1000))

    statement = text(
        f"""
        SELECT *
        FROM {quoted_schema}.{quoted_table}
        LIMIT :limit
        """
    )

    rows = db_session.execute(
        statement,
        {"limit": safe_limit},
    ).mappings().all()

    output: List[Dict[str, Any]] = []

    for row in rows:
        output.append(
            {
                str(key): _make_json_safe(value)
                for key, value in dict(row).items()
            }
        )

    return output


def fetch_saved_bi_configuration(
    db_session,
    *,
    bi_view_name: str,
    database_table: str,
) -> Dict[str, Any]:
    rows = db_session.execute(
        text(
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
            FROM {CONFIGURATION_TABLE}
            WHERE LOWER(BTRIM(bi_view_name)) =
                  LOWER(BTRIM(:bi_view_name))
              AND LOWER(BTRIM(database_tables)) =
                  LOWER(BTRIM(:database_table))
            LIMIT 1
            """
        ),
        {
            "bi_view_name": _clean_text(bi_view_name),
            "database_table": _clean_text(database_table),
        },
    ).mappings().all()

    row = rows[0] if rows else None

    if not row:
        return {
            "success": True,
            "exists": False,
            "bi_view_id": None,
            "bi_view_name": _clean_text(bi_view_name),
            "database_tables": _clean_text(database_table),
            "config_status": "Draft",
            "dashboard_pages": {},
        }

    result = dict(row)
    result["success"] = True
    result["exists"] = True
    result["dashboard_pages"] = _normalise_json_object(
        result.get("dashboard_pages")
    )

    return result

import json
def save_bi_configuration(
    db_session,
    *,
    bi_view_name: str,
    database_table: str,
    dashboard_pages: Dict[str, Any],
    configured_by: str,
    config_status: str = "Draft",
) -> Dict[str, Any]:
    mapping = resolve_bi_mapping(
        bi_view_name=bi_view_name,
        database_table=database_table,
    )

    if not mapping:
        return {
            "success": False,
            "message": (
                "The selected BI view and database table do not match "
                "an item in BI_FORM_MAPPING."
            ),
        }

    cleaned_status = _clean_text(config_status) or "Draft"

    if cleaned_status.lower() not in ALLOWED_CONFIG_STATUSES:
        return {
            "success": False,
            "message": "The supplied configuration status is invalid.",
        }

    cleaned_pages = validate_dashboard_pages(
        dashboard_pages
    )

    cleaned_user = _clean_text(
        configured_by
    )

    try:
        row = db_session.execute(
            text(
                f"""
                INSERT INTO {CONFIGURATION_TABLE}
                (
                    bi_view_name,
                    database_tables,
                    config_status,
                    dashboard_pages,
                    created_by,
                    created_at,
                    updated_by,
                    updated_at
                )
                VALUES
                (
                    :bi_view_name,
                    :database_table,
                    :config_status,
                    CAST(:dashboard_pages AS jsonb),
                    :configured_by,
                    CURRENT_TIMESTAMP,
                    NULL,
                    NULL
                )
                ON CONFLICT (bi_view_name)
                DO UPDATE SET
                    database_tables = EXCLUDED.database_tables,
                    config_status = EXCLUDED.config_status,
                    dashboard_pages = EXCLUDED.dashboard_pages,
                    updated_by = EXCLUDED.created_by,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING
                    bi_view_id,
                    bi_view_name,
                    database_tables,
                    config_status,
                    dashboard_pages,
                    created_by,
                    created_at,
                    updated_by,
                    updated_at
                """
            ),
            {
                "bi_view_name": mapping["bi_view_name"],
                "database_table": mapping["database_table"],
                "config_status": cleaned_status,
                "dashboard_pages": json.dumps(
                    cleaned_pages,
                    default=str,
                ),
                "configured_by": cleaned_user or None,
            },
        ).mappings().first()

        db_session.commit()

    except Exception:
        db_session.rollback()
        raise

    # Convert all returned PostgreSQL values to JSON-safe values.
    # This prevents Flask jsonify from failing after the database
    # configuration has already been saved.
    result = _make_json_safe(
        dict(row or {})
    )

    result["dashboard_pages"] = (
        _normalise_json_object(
            result.get("dashboard_pages")
        )
    )

    return _make_json_safe({
        "success": True,
        "message": (
            "BI dashboard configuration "
            "saved successfully."
        ),
        **result,
    })


def delete_bi_configuration_page(
    db_session,
    *,
    bi_view_name: str,
    database_table: str,
    page_name: str,
    configured_by: str,
) -> Dict[str, Any]:
    existing = fetch_saved_bi_configuration(
        db_session,
        bi_view_name=bi_view_name,
        database_table=database_table,
    )

    if not existing.get("exists"):
        return {
            "success": False,
            "message": "No saved BI configuration was found.",
        }

    cleaned_page_name = _clean_text(page_name)
    pages = existing.get("dashboard_pages") or {}

    if cleaned_page_name not in pages:
        return {
            "success": False,
            "message": f'Dashboard page "{cleaned_page_name}" was not found.',
        }

    pages.pop(cleaned_page_name, None)

    if not pages:
        return {
            "success": False,
            "message": (
                "The last page cannot be deleted from the saved "
                "configuration. Add another page first."
            ),
        }

    return save_bi_configuration(
        db_session,
        bi_view_name=bi_view_name,
        database_table=database_table,
        dashboard_pages=pages,
        configured_by=configured_by,
        config_status=existing.get("config_status") or "Draft",
    )


def build_configure_bi_template_context(
    db_session,
    *,
    bi_view_name: str,
    database_table: str,
    preview_limit: int = 250,
) -> Dict[str, Any]:
    mapping = resolve_bi_mapping(
        bi_view_name=bi_view_name,
        database_table=database_table,
    )

    if not mapping:
        raise ValueError(
            "The selected BI view and database table are not mapped."
        )

    columns = fetch_database_table_columns(
        db_session,
        database_table=mapping["database_table"],
    )

    rows = fetch_database_table_preview_rows(
        db_session,
        database_table=mapping["database_table"],
        limit=preview_limit,
    )

    saved = fetch_saved_bi_configuration(
        db_session,
        bi_view_name=mapping["bi_view_name"],
        database_table=mapping["database_table"],
    )

    safe_columns = _make_json_safe(columns)
    safe_rows = _make_json_safe(rows)
    safe_saved_pages = _make_json_safe(
        saved.get("dashboard_pages") or {}
    )

    return {
        "bi_view_name": str(mapping["bi_view_name"]),
        "database_table": str(mapping["database_table"]),
        "columns": safe_columns,
        "data_rows": safe_rows,
        "page_columns": safe_columns,
        "page_rows": safe_rows,
        "saved_dashboard_pages": safe_saved_pages,
        "config_status": str(saved.get("config_status") or "Draft"),
        "bi_view_id": _make_json_safe(saved.get("bi_view_id")),
        "configuration_exists": bool(saved.get("exists")),
    }
