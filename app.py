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

with st.form("service_request"):
    customer_name = st.text_input("Customer Name", max_chars=100)
    email = st.text_input("Email (optional)", max_chars=254)

    col_a, col_b = st.columns(2)
    service_type = col_a.selectbox("Service Type", SERVICE_TYPES)
    priority = col_b.selectbox("Priority", PRIORITIES, index=1)

    description = st.text_area(
        "Describe the problem",
        max_chars=MAX_DESCRIPTION,
        help="What is happening, where, and since when?",
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
                st.success("Service request submitted!")
                st.write(f"### Ticket Number: `{ticket_id}`")
                st.write("Save this ticket number for your records.")
