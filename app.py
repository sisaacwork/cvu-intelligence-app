"""CVU Intelligence App — Streamlit entry point.

Workflow:
    1. Sidebar: WordPress login + DB credentials (held in session_state).
    2. Main: pick geography type + items, choose tier(s), generate.
    3. On Generate:
        a. pull MySQL → buildings, teams, team_builds, country_city_map
        b. pull Postgres → ghsl
        c. build boundary config
        d. for each chosen tier: build payload + POST /mds/v1/intelligence/publish
        e. show edit links for the created drafts.
    4. Bottom: recently created drafts.

Mirrors the tkinter desktop tool's "one combined report per selection" model:
selecting multiple geos produces a single report with all of them merged.
"""

from __future__ import annotations

import hmac
import io
import os
from contextlib import redirect_stdout
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

import cvu_intelligence_core as core
from cvu_intelligence_core.wp_client import WPClient, WPClientError


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# Bridge: when running on Streamlit Cloud (or any host that injects values
# via st.secrets), copy them into os.environ so the rest of the codebase
# keeps reading os.environ uniformly. No-op locally when no secrets.toml
# is present — Streamlit raises in that case and we swallow it.
try:
    _secrets = dict(st.secrets)
    for _k, _v in _secrets.items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ[_k] = str(_v)
except Exception:  # noqa: BLE001 — Streamlit raises different exception types across versions
    pass


def env(key, default=""):
    return os.environ.get(key, default) or ""


DEFAULTS = {
    "wp_base_url":    env("WP_BASE_URL", "https://verticalurbanism.org"),
    "mysql_host":     env("CTBUH_MYSQL_HOST", "mysql.ctbuh.org"),
    "mysql_port":     env("CTBUH_MYSQL_PORT", "3306"),
    "mysql_user":     env("CTBUH_MYSQL_USER", "build_db_prod_RO"),
    "mysql_password": env("CTBUH_MYSQL_PASSWORD", ""),
    "mysql_database": env("CTBUH_MYSQL_DATABASE", "buldingdb"),
    "pg_host":        env("GHSL_PG_HOST", "vui-vui.i.aivencloud.com"),
    "pg_port":        env("GHSL_PG_PORT", "15955"),
    "pg_user":        env("GHSL_PG_USER", "avnadmin"),
    "pg_password":    env("GHSL_PG_PASSWORD", ""),
    "pg_database":    env("GHSL_PG_DATABASE", "defaultdb"),
}


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="CVU Intelligence", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# App password gate
# ---------------------------------------------------------------------------
# Soft gate against casual access. Per-browser-session only — closing the tab
# requires re-entry. NOT a security boundary; the real auth happens on the
# WordPress side via app passwords. Set APP_PASSWORD in .env to override.
APP_PASSWORD = env("APP_PASSWORD", "rtl2026")

if not st.session_state.get("gate_authed"):
    st.title("CVU Intelligence")
    st.caption("Restricted — enter the access password to continue.")
    with st.form("gate_form", clear_on_submit=False):
        pw_attempt = st.text_input("Password", type="password", label_visibility="collapsed",
                                   placeholder="Password")
        unlock = st.form_submit_button("Unlock")
    if unlock:
        if hmac.compare_digest(pw_attempt, APP_PASSWORD):
            st.session_state["gate_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()


st.title("CVU Intelligence Generator")
st.caption(
    "Pull building + GHSL data and publish a draft Intelligence Brief or "
    "Report to WordPress for editor review."
)


# ---------------------------------------------------------------------------
# Sidebar: WordPress login + DB credentials
# ---------------------------------------------------------------------------
with st.sidebar:
    section = st.radio(
        "View",
        options=["Generator", "Setup Instructions"],
        index=0,
        label_visibility="collapsed",
    )
    st.divider()
    st.header("WordPress")

    wp_base_url = st.text_input(
        "Base URL",
        value=st.session_state.get("wp_base_url", DEFAULTS["wp_base_url"]),
    )
    wp_username = st.text_input(
        "Username",
        value=st.session_state.get("wp_username", ""),
        placeholder="iwork",
    )
    wp_app_password = st.text_input(
        "Application password",
        type="password",
        value=st.session_state.get("wp_app_password", ""),
        help="Generate at /wp-admin/profile.php → Application Passwords.",
    )

    if st.button("Verify login", use_container_width=True):
        try:
            client = WPClient(wp_base_url, wp_username, wp_app_password)
            me = client.verify()
            st.session_state.update({
                "wp_base_url":     wp_base_url,
                "wp_username":     wp_username,
                "wp_app_password": wp_app_password,
                "wp_me":           me,
            })
            st.success(f"Authenticated as **{me.get('name', '?')}**")
        except WPClientError as e:
            st.error(f"Auth failed: {e}")

    me = st.session_state.get("wp_me")
    if me:
        st.caption(f"Logged in: {me.get('name', '?')} (id {me.get('id', '?')})")
    else:
        st.caption("Not logged in.")

    st.divider()
    st.header("Database credentials")
    with st.expander("MySQL (CTBUH)", expanded=False):
        mysql_cfg = {
            "host":     st.text_input("Host",     DEFAULTS["mysql_host"],     key="mysql_host"),
            "port":     st.text_input("Port",     DEFAULTS["mysql_port"],     key="mysql_port"),
            "user":     st.text_input("User",     DEFAULTS["mysql_user"],     key="mysql_user"),
            "password": st.text_input("Password", DEFAULTS["mysql_password"], type="password", key="mysql_password"),
            "database": st.text_input("Database", DEFAULTS["mysql_database"], key="mysql_database"),
        }
    with st.expander("Postgres (Aiven / GHSL)", expanded=False):
        pg_cfg = {
            "host":     st.text_input("Host",     DEFAULTS["pg_host"],     key="pg_host"),
            "port":     st.text_input("Port",     DEFAULTS["pg_port"],     key="pg_port"),
            "user":     st.text_input("User",     DEFAULTS["pg_user"],     key="pg_user"),
            "password": st.text_input("Password", DEFAULTS["pg_password"], type="password", key="pg_password"),
            "database": st.text_input("Database", DEFAULTS["pg_database"], key="pg_database"),
        }


# ---------------------------------------------------------------------------
# Setup Instructions view
# ---------------------------------------------------------------------------
if section == "Setup Instructions":
    st.title("Setup Instructions")
    st.markdown(
        "### 1. Generate a WordPress application password\n\n"
        "1. Log into "
        "[verticalurbanism.org/wp-admin](https://verticalurbanism.org/wp-admin/).\n"
        "2. Click **Profile** in the WordPress sidebar.\n"
        "3. Scroll to the bottom of the page to the **Application Passwords** section.\n"
        "4. Enter `Intelligence Admin` as the name and click "
        "**Add New Application Password**.\n"
        "5. **Save the generated password somewhere safe** — WordPress will not "
        "show it to you again.\n\n"
        "### 2. Log into this app\n\n"
        "Use the **WordPress** section in the sidebar:\n\n"
        "- **Username:** your WordPress username (first initial + last name, "
        "e.g. `iwork`).\n"
        "- **Password:** the application password you just generated.\n\n"
        "### 3. Database credentials\n\n"
        "Database credentials are pre-filled and hidden under "
        "**Database credentials → MySQL / Postgres** in the sidebar. "
        "You don't need to touch them.\n\n"
        "### Not sure which product you need?\n\n"
        "See the "
        "[Intelligence overview]"
        "(https://verticalurbanism.org/resources/research/intelligence/) "
        "for the difference between an Intelligence Brief and a Report."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Main: generator flow
# ---------------------------------------------------------------------------
logged_in = bool(st.session_state.get("wp_me"))
if not logged_in:
    st.info("👈 Log in to WordPress in the sidebar to enable generation.")

st.header("1. Geography")
col_type, col_btn = st.columns([2, 1])
with col_type:
    geo_type = st.selectbox(
        "Type",
        options=["agglomeration", "region", "country", "city"],
        index=0,
        format_func=str.title,
    )
with col_btn:
    st.write("")  # vertical alignment
    st.write("")
    load_clicked = st.button("Load list", use_container_width=True)

min_height_for_list = st.session_state.get("min_height", 75)
if load_clicked:
    with st.spinner(f"Loading {geo_type} list from MySQL…"):
        try:
            geos = core.list_geographies(mysql_cfg, geo_type, min_height=min_height_for_list)
            st.session_state["geo_list"] = geos
            st.session_state["geo_list_type"] = geo_type
            st.success(f"Loaded {len(geos)} {geo_type}(s).")
        except Exception as e:  # noqa: BLE001 — surface DB errors to the user
            st.error(f"MySQL failed: {e}")

geo_list = st.session_state.get("geo_list", [])
geo_list_type = st.session_state.get("geo_list_type")
if geo_list and geo_list_type != geo_type:
    st.info(f"Loaded list is for `{geo_list_type}`. Click **Load list** to refresh for `{geo_type}`.")

if geo_list:
    # Format options as "Name (count buildings)" so users can prioritise.
    options = {f"{g['name']}  ({g['count']:,} buildings)": g for g in geo_list}
    selected_labels = st.multiselect(
        f"{geo_type.title()}(s) — pick one or more",
        options=list(options.keys()),
        max_selections=20,
        help="Multiple selections are merged into a single combined report.",
    )
    selected_geos = [options[lbl] for lbl in selected_labels]
else:
    selected_geos = []
    st.caption("No list loaded yet — click **Load list** above.")


st.header("2. Output")
col_brief, col_report, col_height = st.columns([1, 1, 2])
with col_brief:
    do_brief = st.checkbox("Intelligence Brief", value=False, help="Tier 2 — Snapshot")
with col_report:
    do_report = st.checkbox("Intelligence Report", value=True, help="Tier 3 — Full")
with col_height:
    min_height = st.number_input("Minimum building height (m)", min_value=0, value=75, step=5)
    st.session_state["min_height"] = min_height


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
st.header("3. Generate")

can_generate = bool(
    logged_in
    and selected_geos
    and (do_brief or do_report)
    and mysql_cfg.get("password")
    and pg_cfg.get("password")
)
go = st.button(
    "Generate drafts",
    type="primary",
    disabled=not can_generate,
    use_container_width=False,
    help=(None if can_generate else
          "Log in to WP, pick at least one geography, choose a tier, and fill in DB passwords."),
)


def _combined_geo_name(geos):
    names = [g["name"] for g in geos]
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ", ".join(names)
    return f"{names[0]} + {len(names) - 1} more"


def _run_generation():
    """Execute the full pipeline: pull → build payload → POST per tier."""
    geo_ids = [g["id"] for g in selected_geos]
    geo_names = [g["name"] for g in selected_geos]
    report_name = _combined_geo_name(selected_geos)
    tiers = []
    if do_brief:  tiers.append("brief")
    if do_report: tiers.append("report")

    log_buf = io.StringIO()
    def log(msg):
        log_buf.write(str(msg) + "\n")
        log_area.code(log_buf.getvalue(), language="text")

    log(f"=== Generating for: {report_name} ===")
    log(f"  geo_type={geo_type}, ids={geo_ids}")
    log(f"  tiers={tiers}, min_height={min_height}")

    with st.status("Pulling MySQL data…", expanded=True) as status:
        try:
            buildings, teams, team_builds, country_city_map = core.pull_mysql_data(
                mysql_cfg, geo_type, geo_ids, log, min_height=min_height,
            )
        except Exception as e:  # noqa: BLE001
            status.update(label=f"MySQL failed: {e}", state="error")
            st.error(f"MySQL failed: {e}")
            return

        log("Building boundary config…")
        try:
            boundary = core.build_boundary_config(
                country_city_map, geo_type, geo_names, log,
            )
        except Exception as e:  # noqa: BLE001
            log(f"  Boundary failed (continuing without overlay): {e}")
            boundary = []

        log("Pulling GHSL data…")
        try:
            ghsl = core.pull_ghsl_data(
                pg_cfg, geo_type, geo_ids, geo_names, mysql_cfg, log,
            )
        except Exception as e:  # noqa: BLE001
            status.update(label=f"Postgres failed: {e}", state="error")
            st.error(f"Postgres failed: {e}")
            return

        status.update(label="Publishing to WordPress…", state="running")
        wp_client = WPClient(
            st.session_state["wp_base_url"],
            st.session_state["wp_username"],
            st.session_state["wp_app_password"],
            timeout=120,
        )

        results = []
        for tier in tiers:
            log(f"Publishing tier={tier}…")
            payload = core.build_publish_payload(
                tier=tier,
                geo_type=geo_type,
                geo_name=report_name,
                geo_ids=geo_ids,
                min_height=min_height,
                buildings=buildings,
                teams=teams,
                team_builds=team_builds,
                ghsl=ghsl,
                boundary=boundary,
            )
            try:
                resp = wp_client.publish(payload)
                results.append(resp)
                log(f"  ✓ post_id={resp['post_id']} slug={resp['slug']}")
            except WPClientError as e:
                log(f"  ✗ {tier} publish failed: {e}")
                st.error(f"{tier} publish failed: {e}")

        status.update(label=f"Done — created {len(results)} draft(s).", state="complete")

    if results:
        st.success(f"Created **{len(results)}** draft(s).")
        for r in results:
            tier_label = r.get("tier", "?").title()
            geo = r.get("geo_name", "?")
            edit = r.get("edit_url") or "#"
            view = r.get("view_url") or "#"
            st.markdown(
                f"- **{tier_label}** — {geo}  "
                f"[· edit draft]({edit}) · [preview]({view})"
            )


log_area = st.empty()
if go:
    _run_generation()


# ---------------------------------------------------------------------------
# Recent drafts (read from WP)
# ---------------------------------------------------------------------------
st.divider()
st.header("Recent reports")
if logged_in:
    if st.button("Refresh list"):
        try:
            wp_client = WPClient(
                st.session_state["wp_base_url"],
                st.session_state["wp_username"],
                st.session_state["wp_app_password"],
            )
            posts = wp_client.list_reports(status="any", per_page=20)
            st.session_state["recent_posts"] = posts
        except WPClientError as e:
            st.error(f"Could not fetch reports: {e}")

    posts = st.session_state.get("recent_posts", [])
    if posts:
        rows = []
        for p in posts:
            title = (p.get("title") or {}).get("rendered", "(untitled)")
            rows.append({
                "id":     p.get("id"),
                "title":  title,
                "status": p.get("status"),
                "slug":   p.get("slug"),
                "link":   p.get("link"),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("Click **Refresh list** to load recent intelligence_report posts.")
else:
    st.caption("Log in to see existing reports.")
