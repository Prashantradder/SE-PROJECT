# app.py
import streamlit as st
from database import init_db, get_conn
import auth
import change_requests
import cab_approval
import utils
import blackout
from sla_engine import check_sla_for_change_row, escalate_sla_breach
import pandas as pd
import networkx as nx
from pyvis.network import Network
from pathlib import Path
import datetime
import time

# -----------------------------------------------------------------------------
# INITIALIZATION
# -----------------------------------------------------------------------------
conn = init_db()
auth.ensure_admin_exists()

st.set_page_config(page_title="Change Management System", layout="wide")

# -----------------------------------------------------------------------------
# SESSION STATE HELPERS (TESTABLE)
# -----------------------------------------------------------------------------
SESSION_KEYS_DEFAULTS = {
    "username": None,
    "role": None,
    "password_ok": False,
    "generated_otp": None,
    "otp_expiry": None,
    "temp_user": None,
    "temp_role": None,
    "last_activity": time.time(),
    "impact_change_id": None,
    "trigger_my_impact": False,
    "trigger_all_impact": False,
}


def ensure_session_state_defaults():
    """Ensure all expected session state keys exist.

    Pure logic is simple, but this lets you unit test that default values
    are consistent in one place.
    """
    for k, v in SESSION_KEYS_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def update_activity():
    st.session_state["last_activity"] = time.time()


def clear_login_state():
    """Clear all login-related session keys."""
    for key in [
        "username",
        "role",
        "password_ok",
        "generated_otp",
        "otp_expiry",
        "temp_user",
        "temp_role",
    ]:
        st.session_state[key] = SESSION_KEYS_DEFAULTS[key]


def check_auto_logout(timeout_seconds: int = 15 * 60):
    """Auto-logout user after inactivity.

    Logic is simple; can be unit-tested by controlling last_activity and now.
    """
    if st.session_state.get("username"):
        now_ts = time.time()
        inactivity = now_ts - st.session_state.get("last_activity", now_ts)
        if inactivity > timeout_seconds:
            clear_login_state()
            st.warning(
                "⚠️ Session expired due to 15 minutes of inactivity. "
                "Please log in again."
            )
            st.stop()


# -----------------------------------------------------------------------------
# AUTH / LOGIN PANEL (UI + A BIT OF LOGIC)
# -----------------------------------------------------------------------------
def handle_password_step(user: str, pwd: str):
    """Handle the username/password portion (separate for easier testing)."""
    ok, info = auth.authenticate(user, pwd)
    if not ok:
        return False, info

    st.session_state["temp_user"] = user
    st.session_state["temp_role"] = info
    otp, expiry = auth.generate_otp()
    st.session_state["generated_otp"] = str(otp)
    st.session_state["otp_expiry"] = expiry
    st.session_state["password_ok"] = True
    update_activity()
    return True, otp


def handle_otp_step(otp_input: str, now_ts: float | None = None):
    """Validate OTP. Split from UI for easier unit testing."""
    if now_ts is None:
        now_ts = time.time()

    expiry = st.session_state.get("otp_expiry") or 0
    if now_ts > expiry:
        st.session_state["password_ok"] = False
        return False, "OTP expired. Please restart login."

    if otp_input != st.session_state.get("generated_otp"):
        return False, "Invalid OTP. Try again."

    # success → set actual login
    st.session_state["username"] = st.session_state.get("temp_user")
    st.session_state["role"] = st.session_state.get("temp_role")
    st.session_state["password_ok"] = False

    # reset temps
    st.session_state["temp_user"] = None
    st.session_state["temp_role"] = None
    st.session_state["generated_otp"] = None
    st.session_state["otp_expiry"] = None
    update_activity()
    return True, f"Logged in as {st.session_state['username']}"


def login_panel():
    st.sidebar.header("Authentication")
    mode = st.sidebar.radio("Mode", ["Login", "Register"])

    if mode == "Login":
        user = st.sidebar.text_input("Username")
        pwd = st.sidebar.text_input("Password", type="password")

        if st.sidebar.button("Next"):
            ok, result = handle_password_step(user, pwd)
            if ok:
                otp = result
                st.success("Password verified. OTP generated.")
                st.info(f"🔐 **Your OTP is: {otp}** (valid for 30 seconds)")
            else:
                st.error(result)

        if st.session_state.get("password_ok"):
            otp_in = st.sidebar.text_input("Enter OTP")
            if st.sidebar.button("Verify OTP"):
                ok, msg = handle_otp_step(otp_in)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    else:
        new_user = st.sidebar.text_input("New username")
        new_pwd = st.sidebar.text_input("New password", type="password")
        role = st.sidebar.selectbox("Role", ["requester", "approver", "cab", "admin"])
        if st.sidebar.button("Register"):
            created = auth.create_user(new_user, new_pwd, role)
            if created:
                st.success("User created. Please login.")
            else:
                st.error("User exists or creation failed.")


# -----------------------------------------------------------------------------
# UTILS / DATA HELPERS (HIGHLY TESTABLE)
# -----------------------------------------------------------------------------
def load_cis_list(conn_):
    cur = conn_.cursor()
    cur.execute("SELECT id, name FROM cis ORDER BY name")
    return cur.fetchall()


def sla_badge_text(s: str) -> str:
    if s.startswith("✔"):
        return f"🟢 {s}"
    if s.startswith("⛔"):
        return f"🔴 {s}"
    return s


def apply_sla_status(rows: list[dict]) -> list[dict]:
    """Given rows of change data, compute and add 'sla_status'."""
    for r in rows:
        overdue = check_sla_for_change_row(r)
        if overdue is not None:
            r["sla_status"] = sla_badge_text(f"⛔ Overdue by {overdue} hrs")
            escalate_sla_breach(r["change_id"])
        else:
            r["sla_status"] = sla_badge_text("✔ On Time")
    return rows


def fetch_my_changes(conn_, username: str) -> list[dict]:
    q = """
    SELECT 
        cr.change_id,
        cr.title,
        cr.category,
        cr.workflow_status,
        cr.risk_score,
        cr.scheduled_start,
        cr.scheduled_end,
        c.name AS ci_name,
        cr.created_at,
        cr.last_status_change
    FROM change_requests cr
    LEFT JOIN cis c ON cr.ci_id = c.id
    WHERE cr.created_by = ?
    ORDER BY cr.created_at DESC
    """
    cur = conn_.cursor()
    cur.execute(q, (username,))
    return [dict(r) for r in cur.fetchall()]


def fetch_all_changes(conn_) -> list[dict]:
    q = """
    SELECT 
        cr.change_id,
        cr.title,
        cr.created_by,
        cr.category,
        cr.workflow_status,
        cr.risk_score,
        cr.scheduled_start,
        cr.scheduled_end,
        c.name AS ci_name,
        cr.created_at,
        cr.last_status_change
    FROM change_requests cr
    LEFT JOIN cis c ON cr.ci_id = c.id
    ORDER BY cr.created_at DESC
    """
    cur = conn_.cursor()
    cur.execute(q)
    return [dict(r) for r in cur.fetchall()]


def build_ci_graph(conn_) -> tuple[nx.DiGraph, dict]:
    """Build CI dependency graph and name mapping.

    Returns:
        G: networkx.DiGraph
        ci_name_map: {id: name}
    """
    cur = conn_.cursor()
    cur.execute("SELECT id, name FROM cis")
    cis = cur.fetchall()
    ci_name_map = {c["id"]: c["name"] for c in cis}

    G = nx.DiGraph()
    for name in ci_name_map.values():
        G.add_node(name)

    cur.execute("SELECT ci_from, ci_to FROM dependencies")
    deps = cur.fetchall()
    for d in deps:
        from_name = ci_name_map.get(d["ci_from"])
        to_name = ci_name_map.get(d["ci_to"])
        if from_name and to_name:
            G.add_edge(from_name, to_name)

    return G, ci_name_map


def build_impact_subsets(G: nx.DiGraph, ci_name: str) -> tuple[list[str], list[str]]:
    """Return upstream and downstream nodes for a selected CI."""
    upstream = list(nx.ancestors(G, ci_name))
    downstream = list(nx.descendants(G, ci_name))
    return upstream, downstream


def render_pyvis_graph(G: nx.DiGraph, node_styles: dict[str, dict], html_file: str):
    """Create a PyVis graph from G and node styles; write to html_file."""
    net = Network(height="600px", width="100%", directed=True)

    for node in G.nodes():
        style = node_styles.get(node, {})
        net.add_node(node, label=node, **style)

    for u, v in G.edges():
        net.add_edge(u, v)

    html_path = Path(html_file)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(html_path))

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    st.components.v1.html(html, height=600, scrolling=True)


# -----------------------------------------------------------------------------
# PAGE RENDERERS
# -----------------------------------------------------------------------------
def page_submit_change(conn_, username: str):
    st.header("Submit Change Request")

    title = st.text_input("Title")
    description = st.text_area("Description")
    category = st.selectbox("Category", ["Normal", "Emergency", "Standard"])

    cis = load_cis_list(conn_)
    ci_map = {c["name"]: c["id"] for c in cis} if cis else {}
    ci_choice = st.selectbox("Configuration Item (CI)", ["-- none --"] + list(ci_map.keys()))

    st.subheader("Risk Assessment Questions")
    q1 = st.selectbox("Does this change impact production?", ["No", "Yes"])
    q2 = st.selectbox("Is there NO rollback plan available?", ["No", "Yes"])
    q3 = st.selectbox("Does this affect a critical system/CI?", ["No", "Yes"])
    q4 = st.selectbox("Could customers/end-users be impacted?", ["No", "Yes"])

    start_date = st.date_input("Scheduled Start Date")
    start_time = st.time_input("Scheduled Start Time", value=datetime.time(9, 0))
    end_date = st.date_input("Scheduled End Date")
    end_time = st.time_input("Scheduled End Time", value=datetime.time(10, 0))

    start_dt = datetime.datetime.combine(start_date, start_time)
    end_dt = datetime.datetime.combine(end_date, end_time)

    if st.button("Submit Change"):
        update_activity()
        if not title:
            st.error("Title is required.")
        elif end_dt <= start_dt:
            st.error("End time must be after start time.")
        else:
            start_iso = start_dt.isoformat()
            end_iso = end_dt.isoformat()

            conflicts = blackout.check_conflict(start_iso, end_iso)
            if conflicts:
                st.error(
                    "❌ Scheduling conflict: your requested window overlaps "
                    "an administrative blackout window."
                )
                for c in conflicts:
                    st.write(
                        f"- Blackout #{c['id']}: "
                        f"{c['start_dt']} → {c['end_dt']} — {c['reason']}"
                    )
            else:
                ci_id = ci_map.get(ci_choice) if ci_choice != "-- none --" else None
                cid = change_requests.submit_change(
                    title=title,
                    description=description,
                    category=category,
                    ci_id=ci_id,
                    start=start_iso,
                    end=end_iso,
                    created_by=username,
                    q1=q1,
                    q2=q2,
                    q3=q3,
                    q4=q4,
                )
                st.success(f"Change submitted successfully! ID: {cid}")


def page_my_changes(conn_, username: str):
    st.header("My Changes")
    rows = fetch_my_changes(conn_, username)

    if not rows:
        st.info("No changes found.")
        update_activity()
        return

    rows = apply_sla_status(rows)
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.subheader("View Impact Map for any Change")
    for r in rows:
        if st.button(f"Impact Map: {r['change_id']}", key=f"imp_my_{r['change_id']}"):
            st.session_state["impact_change_id"] = r["change_id"]
            st.session_state["trigger_my_impact"] = True

    if st.session_state.get("trigger_my_impact"):
        st.session_state["trigger_my_impact"] = False
        st.rerun()

    update_activity()


def page_all_changes(conn_):
    st.header("All Changes")
    rows = fetch_all_changes(conn_)

    if not rows:
        st.info("No changes present.")
        update_activity()
        return

    rows = apply_sla_status(rows)
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.subheader("View Impact Map for any Change")
    for r in rows:
        if st.button(f"Impact Map: {r['change_id']}", key=f"imp_all_{r['change_id']}"):
            st.session_state["impact_change_id"] = r["change_id"]
            st.session_state["trigger_all_impact"] = True

    if st.session_state.get("trigger_all_impact"):
        st.session_state["trigger_all_impact"] = False
        st.experimental_rerun()

    update_activity()


def page_cab_review(conn_, username: str, role: str):
    if role not in ("cab", "approver", "admin"):
        st.error("Access denied. CAB/Approver/Admin only.")
        return

    st.header("CAB Review Queue")
    cur = conn_.cursor()
    cur.execute(
        "SELECT * FROM change_requests "
        "WHERE workflow_status IN ('Pending CAB','Draft')"
    )
    rows = cur.fetchall()
    if not rows:
        st.info("No pending CAB items.")
        return

    for r in rows:
        st.subheader(f"{r['change_id']} — {r['title']}")
        st.write(
            "Category:", r["category"],
            "Risk:", r["risk_score"],
            "Status:", r["workflow_status"]
        )
        st.write("Description:", r["description"])

        if st.button(f"Approve {r['change_id']}", key=f"appr_{r['change_id']}"):
            try:
                cab_approval.record_approval(r["change_id"], username, "Approve")
                st.success("Approved.")
                update_activity()
            except Exception as e:
                st.error(f"Approval failed: {e}")

        if st.button(f"Reject {r['change_id']}", key=f"rej_{r['change_id']}"):
            try:
                cab_approval.record_approval(r["change_id"], username, "Reject")
                st.warning("Rejected.")
                update_activity()
            except Exception as e:
                st.error(f"Reject failed: {e}")


def page_audit_logs(conn_):
    st.header("Audit Logs")
    cur = conn_.cursor()
    cur.execute("SELECT change_id FROM change_requests ORDER BY created_at DESC")
    change_ids = [r["change_id"] for r in cur.fetchall()]

    selected_change = st.selectbox(
        "Filter logs by Change Request ID", ["-- Select --"] + change_ids
    )

    if selected_change != "-- Select --":
        st.subheader(f"Audit Logs for: {selected_change}")
        cur.execute(
            """
            SELECT *
            FROM audit_logs
            WHERE metadata = ?
            ORDER BY created_at DESC
            """,
            (selected_change,),
        )
        logs = cur.fetchall()
        if logs:
            st.dataframe(pd.DataFrame(logs), use_container_width=True)
        else:
            st.info("No audit logs found for this change request.")

        if st.button("Show All Logs"):
            selected_change = "-- Select --"

    if selected_change == "-- Select --":
        st.subheader("All Audit Logs")
        cur.execute("SELECT * FROM audit_logs ORDER BY created_at DESC")
        logs = cur.fetchall()
        if logs:
            st.dataframe(pd.DataFrame(logs), use_container_width=True)
        else:
            st.info("No audit logs recorded yet.")

    update_activity()


def page_dependency_map(conn_):
    st.header("CI Dependency Map")
    G, ci_name_map = build_ci_graph(conn_)

    if not ci_name_map:
        st.info("No CIs found. Add in Admin.")
        return

    node_styles = {n: {} for n in G.nodes()}
    render_pyvis_graph(G, node_styles, "data/dependency_map.html")
    update_activity()


def page_impact_analysis(conn_):
    st.header("CI Impact Analysis")
    change_id = st.session_state.get("impact_change_id")
    if not change_id:
        st.info("Select a Change Request from My Changes or All Changes.")
        st.stop()

    cur = conn_.cursor()
    cur.execute(
        """
        SELECT cr.change_id, cr.title, cr.description, cr.ci_id, 
               c.name AS ci_name
        FROM change_requests cr
        LEFT JOIN cis c ON cr.ci_id = c.id
        WHERE cr.change_id = ?
        """,
        (change_id,),
    )
    row = cur.fetchone()
    if not row:
        st.error("Change not found.")
        st.stop()

    ci_id = row["ci_id"]
    selected_ci = row["ci_name"]

    st.subheader(f"Change ID: {row['change_id']}")
    st.write("### Title:", row["title"])
    st.write("### Selected CI:", selected_ci)

    G, ci_name_map = build_ci_graph(conn_)
    if not ci_name_map:
        st.info("No CIs found.")
        st.stop()

    if selected_ci not in ci_name_map.values():
        st.error("Selected CI not found in dependency graph.")
        st.stop()

    upstream, downstream = build_impact_subsets(G, selected_ci)

    node_styles = {}
    for node in G.nodes():
        if node == selected_ci:
            node_styles[node] = {"color": "green"}
        elif node in downstream:
            node_styles[node] = {"color": "red"}
        elif node in upstream:
            node_styles[node] = {"color": "orange"}
        else:
            node_styles[node] = {"color": "#85C1E9"}

    render_pyvis_graph(G, node_styles, "data/impact_map.html")


def page_admin(conn_, role: str):
    if role != "admin":
        st.error("Admin only section.")
        st.stop()

    st.header("Admin Console")

    # Add CI
    st.subheader("Add Configuration Item (CI)")
    name = st.text_input("CI Name")
    if st.button("Add CI"):
        if not name:
            st.error("Enter CI name.")
        else:
            try:
                cur = conn_.cursor()
                cur.execute("INSERT INTO cis (name) VALUES (?)", (name,))
                conn_.commit()
                st.success("CI added.")
            except Exception as e:
                st.error(f"Failed to add CI: {e}")

    st.markdown("---")

    # Manage CI Dependencies
    st.subheader("Manage CI Dependencies")
    cur = conn_.cursor()
    cur.execute("SELECT id, name FROM cis ORDER BY name")
    cis = cur.fetchall()
    if not cis:
        st.info("Please add CI items first.")
    else:
        ci_map = {c["name"]: c["id"] for c in cis}
        ci_names = list(ci_map.keys())

        colA, colB = st.columns(2)
        with colA:
            dep_from = st.selectbox("CI From (Source)", ci_names)
        with colB:
            dep_to = st.selectbox("CI To (Destination)", ci_names)

        if st.button("Add Dependency (CI From → CI To)"):
            if dep_from == dep_to:
                st.error("A CI cannot depend on itself.")
            else:
                try:
                    cur.execute(
                        "INSERT INTO dependencies (ci_from, ci_to) VALUES (?, ?)",
                        (ci_map[dep_from], ci_map[dep_to]),
                    )
                    conn_.commit()
                    st.success(f"Dependency added: {dep_from} → {dep_to}")
                except Exception as e:
                    st.error(f"Failed to add dependency: {e}")

        st.markdown("### Existing Dependencies")
        cur.execute(
            """
            SELECT d.id, c1.name AS from_ci, c2.name AS to_ci
            FROM dependencies d
            LEFT JOIN cis c1 ON d.ci_from = c1.id
            LEFT JOIN cis c2 ON d.ci_to = c2.id
            ORDER BY d.id DESC
            """
        )
        deps_list = cur.fetchall()
        if not deps_list:
            st.info("No dependencies added yet.")
        else:
            st.table(pd.DataFrame([dict(d) for d in deps_list]))

        dep_id_to_delete = st.text_input("Enter Dependency ID to delete")
        if st.button("Delete Dependency"):
            try:
                if not dep_id_to_delete:
                    st.error("Enter a dependency ID.")
                else:
                    cur.execute(
                        "DELETE FROM dependencies WHERE id = ?",
                        (dep_id_to_delete,),
                    )
                    conn_.commit()
                    st.success(f"Deleted dependency ID {dep_id_to_delete}")
                    st.experimental_rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")

    st.markdown("---")

    # Blackout windows
    st.subheader("Manage Blackout Windows (Admin)")
    col1, col2 = st.columns(2)
    with col1:
        b_start_date = st.date_input("Blackout Start Date")
        b_start_time = st.time_input("Blackout Start Time",
                                     value=datetime.time(0, 0), key="bstart")
    with col2:
        b_end_date = st.date_input("Blackout End Date")
        b_end_time = st.time_input("Blackout End Time",
                                   value=datetime.time(23, 59), key="bend")

    b_reason = st.text_input("Reason / Note for blackout")

    if st.button("Add Blackout Window"):
        b_start_dt = datetime.datetime.combine(b_start_date, b_start_time)
        b_end_dt = datetime.datetime.combine(b_end_date, b_end_time)
        if b_end_dt <= b_start_dt:
            st.error("Blackout end must be after start.")
        else:
            try:
                bid = blackout.add_blackout(
                    b_start_dt.isoformat(),
                    b_end_dt.isoformat(),
                    b_reason
                )
                st.success(f"Blackout window added (id={bid})")
            except Exception as e:
                st.error(f"Failed to add blackout: {e}")

    st.markdown("#### Existing blackout windows")
    bw = blackout.list_blackouts()
    if not bw:
        st.info("No blackout windows defined.")
    else:
        for row in bw:
            st.write(
                f"ID {row['id']}: {row['start_dt']} → {row['end_dt']} — {row['reason']}"
            )
            if st.button(f"Delete blackout {row['id']}",
                         key=f"del_bw_{row['id']}"):
                try:
                    blackout.delete_blackout(row["id"])
                    st.success(f"Deleted blackout {row['id']}")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")

    st.markdown("---")

    # Users
    st.subheader("Users")
    cur.execute("SELECT username, role, locked FROM users")
    users = cur.fetchall()
    if users:
        st.dataframe(pd.DataFrame([dict(u) for u in users]))
    else:
        st.info("No users found.")

    update_activity()


# -----------------------------------------------------------------------------
# MAIN ENTRYPOINT (SMALL → EASIER TO TEST)
# -----------------------------------------------------------------------------
def main():
    ensure_session_state_defaults()
    login_panel()
    check_auto_logout()
    update_activity()

    if not st.session_state.get("username"):
        st.title("Change Management System — Full (SLA + MFA)")
        st.info("Please login to continue.")
        st.stop()

    username = st.session_state["username"]
    role = st.session_state["role"]

    st.title("Change Management System — Full (SLA + MFA)")

    page = st.sidebar.selectbox(
        "Menu",
        [
            "Submit Change",
            "My Changes",
            "All Changes",
            "CAB Review",
            "Audit Logs",
            "Dependency Map",
            "Impact Analysis",
            "Admin",
        ],
    )

    if page == "Submit Change":
        page_submit_change(conn, username)
    elif page == "My Changes":
        page_my_changes(conn, username)
    elif page == "All Changes":
        page_all_changes(conn)
    elif page == "CAB Review":
        page_cab_review(conn, username, role)
    elif page == "Audit Logs":
        page_audit_logs(conn)
    elif page == "Dependency Map":
        page_dependency_map(conn)
    elif page == "Impact Analysis":
        page_impact_analysis(conn)
    elif page == "Admin":
        page_admin(conn, role)


if __name__ == "__main__":
    # Streamlit ignores this when run via `streamlit run`, but it makes
    # the module importable and testable by calling main() in tests.
    main()
