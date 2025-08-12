# ABS Project Intake Portal (Streamlit MVP)
# Author: ChatGPT for Rishikesh (ABS)
# Run with: streamlit run app.py
# Requirements: streamlit>=1.26

import os
import sqlite3
from datetime import datetime

import streamlit as st

DB_PATH = "tickets.db"
MANAGER_NAME = "Ruben"
DEFAULT_PIN = "1234"  # Change this or set env var MANAGER_PIN / secrets.toml

# Reviewer (you)
REVIEWER_NAME = "Rishi"
DEFAULT_REVIEWER_PIN = "2468"  # Change this or set env var RISHI_PIN / secrets.toml

# -----------------------------
# DB utilities
# -----------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            project_name TEXT NOT NULL,
            department TEXT,
            requester_name TEXT,
            requester_email TEXT,
            description TEXT,
            priority TEXT,
            impact TEXT,
            due_date TEXT,
            attachments TEXT,
            status TEXT NOT NULL DEFAULT 'Submitted',
            manager_comment TEXT
        );
        """
    )
    conn.commit()

    # --- lightweight migrations for new columns ---
    def add_col(name, ddl):
        cols = [r[1] for r in cur.execute("PRAGMA table_info(tickets)").fetchall()]
        if name not in cols:
            cur.execute(f"ALTER TABLE tickets ADD COLUMN {name} {ddl}")
            conn.commit()

    add_col("estimate_hours", "REAL")            # reviewer estimate
    add_col("estimate_notes", "TEXT")             # reviewer notes
    add_col("triaged_by", "TEXT")                 # who triaged
    add_col("triaged_at", "TEXT")                 # when triaged

    return conn


conn = init_db()

# -----------------------------
# Helpers
# -----------------------------

PRIORITY_OPTIONS = ["Critical", "High", "Medium", "Low"]
IMPACT_OPTIONS = [
    "Revenue / Sales", "Customer-facing", "Compliance / Risk", "Operational Efficiency",
    "Internal Productivity", "Data Quality", "Other"
]
DEPTS = [
    "Sales", "Engineering", "Supply Chain", "Finance", "Operations", "IT", "Marketing", "HR", "Other"
]
STATUS_OPTIONS = [
    "Submitted",
    "Pending Manager Approval",
    "Approved", "Denied", "On Hold", "In Progress", "Done"
]


def submit_ticket(payload: dict):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tickets (
            created_at, project_name, department, requester_name, requester_email,
            description, priority, impact, due_date, attachments, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(),
            payload.get("project_name"),
            payload.get("department"),
            payload.get("requester_name"),
            payload.get("requester_email"),
            payload.get("description"),
            payload.get("priority"),
            payload.get("impact"),
            payload.get("due_date"),
            payload.get("attachments"),
            "Submitted",
        ),
    )
    conn.commit()


def list_tickets(status_filter=None, dept_filter=None, search=None):
    q = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if status_filter and status_filter != "(all)":
        q += " AND status = ?"
        params.append(status_filter)
    if dept_filter and dept_filter != "(all)":
        q += " AND department = ?"
        params.append(dept_filter)
    if search:
        q += " AND (project_name LIKE ? OR description LIKE ? OR requester_name LIKE ? OR requester_email LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like, like])
    q += (
        " ORDER BY CASE priority "
        "WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END, "
        "datetime(created_at) ASC"
    )
    cur = conn.cursor()
    rows = cur.execute(q, params).fetchall()
    return rows


def update_status(ticket_id: int, new_status: str, comment: str | None = None):
    cur = conn.cursor()
    if comment is not None:
        cur.execute("UPDATE tickets SET status = ?, manager_comment = ? WHERE id = ?", (new_status, comment, ticket_id))
    else:
        cur.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
    conn.commit()


def set_triage(ticket_id: int, hours: float | None, notes: str | None, triager: str):
    cur = conn.cursor()
    cur.execute(
        "UPDATE tickets SET estimate_hours = ?, estimate_notes = ?, triaged_by = ?, triaged_at = ?, status = ? WHERE id = ?",
        (hours, notes, triager, datetime.utcnow().isoformat(), "Pending Manager Approval", ticket_id),
    )
    conn.commit()

# -----------------------------
# UI
# -----------------------------

st.set_page_config(page_title="ABS Project Intake", page_icon="🧭", layout="wide")

st.title("🧭 ABS Project Intake Portal")
_ = st.markdown("Collect, triage, and approve project requests across departments.")

with st.sidebar:
    st.header("Navigation")
    view = st.radio("Choose a view", ["Submit a Request", "My Triage", "Manager Dashboard"], index=0)
    st.markdown("---")
    st.caption("This is an internal MVP. Data is stored locally in SQLite (tickets.db). For prod, swap to SQL Server/SharePoint/Dataverse.")

if view == "Submit a Request":
    st.subheader("Submit a New Project Request")
    with st.form("project_form", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        project_name = c1.text_input("Project name *")
        department = c2.selectbox("Department", DEPTS)

        c3, c4 = st.columns(2)
        requester_name = c3.text_input("Your name *")
        requester_email = c4.text_input("Your email *")

        description = st.text_area("Description *", height=160, placeholder="What problem are we solving? Scope, stakeholders, systems involved…")

        c5, c6, c7 = st.columns(3)
        priority = c5.selectbox("Priority *", PRIORITY_OPTIONS, index=2)
        impact = c6.selectbox("Primary impact", IMPACT_OPTIONS, index=3)
        due_date = c7.date_input("Requested due date", value=None, format="YYYY-MM-DD")

        attachments = st.text_input("Links (Figma, Excel, specs, tickets)")

        submitted = st.form_submit_button("Submit to Rishi ➜", use_container_width=True)

        if submitted:
            required = [project_name, requester_name, requester_email, description]
            if any(not x for x in required):
                st.error("Please fill all required fields marked with *.")
            else:
                payload = {
                    "project_name": project_name.strip(),
                    "department": department,
                    "requester_name": requester_name.strip(),
                    "requester_email": requester_email.strip(),
                    "description": description.strip(),
                    "priority": priority,
                    "impact": impact,
                    "due_date": due_date.isoformat() if due_date else None,
                    "attachments": attachments.strip() if attachments else None,
                }
                submit_ticket(payload)
                st.success("Request submitted! Rishi has been notified.")
                st.info("You’ll receive an update once it’s reviewed.")

elif view == "My Triage":
    st.subheader("My Triage (Add Estimates & Forward)")

    # Reviewer PIN auth with session persistence
    rishi_pin_source = os.getenv("RISHI_PIN") or DEFAULT_REVIEWER_PIN
    try:
        _ = st.secrets  # may raise if no secrets file
        rishi_pin_source = st.secrets.get("RISHI_PIN", rishi_pin_source)
    except Exception:
        pass

    if "reviewer_unlocked" not in st.session_state:
        st.session_state["reviewer_unlocked"] = False

    with st.expander("Sign in (Reviewer PIN)", expanded=not st.session_state["reviewer_unlocked"]):
        rpin = st.text_input("Enter reviewer PIN", type="password", key="reviewer_pin")
        if st.button("Unlock (Reviewer)"):
            if rpin == rishi_pin_source:
                st.session_state["reviewer_unlocked"] = True
                st.success(f"Welcome, {REVIEWER_NAME}!")
                st.rerun()
            else:
                st.error("Invalid PIN. Please try again.")

    if not st.session_state["reviewer_unlocked"]:
        st.stop()

    rows = list_tickets(status_filter="Submitted")
    st.caption(f"{len(rows)} request(s) awaiting triage")

    for r in rows:
        with st.container(border=True):
            st.markdown(f"**#{r['id']} — {r['project_name']}** · {r['department']}")
            st.write(r["description"])  # details
            c1, c2 = st.columns([2, 2])
            est_hours = c1.number_input(f"Estimated effort (hours) for #{r['id']}", min_value=0.0, step=0.5, key=f"eh_{r['id']}")
            est_notes = c2.text_input(f"Notes (#{r['id']})", key=f"en_{r['id']}")
            if st.button("Send to Manager for Approval", key=f"to_mgr_{r['id']}"):
                set_triage(r["id"], est_hours, est_notes, REVIEWER_NAME)
                st.success(f"Ticket #{r['id']} forwarded to {MANAGER_NAME}.")
                st.rerun()

else:
    st.subheader("Manager Dashboard")

    # Simple auth (PIN). Replace with SSO in production.
    pin_source = os.getenv("MANAGER_PIN") or DEFAULT_PIN
    try:
        _ = st.secrets
        pin_source = st.secrets.get("MANAGER_PIN", pin_source)
    except Exception:
        pass

    if "manager_unlocked" not in st.session_state:
        st.session_state["manager_unlocked"] = False

    with st.expander("Sign in (Manager PIN)", expanded=not st.session_state["manager_unlocked"]):
        pin = st.text_input("Enter manager PIN", type="password", key="manager_pin")
        if st.button("Unlock", key="unlock_manager"):
            if pin == pin_source:
                st.session_state["manager_unlocked"] = True
                st.success(f"Welcome, {MANAGER_NAME}!")
                st.rerun()
            else:
                st.error("Invalid PIN. Please try again.")

    if not st.session_state["manager_unlocked"]:
        st.stop()

    # Filters
    f1, f2, f3 = st.columns([2, 2, 2])
    default_idx = (["(all)"] + STATUS_OPTIONS).index("Pending Manager Approval") if "Pending Manager Approval" in STATUS_OPTIONS else 0
    status_filter = f1.selectbox("Status", ["(all)"] + STATUS_OPTIONS, index=default_idx)
    dept_filter = f2.selectbox("Department", ["(all)"] + DEPTS, index=0)
    search = f3.text_input("Search (name, description, requester, email)")

    rows = list_tickets(status_filter=status_filter, dept_filter=dept_filter, search=search)

    st.caption(f"{len(rows)} request(s) shown")

    for r in rows:
        with st.container(border=True):
            top = st.columns([6, 2, 2, 2])
            with top[0]:
                st.markdown(f"**#{r['id']} — {r['project_name']}**")
                st.caption(f"{r['department']} • submitted {r['created_at']}")
            with top[1]:
                st.markdown(f"Priority: **{r['priority']}**")
            with top[2]:
                st.markdown(f"Status: **{r['status']}**")
            with top[3]:
                st.markdown(f"Due: **{r['due_date'] or '—'}**")

            st.write(r["description"])  # long text

            # Show reviewer estimate if available (sqlite Row-safe)
            row_keys = r.keys() if hasattr(r, "keys") else []
            eh = r["estimate_hours"] if "estimate_hours" in row_keys else None
            en = r["estimate_notes"] if "estimate_notes" in row_keys else None
            tb = r["triaged_by"] if "triaged_by" in row_keys else None
            if eh is not None or (en and len(str(en)) > 0):
                st.info(
                    f"Reviewer estimate: {eh if eh is not None else '—'} h  •  "
                    f"Notes: {en or '—'}  •  By: {tb or '—'}"
                )

            meta1, meta2, meta3 = st.columns([3, 3, 6])
            meta1.caption(f"Requester: {r['requester_name']}")
            meta2.caption(f"Email: {r['requester_email']}")
            meta3.caption(f"Links: {r['attachments'] or '—'}")

            cA, cB, cC, cD = st.columns([2, 2, 2, 6])
            with cD:
                mgr_comment = st.text_input(
                    f"Manager comment (#{r['id']})",
                    value=r["manager_comment"] or "",
                    key=f"mc_{r['id']}"
                )
            with cA:
                if st.button("Approve", key=f"ap_{r['id']}"):
                    update_status(r["id"], "Approved", st.session_state.get(f"mc_{r['id']}") or None)
                    st.success(f"Ticket #{r['id']} approved.")
                    st.rerun()
            with cB:
                if st.button("Deny", key=f"dn_{r['id']}"):
                    update_status(r["id"], "Denied", st.session_state.get(f"mc_{r['id']}") or None)
                    st.warning(f"Ticket #{r['id']} denied.")
                    st.rerun()
            with cC:
                if st.button("On Hold", key=f"oh_{r['id']}"):
                    update_status(r["id"], "On Hold", st.session_state.get(f"mc_{r['id']}") or None)
                    st.info(f"Ticket #{r['id']} on hold.")
                    st.rerun()

    st.markdown("---")
    st.caption("Export")
    if st.button("Download CSV of all tickets"):
        import pandas as pd
        df = pd.read_sql_query("SELECT * FROM tickets ORDER BY id DESC", conn)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Save tickets.csv", data=csv, file_name="tickets.csv", mime="text/csv")

    st.caption("Tip: For production, integrate with Power Automate Approvals, SharePoint or Dataverse, and Azure AD for SSO.")
