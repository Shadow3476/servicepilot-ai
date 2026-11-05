import streamlit as st

from servicepilot.client import ApiError, fingerprint, submit_ticket
from servicepilot.config import load_settings
from servicepilot.models import (
    MAX_DESCRIPTION,
    PRIORITIES,
    SERVICE_TYPES,
    ValidationError,
    validate_ticket_input,
)

settings = load_settings()

st.set_page_config(
    page_title="ServicePilot AI",
    page_icon="🔧"
)

st.title("🔧 ServicePilot AI")
st.write("Submit a service request and we will get back to you.")

# Fingerprints of tickets already created in this browser session, so a
# double click or page re-run does not create the same ticket twice.
submitted = st.session_state.setdefault("submitted", {})

# Preserve form inputs in session state across refreshes
st.session_state.setdefault("form_customer_name", "")
st.session_state.setdefault("form_email", "")
st.session_state.setdefault("form_service_type", SERVICE_TYPES[0])
st.session_state.setdefault("form_priority", PRIORITIES[1])
st.session_state.setdefault("form_description", "")

with st.form("service_request"):
    customer_name = st.text_input(
        "Customer Name",
        max_chars=100,
        value=st.session_state.form_customer_name,
        key="form_customer_name"
    )
    email = st.text_input(
        "Email (optional)",
        max_chars=254,
        value=st.session_state.form_email,
        key="form_email"
    )

    col_a, col_b = st.columns(2)
    service_type = col_a.selectbox(
        "Service Type",
        SERVICE_TYPES,
        index=SERVICE_TYPES.index(st.session_state.form_service_type),
        key="form_service_type"
    )
    priority = col_b.selectbox(
        "Priority",
        PRIORITIES,
        index=PRIORITIES.index(st.session_state.form_priority),
        key="form_priority"
    )

    description = st.text_area(
        "Describe the problem",
        max_chars=MAX_DESCRIPTION,
        help="What is happening, where, and since when?",
        value=st.session_state.form_description,
        key="form_description"
    )
    send = st.form_submit_button("Submit Service Request", type="primary")

if send:
    try:
        payload = validate_ticket_input(
            {
                "customer_name": customer_name,
                "email": email,
                "service_type": service_type,
                "priority": priority,
                "description": description,
            }
        )
    except ValidationError as err:
        for message in err.errors:
            st.error(message)
    else:
        key = fingerprint(payload)
        if key in submitted:
            st.info("This request was already submitted.")
            st.write(f"### Ticket Number: `{submitted[key]}`")
        else:
            try:
                with st.spinner("Submitting..."):
                    ticket_id = submit_ticket(settings.api_url, payload)
            except ApiError as err:
                st.error(str(err))
            else:
                submitted[key] = ticket_id
                # Clear form fields after successful submission
                st.session_state.form_customer_name = ""
                st.session_state.form_email = ""
                st.session_state.form_service_type = SERVICE_TYPES[0]
                st.session_state.form_priority = PRIORITIES[1]
                st.session_state.form_description = ""
                st.success("Service request submitted!")
                st.write(f"### Ticket Number: `{ticket_id}`")
                st.write("Save this ticket number for your records.")
