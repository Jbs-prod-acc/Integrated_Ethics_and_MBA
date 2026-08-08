from math import ceil


# =============================================================================
# BI FORM MAPPING
# =============================================================================
# Add every BI report here.
#
# bi_view_name:
#     The name displayed in the frontend table.
#
# database_table:
#     The PostgreSQL table that will eventually provide the report data.
#
# status:
#     The current configuration status displayed in the table.
#
# Any new dictionary added here will automatically appear in:
# - The configured BI views table
# - The BI view filter
# - The database table filter
# - The status filter
# - Pagination totals
# =============================================================================

BI_FORM_MAPPING = [

    # 1
    {
        "bi_view_name": "Ethics Activity Logs",
        "database_table": "ethcis_activity_logs",
        "status": "Active",
    },
    # 2
    {
        "bi_view_name": "Ethics Application",
        "database_table": "ethcis_applications",
        "status": "Active",
    },
    # 3
    {
        "bi_view_name": "Ethics Draft Form",
        "database_table": "ethcis_form_drafts",
        "status": "Active",
    },





    # 4

     {
        "bi_view_name": "Ethics Form Requirements",
        "database_table": "ethcis_form_requirements",
        "status": "Draft",
    },

    # 5
     {
        "bi_view_name": "Ethics Form Submissions",
        "database_table": "ethcis_form_submissions",
        "status": "Draft",
    },

    # 6
     {
        "bi_view_name": "Ethics Reviewer Assignments",
        "database_table": "ethcis_reviewer_assignments",
        "status": "Draft",
    },

    # 7
     {
        "bi_view_name": "Ethics Reviewers",
        "database_table": "ethcis_reviews",
        "status": "Draft",
    },

    # 8
     {
        "bi_view_name": "Ethics User Legacy",
        "database_table": "ethcis_users_legacy",
        "status": "Draft",
    },

    # 9
     {
        "bi_view_name": "Form A",
        "database_table": "form_a",
        "status": "Draft",
    },

    # 10
     {
        "bi_view_name": "Form A Archive",
        "database_table": "form_a_archive",
        "status": "Draft",
    },

    # # 11
     {
        "bi_view_name": "Form A Requirements",
        "database_table": "form_a_requirements",
        "status": "Draft",
    },

    # # 12
     {
        "bi_view_name": "Form B",
        "database_table": "form_b",
        "status": "Draft",
    },

    # # 13
     {
        "bi_view_name": "Form B Archieve",
        "database_table": "form_b_archive",
        "status": "Draft",
    },

    # # 14
     {
        "bi_view_name": "Form C",
        "database_table": "form_c",
        "status": "Draft",
    },

    # # 15
     {
        "bi_view_name": "Form C Archives",
        "database_table": "form_c_archive",
        "status": "Draft",
    },

    # # 16
     {
        "bi_view_name": "Form D",
        "database_table": "form_d",
        "status": "Draft",
    },

    # # 17
     {
        "bi_view_name": "Form Uploads",
        "database_table": "form_uploads",
        "status": "Draft",
    },

    # # 18
     {
        "bi_view_name": "Login Logs",
        "database_table": "login_logs",
        "status": "Draft",
    },

    # # 19
     {
        "bi_view_name": "MBA Desciplines",
        "database_table": "mba_disciplines",
        "status": "Draft",
    },

    # # 20
     {
        "bi_view_name": "MBA Forms",
        "database_table": "mba_forms",
        "status": "Draft",
    },











    # # 21
     {
        "bi_view_name": "MBA Project Documents",
        "database_table": "mba_project_documents",
        "status": "Draft",
    },

    # # 22
     {
        "bi_view_name": "MBA Project Supervisor Invitations",
        "database_table": "mba_project_supervisor_invitations",
        "status": "Draft",
    },

    # # 23
     {
        "bi_view_name": "MBA Projects",
        "database_table": "mba_projects",
        "status": "Draft",
    },

    # # 24
     {
        "bi_view_name": "MBA Reminder States",
        "database_table": "mba_reminder_states",
        "status": "Draft",
    },

    # # 25
     {
        "bi_view_name": "MBA Research Interests",
        "database_table": "mba_research_interests",
        "status": "Draft",
    },

    # # 26
     {
        "bi_view_name": "MBA Scholar Profiles",
        "database_table": "mba_scholar_profiles",
        "status": "Draft",
    },

    # # 27
     {
        "bi_view_name": "MBA Student Profiles",
        "database_table": "mba_student_profiles",
        "status": "Draft",
    },

    # # 28
     {
        "bi_view_name": "MBA User Signatures",
        "database_table": "mba_user_signatures",
        "status": "Draft",
    },

    # # 29
     {
        "bi_view_name": "MBA User Legacy",
        "database_table": "mba_users_legacy",
        "status": "Draft",
    },

    # # 30
     {
        "bi_view_name": "Recs",
        "database_table": "rec",
        "status": "Draft",
    },

    # # 31
     {
        "bi_view_name": "User Activity Logs",
        "database_table": "user_activity_logs",
        "status": "Draft",
    },

    # # 32
     {
        "bi_view_name": "User Information",
        "database_table": "user_information",
        "status": "Draft",
    },

    # # 33
     {
        "bi_view_name": "Users",
        "database_table": "users",
        "status": "Draft",
    },

    # # 34
     {
        "bi_view_name": "MBA Forms",
        "database_table": "mba_forms",
        "status": "Draft",
    },

    # 35

    # 36



]


def normalise_bi_form_mapping():
    """
    Return a clean and consistent list from BI_FORM_MAPPING.
    """

    cleaned_records = []

    for position, mapping_record in enumerate(BI_FORM_MAPPING, start=1):
        if not isinstance(mapping_record, dict):
            continue

        bi_view_name = str(
            mapping_record.get("bi_view_name") or ""
        ).strip()

        database_table = str(
            mapping_record.get("database_table") or ""
        ).strip()

        status = str(
            mapping_record.get("status") or "Active"
        ).strip()

        if not bi_view_name or not database_table:
            continue

        cleaned_records.append(
            {
                "mapping_id": position,
                "bi_view_name": bi_view_name,
                "database_table": database_table,
                "bi_column": str(
                    mapping_record.get("bi_column")
                    or database_table
                ).strip(),
                "status": status,
            }
        )

    return cleaned_records


def get_bi_filter_options():
    """
    Build all frontend filter dropdown values from BI_FORM_MAPPING.
    """

    records = normalise_bi_form_mapping()

    bi_view_names = sorted(
        {
            record["bi_view_name"]
            for record in records
            if record.get("bi_view_name")
        },
        key=str.lower,
    )

    database_tables = sorted(
        {
            record["database_table"]
            for record in records
            if record.get("database_table")
        },
        key=str.lower,
    )

    statuses = sorted(
        {
            record["status"]
            for record in records
            if record.get("status")
        },
        key=str.lower,
    )

    return {
        "bi_view_names": bi_view_names,
        "database_tables": database_tables,
        "statuses": statuses,
    }


def filter_bi_forms(
    records,
    search_text="",
    selected_view="",
    selected_table="",
    selected_status="",
):
    """
    Filter the BI mapping records.
    """

    search_text = str(search_text or "").strip().lower()
    selected_view = str(selected_view or "").strip().lower()
    selected_table = str(selected_table or "").strip().lower()
    selected_status = str(selected_status or "").strip().lower()

    filtered_records = []

    for record in records:
        bi_view_name = str(
            record.get("bi_view_name") or ""
        ).strip()

        database_table = str(
            record.get("database_table") or ""
        ).strip()

        bi_column = str(
            record.get("bi_column") or ""
        ).strip()

        status = str(
            record.get("status") or ""
        ).strip()

        searchable_text = " ".join(
            [
                bi_view_name,
                database_table,
                bi_column,
                status,
            ]
        ).lower()

        matches_search = (
            not search_text
            or search_text in searchable_text
        )

        matches_view = (
            not selected_view
            or bi_view_name.lower() == selected_view
        )

        matches_table = (
            not selected_table
            or database_table.lower() == selected_table
        )

        matches_status = (
            not selected_status
            or status.lower() == selected_status
        )

        if (
            matches_search
            and matches_view
            and matches_table
            and matches_status
        ):
            filtered_records.append(record)

    return filtered_records


def build_page_links(
    current_page,
    total_pages,
    window=10,
    tail=3,
):
    """
    Build pagination links.

    Example:
    [1, 2, 3, 4, None, 18, 19, 20]

    None represents an ellipsis.
    """

    if total_pages <= 1:
        return [1]

    if total_pages <= window + tail:
        return list(range(1, total_pages + 1))

    half_window = window // 2

    start_page = max(
        1,
        current_page - half_window,
    )

    end_page = start_page + window - 1

    if end_page > total_pages:
        end_page = total_pages

        start_page = max(
            1,
            end_page - window + 1,
        )

    tail_start = max(
        1,
        total_pages - tail + 1,
    )

    pages = []

    if start_page > 1:
        pages.append(1)

        if start_page > 2:
            pages.append(None)

    pages.extend(
        range(
            start_page,
            end_page + 1,
        )
    )

    if end_page < tail_start - 1:
        pages.append(None)

    if tail_start > end_page:
        pages.extend(
            range(
                tail_start,
                total_pages + 1,
            )
        )

    output = []
    seen_pages = set()

    for page_number in pages:
        if page_number is None:
            if output and output[-1] is not None:
                output.append(None)

            continue

        if page_number in seen_pages:
            continue

        output.append(page_number)
        seen_pages.add(page_number)

    return output


def paginated_processes(
    processes,
    page=1,
    per_page=10,
):
    """
    Paginate a normal Python list.

    Returns:
    - paginated_records
    - total_pages
    - current_page
    - total_records
    - showing_from
    - showing_to
    - page_links
    """

    processes = list(processes or [])

    try:
        page = int(page or 1)
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = int(per_page or 10)
    except (TypeError, ValueError):
        per_page = 10

    if page < 1:
        page = 1

    if per_page not in {10, 25, 50, 100}:
        per_page = 10

    total_records = len(processes)

    if total_records == 0:
        return (
            [],
            1,
            1,
            0,
            0,
            0,
            [1],
        )

    total_pages = ceil(
        total_records / per_page
    )

    current_page = max(
        1,
        min(page, total_pages),
    )

    start_index = (
        current_page - 1
    ) * per_page

    end_index = min(
        start_index + per_page,
        total_records,
    )

    paginated_records = processes[
        start_index:end_index
    ]

    showing_from = start_index + 1
    showing_to = end_index

    page_links = build_page_links(
        current_page=current_page,
        total_pages=total_pages,
        window=10,
        tail=3,
    )

    return (
        paginated_records,
        total_pages,
        current_page,
        total_records,
        showing_from,
        showing_to,
        page_links,
    )


def get_bi_landing_page_context(
    page=1,
    per_page=10,
    search_text="",
    selected_view="",
    selected_table="",
    selected_status="",
):
    """
    Build the complete template context required by
    power_bi_landing_home.html.
    """

    try:
        page = int(page or 1)
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = int(per_page or 10)
    except (TypeError, ValueError):
        per_page = 10

    if page < 1:
        page = 1

    if per_page not in {10, 25, 50, 100}:
        per_page = 10

    search_text = str(
        search_text or ""
    ).strip()

    selected_view = str(
        selected_view or ""
    ).strip()

    selected_table = str(
        selected_table or ""
    ).strip()

    selected_status = str(
        selected_status or ""
    ).strip()

    all_records = normalise_bi_form_mapping()

    filtered_records = filter_bi_forms(
        records=all_records,
        search_text=search_text,
        selected_view=selected_view,
        selected_table=selected_table,
        selected_status=selected_status,
    )

    (
        paginated_records,
        total_pages,
        current_page,
        total_records,
        showing_from,
        showing_to,
        page_links,
    ) = paginated_processes(
        processes=filtered_records,
        page=page,
        per_page=per_page,
    )

    filter_options = get_bi_filter_options()

    return {
        "bi_records": paginated_records,

        "current_page": current_page,
        "total_pages": total_pages,
        "total_records": total_records,
        "showing_from": showing_from,
        "showing_to": showing_to,
        "page_links": page_links,
        "per_page": per_page,

        "search_text": search_text,
        "selected_view": selected_view,
        "selected_table": selected_table,
        "selected_status": selected_status,

        "bi_view_names": filter_options.get(
            "bi_view_names",
            [],
        ),
        "database_tables": filter_options.get(
            "database_tables",
            [],
        ),
        "statuses": filter_options.get(
            "statuses",
            [],
        ),
    }



# RIghts configurations
from sqlalchemy import bindparam, text


# =============================================================================
# BI CONFIGURATION AND VIEWING RIGHTS
# =============================================================================

BI_CONFIGURATION_RIGHTS_EXCLUDED_ROLES = {
    "STUDENT": True,
}


def ensure_bi_configuration_rights_table(db_session):
    """Create the BI rights table when deploying the feature to an older DB."""
    try:
        db_session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.users_bi_config_rights
                (
                    id BIGSERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL UNIQUE,
                    full_name VARCHAR(255),
                    email VARCHAR(255),
                    role VARCHAR(100),
                    has_bi_config_rights VARCHAR(3) NOT NULL DEFAULT 'No',
                    has_bi_view_rights VARCHAR(3) NOT NULL DEFAULT 'No',
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_by VARCHAR(255),
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT users_bi_config_rights_config_check
                        CHECK (has_bi_config_rights IN ('Yes', 'No')),
                    CONSTRAINT users_bi_config_rights_view_check
                        CHECK (has_bi_view_rights IN ('Yes', 'No'))
                )
                """
            )
        )
        db_session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.bi_dashboard_saved_configurations_dashbooards
                (
                    bi_view_id BIGSERIAL PRIMARY KEY,
                    bi_view_name VARCHAR(255) NOT NULL UNIQUE,
                    database_tables VARCHAR(255) NOT NULL,
                    config_status VARCHAR(50) NOT NULL DEFAULT 'Draft',
                    dashboard_pages JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_by VARCHAR(255),
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_by VARCHAR(255),
                    updated_at TIMESTAMP WITHOUT TIME ZONE,
                    CONSTRAINT bi_dashboard_saved_config_status_check CHECK
                    (
                        LOWER(config_status) IN
                        ('draft', 'active', 'inactive', 'archived', 'not configured')
                    )
                )
                """
            )
        )
        db_session.commit()
        return True
    except Exception as error:
        db_session.rollback()
        print("ensure_bi_configuration_rights_table error:", error)
        return False


def normalise_bi_configuration_rights_users(
    db_session,
):
    """
    Fetch all active eligible users directly from public.users.

    public.users_bi_config_rights contains one global rights row
    per user.

    Users without a rights record are returned with:
    - has_bi_config_rights = No
    - has_bi_view_rights = No
    """

    excluded_role_values = [
        str(role_name or "").strip().upper()
        for role_name, should_exclude
        in BI_CONFIGURATION_RIGHTS_EXCLUDED_ROLES.items()
        if should_exclude
        and str(role_name or "").strip()
    ]

    sql_statement = text(
        """
        SELECT
            u.user_id,
            u.full_name,
            u.email,
            u.role::text AS role,

            COALESCE(
                r.has_bi_config_rights,
                'No'
            ) AS has_bi_config_rights,

            COALESCE(
                r.has_bi_view_rights,
                'No'
            ) AS has_bi_view_rights

        FROM public.users AS u

        LEFT JOIN public.users_bi_config_rights AS r
          ON r.user_id = u.user_id

        WHERE u.is_active = TRUE

          AND (
                :exclude_roles = FALSE
                OR UPPER(u.role::text)
                   NOT IN :excluded_roles
              )

        ORDER BY
            u.full_name ASC,
            u.email ASC
        """
    ).bindparams(
        bindparam(
            "excluded_roles",
            expanding=True,
        )
    )

    try:
        records = db_session.execute(
            sql_statement,
            {
                "exclude_roles": bool(
                    excluded_role_values
                ),
                "excluded_roles": (
                    excluded_role_values
                    if excluded_role_values
                    else [""]
                ),
            },
        ).mappings().all()

        normalised_users = []

        for record in records:
            normalised_users.append(
                {
                    "user_id": str(
                        record.get("user_id") or ""
                    ).strip(),

                    "full_name": str(
                        record.get("full_name") or ""
                    ).strip(),

                    "email": str(
                        record.get("email") or ""
                    ).strip(),

                    "role": str(
                        record.get("role") or ""
                    ).strip(),

                    "has_bi_config_rights": str(
                        record.get(
                            "has_bi_config_rights"
                        )
                        or "No"
                    ).strip(),

                    "has_bi_view_rights": str(
                        record.get(
                            "has_bi_view_rights"
                        )
                        or "No"
                    ).strip(),
                }
            )

        return normalised_users

    except Exception as error:
        db_session.rollback()

        print(
            "normalise_bi_configuration_rights_users error:",
            error,
        )

        return []


# =============================================================================
# FILTER BI CONFIGURATION RIGHTS USERS
# =============================================================================

def filter_bi_configuration_rights_users(
    users,
    search_text="",
):
    """
    Filter the complete eligible-user list before pagination.

    Search fields:
    - Full name
    - Email
    - Role
    - Configuration rights
    - Viewing rights
    """

    search_text = str(
        search_text or ""
    ).strip().lower()

    if not search_text:
        return list(
            users or []
        )

    filtered_users = []

    for user in list(
        users or []
    ):
        full_name = str(
            user.get("full_name") or ""
        ).strip()

        email = str(
            user.get("email") or ""
        ).strip()

        role = str(
            user.get("role") or ""
        ).strip()

        configuration_rights = str(
            user.get(
                "has_bi_config_rights"
            )
            or "No"
        ).strip()

        viewing_rights = str(
            user.get(
                "has_bi_view_rights"
            )
            or "No"
        ).strip()

        searchable_text = " ".join(
            [
                full_name,
                email,
                role,
                configuration_rights,
                viewing_rights,
            ]
        ).lower()

        if search_text in searchable_text:
            filtered_users.append(
                user
            )

    return filtered_users


# =============================================================================
# BUILD BI CONFIGURATION RIGHTS CONTEXT
# =============================================================================

def get_bi_configuration_rights_context(
    db_session,
    page=1,
    per_page=10,
    search_text="",
):
    """
    Build the complete modal context.

    This uses the existing paginated_processes()
    function already defined in this file.
    """

    try:
        page = int(
            page or 1
        )
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = int(
            per_page or 10
        )
    except (TypeError, ValueError):
        per_page = 10

    if page < 1:
        page = 1

    if per_page not in {
        10,
        25,
        50,
        100,
    }:
        per_page = 10

    search_text = str(
        search_text or ""
    ).strip()

    try:
        all_users = (
            normalise_bi_configuration_rights_users(
                db_session=db_session,
            )
        )

        filtered_users = (
            filter_bi_configuration_rights_users(
                users=all_users,
                search_text=search_text,
            )
        )

        (
            paginated_users,
            total_pages,
            current_page,
            total_records,
            showing_from,
            showing_to,
            page_links,
        ) = paginated_processes(
            processes=filtered_users,
            page=page,
            per_page=per_page,
        )

        full_names = sorted(
            {
                user.get("full_name")
                for user in all_users
                if user.get("full_name")
            },
            key=str.lower,
        )

        emails = sorted(
            {
                user.get("email")
                for user in all_users
                if user.get("email")
            },
            key=str.lower,
        )

        roles = sorted(
            {
                user.get("role")
                for user in all_users
                if user.get("role")
            },
            key=str.lower,
        )

        return {
            "bi_configuration_rights_users":
                paginated_users,

            "bi_rights_current_page":
                current_page,

            "bi_rights_total_pages":
                total_pages,

            "bi_rights_total_records":
                total_records,

            "bi_rights_showing_from":
                showing_from,

            "bi_rights_showing_to":
                showing_to,

            "bi_rights_page_links":
                page_links,

            "bi_rights_per_page":
                per_page,

            "bi_rights_search_text":
                search_text,

            "bi_rights_full_names":
                full_names,

            "bi_rights_emails":
                emails,

            "bi_rights_roles":
                roles,
        }

    except Exception as error:
        db_session.rollback()

        print(
            "get_bi_configuration_rights_context error:",
            error,
        )

        return {
            "bi_configuration_rights_users": [],
            "bi_rights_current_page": 1,
            "bi_rights_total_pages": 1,
            "bi_rights_total_records": 0,
            "bi_rights_showing_from": 0,
            "bi_rights_showing_to": 0,
            "bi_rights_page_links": [1],
            "bi_rights_per_page": per_page,
            "bi_rights_search_text": search_text,
            "bi_rights_full_names": [],
            "bi_rights_emails": [],
            "bi_rights_roles": [],
        }


# =============================================================================
# INSERT OR UPDATE BI CONFIGURATION AND VIEWING RIGHTS
# =============================================================================

def save_bi_configuration_and_view_rights(
    db_session,
    users,
    updated_by,
):
    """
    Insert or update one global BI-rights row per user.

    A user can have:
    - Configuration Yes, Viewing Yes
    - Configuration Yes, Viewing No
    - Configuration No, Viewing Yes
    - Configuration No, Viewing No
    """

    users = list(
        users or []
    )

    if not users:
        return {
            "success": False,
            "message": (
                "No user rights were supplied."
            ),
            "saved_users": 0,
        }

    sql_statement = text(
        """
        INSERT INTO public.users_bi_config_rights
        (
            user_id,
            full_name,
            email,
            role,
            has_bi_config_rights,
            has_bi_view_rights,
            created_by,
            created_at,
            updated_by,
            updated_at
        )

        SELECT
            u.user_id,
            u.full_name,
            u.email,
            u.role,
            :has_bi_config_rights,
            :has_bi_view_rights,
            :updated_by,
            CURRENT_TIMESTAMP,
            :updated_by,
            CURRENT_TIMESTAMP

        FROM public.users AS u

        WHERE u.user_id = :user_id
          AND u.is_active = TRUE

        ON CONFLICT (
            user_id
        )

        DO UPDATE SET
            full_name =
                EXCLUDED.full_name,

            email =
                EXCLUDED.email,

            role =
                EXCLUDED.role,

            has_bi_config_rights =
                EXCLUDED.has_bi_config_rights,

            has_bi_view_rights =
                EXCLUDED.has_bi_view_rights,

            updated_by =
                EXCLUDED.updated_by,

            updated_at =
                CURRENT_TIMESTAMP
        """
    )

    saved_users = 0

    try:
        for user_item in users:
            user_id = str(
                user_item.get("user_id") or ""
            ).strip()

            if not user_id:
                continue

            configuration_rights = (
                "Yes"
                if str(
                    user_item.get(
                        "has_bi_config_rights"
                    )
                    or "No"
                ).strip().lower()
                == "yes"
                else "No"
            )

            viewing_rights = (
                "Yes"
                if str(
                    user_item.get(
                        "has_bi_view_rights"
                    )
                    or "No"
                ).strip().lower()
                == "yes"
                else "No"
            )

            result = db_session.execute(
                sql_statement,
                {
                    "user_id":
                        user_id,

                    "has_bi_config_rights":
                        configuration_rights,

                    "has_bi_view_rights":
                        viewing_rights,

                    "updated_by": str(
                        updated_by or ""
                    ).strip(),
                },
            )

            if result.rowcount:
                saved_users += 1

        db_session.commit()

        return {
            "success": True,
            "message": (
                "BI configuration and viewing "
                "rights were saved successfully."
            ),
            "saved_users": saved_users,
        }

    except Exception as error:
        db_session.rollback()

        print(
            "save_bi_configuration_and_view_rights error:",
            error,
        )

        return {
            "success": False,
            "message": str(
                error
            ),
            "saved_users": 0,
        }


# =============================================================================
# ATTACH SIGNED-IN USER RIGHTS TO BI RECORDS
# =============================================================================

def attach_bi_access_rights_to_records(
    db_session,
    bi_records,
    user_id,
):
    """
    Attach the signed-in user's global BI rights
    to every BI record.

    public.users_bi_config_rights contains one
    rights row per user.
    """

    records = [
        dict(record)
        for record in list(
            bi_records or []
        )
    ]

    clean_user_id = str(
        user_id or ""
    ).strip()

    if not records:
        return []

    if not clean_user_id:
        for record in records:
            record[
                "has_bi_config_rights"
            ] = False

            record[
                "has_bi_view_rights"
            ] = False

        return records

    has_config_rights = False
    has_view_rights = False

    try:
        rights_records = db_session.execute(
            text(
                """
                SELECT
                    COALESCE(
                        has_bi_config_rights,
                        'No'
                    ) AS has_bi_config_rights,

                    COALESCE(
                        has_bi_view_rights,
                        'No'
                    ) AS has_bi_view_rights

                FROM public.users_bi_config_rights

                WHERE user_id = :user_id

                LIMIT 1
                """
            ),
            {
                "user_id":
                    clean_user_id,
            },
        ).mappings().all()

        rights_record = rights_records[0] if rights_records else None

        if rights_record:
            has_config_rights = (
                str(
                    rights_record.get(
                        "has_bi_config_rights"
                    )
                    or "No"
                ).strip().lower()
                == "yes"
            )

            has_view_rights = (
                str(
                    rights_record.get(
                        "has_bi_view_rights"
                    )
                    or "No"
                ).strip().lower()
                == "yes"
            )

    except Exception as error:
        db_session.rollback()

        print(
            "attach_bi_access_rights_to_records error:",
            error,
        )

    for record in records:
        record[
            "has_bi_config_rights"
        ] = has_config_rights

        record[
            "has_bi_view_rights"
        ] = has_view_rights

    return records
