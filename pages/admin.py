
import streamlit as st
import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
)

st.set_page_config(
    page_title="Admin Panel",
    page_icon="🛠️",
    layout="wide",
)

st.title("🛠️ Admin Panel")

# -----------------------------------
# AUTHENTICATION
# -----------------------------------

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pwd = st.text_input("Admin Password", type="password")

    if st.button("Login"):
        if pwd == st.secrets["admin"]["password"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


# -----------------------------------
# DYNAMODB CONNECTION
# -----------------------------------

@st.cache_resource
def get_table():
    dynamodb = boto3.resource(
        "dynamodb",
        region_name="us-west-1",
    )
    return dynamodb.Table("ServicePilotTickets")


table = get_table()


def get_all_tickets():
    tickets = []
    scan_args = {}

    while True:
        response = table.scan(**scan_args)
        tickets.extend(response.get("Items", []))

        if "LastEvaluatedKey" not in response:
            break

        scan_args["ExclusiveStartKey"] = response[
            "LastEvaluatedKey"
        ]

    tickets.sort(
        key=lambda ticket: ticket.get("created_at", ""),
        reverse=True,
    )

    return tickets


def show_aws_error(error):
    if isinstance(
        error,
        (NoCredentialsError, PartialCredentialsError),
    ):
        st.error(
            "AWS credentials are missing or incomplete. "
            "Configure your local AWS credentials first."
        )
    elif isinstance(error, ClientError):
        details = error.response.get("Error", {})
        st.error(
            f"AWS error: {details.get('Code', 'Unknown')} — "
            f"{details.get('Message', 'No details provided')}"
        )
    else:
        st.error(f"Unexpected error: {error}")


try:
    all_tickets = get_all_tickets()
except Exception as error:
    show_aws_error(error)
    st.stop()


# -----------------------------------
# DASHBOARD STATISTICS
# -----------------------------------

total = len(all_tickets)

open_t = sum(
    ticket.get("status", "Open") == "Open"
    for ticket in all_tickets
)

prog_t = sum(
    ticket.get("status", "Open") == "In Progress"
    for ticket in all_tickets
)

done_t = sum(
    ticket.get("status", "Open") == "Completed"
    for ticket in all_tickets
)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total", total)
col2.metric("Open", open_t)
col3.metric("In Progress", prog_t)
col4.metric("Completed", done_t)

st.divider()


# -----------------------------------
# FILTERS
# -----------------------------------

col_s, col_p, col_sv = st.columns(3)

status_filter = col_s.selectbox(
    "Filter by Status",
    ["All", "Open", "In Progress", "Completed"],
)

priority_filter = col_p.selectbox(
    "Filter by Priority",
    ["All", "Emergency", "High", "Medium", "Low"],
)

service_filter = col_sv.selectbox(
    "Filter by Service",
    ["All", "HVAC", "Plumbing", "Electrical", "Appliance", "Other"],
)


tickets = [
    ticket
    for ticket in all_tickets
    if (
        status_filter == "All"
        or ticket.get("status", "Open") == status_filter
    )
    and (
        priority_filter == "All"
        or ticket.get("priority", "Medium") == priority_filter
    )
    and (
        service_filter == "All"
        or ticket.get("service_type", "Other") == service_filter
    )
]

st.subheader(f"Tickets ({len(tickets)})")


# -----------------------------------
# TICKET MANAGEMENT
# -----------------------------------

if not tickets:
    st.info("No tickets match the selected filters.")

else:
    for ticket in tickets:
        tid = ticket["ticket_id"]
        customer = ticket.get("customer_name", "")
        email = ticket.get("email", "")
        service = ticket.get("service_type", "Other")
        problem = ticket.get("description", "")
        status = ticket.get("status", "Open")
        priority = ticket.get("priority", "Medium")

        with st.expander(
            f"{tid} | {service} | {priority} | {status}"
        ):
            st.write(f"**Customer:** {customer}")
            st.write(f"**Email:** {email}")
            st.write(f"**Problem:** {problem}")

            st.divider()

            cols = st.columns(3)

            new_status = cols[0].selectbox(
                "Status",
                ["Open", "In Progress", "Completed"],
                index=(
                    ["Open", "In Progress", "Completed"].index(status)
                    if status in ["Open", "In Progress", "Completed"]
                    else 0
                ),
                key=f"status_{tid}",
            )

            new_priority = cols[1].selectbox(
                "Priority",
                ["Low", "Medium", "High", "Emergency"],
                index=(
                    ["Low", "Medium", "High", "Emergency"].index(priority)
                    if priority in ["Low", "Medium", "High", "Emergency"]
                    else 1
                ),
                key=f"priority_{tid}",
            )

            with cols[2]:
                st.write("")
                st.write("")

                if st.button("Update", key=f"update_{tid}"):
                    try:
                        table.update_item(
                            Key={"ticket_id": tid},
                            UpdateExpression=(
                                "SET #status = :status, priority = :priority"
                            ),
                            ExpressionAttributeNames={
                                "#status": "status"
                            },
                            ExpressionAttributeValues={
                                ":status": new_status,
                                ":priority": new_priority,
                            },
                        )

                        st.success("Ticket updated.")
                        st.rerun()

                    except Exception as error:
                        show_aws_error(error)

            if st.button(
                "🗑️ Delete Ticket",
                key=f"delete_{tid}",
            ):
                try:
                    table.delete_item(
                        Key={"ticket_id": tid}
                    )
                    st.success("Ticket deleted.")
                    st.rerun()

                except Exception as error:
                    show_aws_error(error)


# -----------------------------------
# DANGER ZONE
# -----------------------------------

st.divider()

with st.expander("⚠️ Danger Zone"):
    st.warning(
        "This will permanently delete every ticket in DynamoDB."
    )

    if st.button(
        "Delete All Tickets",
        type="primary",
        disabled=not all_tickets,
    ):
        try:
            with table.batch_writer() as batch:
                for ticket in all_tickets:
                    batch.delete_item(
                        Key={"ticket_id": ticket["ticket_id"]}
                    )

            st.success("All tickets deleted.")
            st.rerun()

        except Exception as error:
            show_aws_error(error)


# -----------------------------------
# LOGOUT
# -----------------------------------

if st.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()
