import logging
import time

import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError

from servicepilot.ai import AIOutputError, AIUnavailable, BedrockTriage
from servicepilot.auth import (
    LoginLimiter,
    check_admin_password,
    session_expired,
    uses_legacy_password,
)
from servicepilot.config import boto_session, load_settings
from servicepilot.models import PRIORITIES, SERVICE_TYPES, STATUSES, TRANSITIONS
from servicepilot.stats import SORT_OPTIONS, compute_stats, filter_tickets, paginate, sort_tickets
from servicepilot.store import InvalidTransition, TicketConflict, TicketStore

logger = logging.getLogger("servicepilot.admin")
settings = load_settings()

st.set_page_config(
    page_title="Admin Panel",
    page_icon="🛠️",
    layout="wide",
)

st.title("🛠️ Admin Panel")

STATUS_BADGE = {"Open": "🟢 Open", "In Progress": "🟡 In Progress", "Resolved": "⚪ Resolved"}
PRIORITY_BADGE = {
    "Low": "🔵 Low",
    "Medium": "🟠 Medium",
    "High": "🔴 High",
    "Emergency": "🚨 Emergency",
}
SESSION_TIMEOUT = 1800  # seconds of inactivity


# -----------------------------------
# AUTHENTICATION
# -----------------------------------

@st.cache_resource
def get_limiter():
    # Shared by all sessions of this server process, so opening a new browser
    # tab does not reset the failure count.
    return LoginLimiter()


def admin_secrets():
    try:
        return dict(st.secrets.get("admin", {}))
    except Exception:  # no secrets.toml
        return {}


def logout():
    st.session_state.authenticated = False
    st.session_state.pop("last_active", None)


if st.session_state.get("authenticated") and session_expired(
    st.session_state.get("last_active"), time.time(), SESSION_TIMEOUT
):
    logout()
    st.warning("Your session expired. Please log in again.")

if not st.session_state.get("authenticated"):
    secrets = admin_secrets()
    limiter = get_limiter()

    if not (secrets.get("password_hash") or secrets.get("password")):
        st.error(
            "Admin login is not configured. Add `[admin] password_hash` to "
            "`.streamlit/secrets.toml` (see README)."
        )
        st.stop()

    locked = limiter.seconds_locked()
    if locked:
        st.error(f"Too many failed attempts. Try again in about {locked} seconds.")
        st.stop()

    with st.form("login"):
        pwd = st.text_input("Admin Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if check_admin_password(pwd, secrets):
            limiter.record_success()
            st.session_state.authenticated = True
            st.session_state.last_active = time.time()
            logger.info("admin login succeeded")
            st.rerun()
        else:
            limiter.record_failure()
            logger.warning("admin login failed")
            st.error("Incorrect password.")
    st.stop()

st.session_state.last_active = time.time()


# -----------------------------------
# DYNAMODB CONNECTION
# -----------------------------------

@st.cache_resource
def get_store(region: str, table_name: str, profile):
    session = boto_session(settings)
    return TicketStore(session.resource("dynamodb").Table(table_name))


@st.cache_data(ttl=30, show_spinner="Loading tickets...")
def load_tickets(region: str, table_name: str, profile):
    return get_store(region, table_name, profile).list_tickets()


def show_aws_error(error):
    logger.error("AWS error: %s", type(error).__name__)
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "Unknown")
        st.error(
            f"AWS error: {code}. Check the region, table name and IAM permissions "
            "shown in the sidebar."
        )
    elif isinstance(error, BotoCoreError):
        st.error(
            "Could not use your AWS credentials or reach AWS. Check the profile "
            "and credentials shown in the sidebar."
        )
    else:
        st.error("Unexpected error while talking to AWS.")


with st.sidebar:
    st.subheader("Connection")
    for label, value in settings.describe().items():
        st.caption(f"**{label}:** {value}")
    if st.button("🔄 Refresh data"):
        load_tickets.clear()
        st.rerun()
    if st.button("Logout"):
        logout()
        st.rerun()

if uses_legacy_password(admin_secrets()):
    st.warning(
        "Admin password is stored in plain text in secrets. "
        "Run `python scripts/hash_password.py` and use `password_hash` instead."
    )

args = (settings.region, settings.table_name, settings.profile)
store = get_store(*args)

try:
    all_tickets = load_tickets(*args)
except Exception as error:
    show_aws_error(error)
    st.stop()


# -----------------------------------
# DASHBOARD STATISTICS
# -----------------------------------

stats = compute_stats(all_tickets)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total", stats["total"])
col2.metric("Open", stats["by_status"]["Open"])
col3.metric("In Progress", stats["by_status"]["In Progress"])
col4.metric("Resolved", stats["by_status"]["Resolved"])
col5.metric("Urgent & unresolved", stats["urgent_open"])

if all_tickets:
    ch1, ch2, ch3 = st.columns(3)
    ch1.caption("By status")
    ch1.bar_chart(stats["by_status"])
    ch2.caption("By priority")
    ch2.bar_chart(stats["by_priority"])
    ch3.caption("By service")
    ch3.bar_chart(stats["by_service"])

st.divider()


# -----------------------------------
# FILTERS
# -----------------------------------

query = st.text_input(
    "Search", placeholder="Ticket ID, customer, email or description"
)
col_s, col_p, col_sv, col_o = st.columns(4)

status_filter = col_s.selectbox("Status", ["All", *STATUSES])
priority_filter = col_p.selectbox("Priority", ["All", *reversed(PRIORITIES)])
service_filter = col_sv.selectbox("Service", ["All", *SERVICE_TYPES])
sort_choice = col_o.selectbox("Sort by", list(SORT_OPTIONS))

tickets = sort_tickets(
    filter_tickets(
        all_tickets,
        status=status_filter,
        priority=priority_filter,
        service=service_filter,
        query=query,
    ),
    sort_choice,
)

st.subheader(f"Tickets ({len(tickets)} of {len(all_tickets)})")

page_size = st.select_slider("Per page", options=[5, 10, 25, 50], value=10)
_, _, total_pages = paginate(tickets, 1, page_size)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
page_items, page, total_pages = paginate(tickets, int(page), page_size)
st.caption(f"Page {page} of {total_pages}")


# -----------------------------------
# AI (optional)
# -----------------------------------

@st.cache_resource
def get_triage():
    return BedrockTriage(settings)


def render_ai(ticket):
    key = f"ai_{ticket['ticket_id']}_{ticket['updated_at']}"
    if st.button("✨ Get AI suggestions", key=f"btn_{key}"):
        try:
            with st.spinner("Asking the AI model..."):
                st.session_state[key] = get_triage().triage(ticket)
        except (AIUnavailable, AIOutputError) as err:
            logger.warning("AI triage failed: %s", type(err).__name__)
            st.session_state[key] = None
            st.warning("AI suggestions are unavailable right now. Triage manually.")
    result = st.session_state.get(key)
    if result:
        st.info(
            "AI-generated suggestions: not verified. Review before acting; "
            "nothing here has been applied to the ticket."
        )
        if result.urgent:
            st.error("AI flagged a possible safety risk. Verify with the customer.")
        st.write(f"**Summary:** {result.summary}")
        st.write(
            f"**Suggested category / priority:** {result.suggested_category} / "
            f"{result.suggested_priority}"
        )
        if result.troubleshooting_steps:
            st.write("**Troubleshooting ideas:**")
            for step in result.troubleshooting_steps:
                st.text(f"• {step}")
        if result.draft_reply:
            st.text_area("Draft reply (edit before sending)", result.draft_reply,
                         key=f"{key}_reply")


# -----------------------------------
# TICKET MANAGEMENT
# -----------------------------------

if not all_tickets:
    st.info("No tickets yet. New requests from the customer form will appear here.")
elif not tickets:
    st.info("No tickets match the selected filters.")
else:
    for ticket in page_items:
        tid = ticket["ticket_id"]
        status = ticket["status"]
        priority = ticket["priority"]

        label = (
            f"{STATUS_BADGE[status]} · {PRIORITY_BADGE[priority]} · "
            f"{ticket['service_type']} · {tid}"
        )
        with st.expander(label):
            st.text(f"Customer: {ticket['customer_name']}")
            st.text(f"Email: {ticket['email'] or '(none)'}")
            st.text(f"Created: {ticket['created_at'] or 'unknown'}")
            st.text(f"Updated: {ticket['updated_at'] or 'unknown'}")
            st.caption("Problem")
            st.text(ticket["description"])

            if ticket["history"]:
                with st.popover("History"):
                    for entry in reversed(ticket["history"]):
                        st.text(
                            f"{entry.get('at', '')}  {entry.get('from_status', '')} → "
                            f"{entry.get('status', '')}, priority {entry.get('priority', '')}"
                        )

            st.divider()

            allowed_status = [status, *sorted(TRANSITIONS[status])]
            with st.form(f"edit_{tid}"):
                c1, c2 = st.columns(2)
                new_status = c1.selectbox("Status", allowed_status)
                new_priority = c2.selectbox(
                    "Priority", PRIORITIES, index=PRIORITIES.index(priority)
                )
                save = st.form_submit_button("Update")

            if save:
                try:
                    store.update(
                        tid,
                        status=new_status,
                        priority=new_priority,
                        expected_version=ticket["version"],
                        current_status=status,
                    )
                except TicketConflict:
                    load_tickets.clear()
                    st.error(
                        "This ticket was changed or deleted by someone else. "
                        "Data has been refreshed; please review and retry."
                    )
                except InvalidTransition:
                    st.error("That status change is not allowed.")
                except Exception as error:
                    show_aws_error(error)
                else:
                    load_tickets.clear()
                    st.rerun()

            if settings.ai_enabled:
                render_ai(ticket)

            with st.popover("🗑️ Delete ticket"):
                st.warning(f"Permanently delete {tid}? This cannot be undone.")
                if st.button("Yes, delete", key=f"delete_{tid}", type="primary"):
                    try:
                        store.delete(tid)
                    except Exception as error:
                        show_aws_error(error)
                    else:
                        load_tickets.clear()
                        st.rerun()


# -----------------------------------
# DANGER ZONE
# -----------------------------------

st.divider()

with st.expander("⚠️ Danger Zone"):
    st.warning("This will permanently delete every ticket in DynamoDB.")
    confirm = st.text_input("Type DELETE ALL to confirm")
    if st.button(
        "Delete All Tickets",
        type="primary",
        disabled=confirm != "DELETE ALL" or not all_tickets,
    ):
        try:
            count = store.delete_all([t["ticket_id"] for t in store.list_tickets()])
        except Exception as error:
            show_aws_error(error)
        else:
            logger.warning("admin deleted all tickets (%d)", count)
            load_tickets.clear()
            st.rerun()
