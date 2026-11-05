import streamlit as st
import requests

API_URL = "https://4mps7hcgi7.execute-api.us-west-1.amazonaws.com/tickets"

st.set_page_config(
    page_title="ServicePilot AI",
    page_icon="🔧"
)

st.title("🔧 ServicePilot AI")
st.write("Submit a service request.")

customer_name = st.text_input("Customer Name")
email = st.text_input("Email")

service_type = st.selectbox(
    "Service Type",
    [
        "HVAC",
        "Plumbing",
        "Electrical",
        "Appliance",
        "Other"
    ]
)

priority = st.selectbox(
    "Priority",
    [
        "Low",
        "Medium",
        "High",
        "Emergency"
    ]
)

description = st.text_area("Describe the problem")

if st.button("Submit Service Request", type="primary"):

    if not customer_name:
        st.error("Please enter your name.")

    elif not description:
        st.error("Please describe the problem.")

    else:

        ticket_data = {
            "customer_name": customer_name,
            "email": email,
            "service_type": service_type,
            "description": description,
            "priority": priority
        }

        try:
            response = requests.post(
                API_URL,
                json=ticket_data,
                timeout=10
            )

            if response.status_code == 201:
                result = response.json()

                st.success("Service request submitted!")

                st.write(
                    f"### Ticket Number: `{result['ticket_id']}`"
                )

                st.write(
                    "Save this ticket number for your records."
                )

            else:
                st.error(
                    f"Something went wrong. "
                    f"Status code: {response.status_code}"
                )

        except requests.exceptions.RequestException as e:
            st.error(f"Could not connect to ServicePilot API: {e}")