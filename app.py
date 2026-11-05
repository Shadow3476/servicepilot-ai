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

# Client-side sessionStorage persistence (survives browser refresh)
st.markdown("""
<script>
(function() {
    const STORAGE_KEY = 'servicepilot_ticket_draft_v1';
    const FIELDS = {
        'customer_name': 'Customer Name',
        'email': 'Email (optional)',
        'service_type': 'Service Type',
        'priority': 'Priority',
        'description': 'Describe the problem'
    };

    // Restore from sessionStorage BEFORE form renders
    function restoreDraft() {
        try {
            const saved = sessionStorage.getItem(STORAGE_KEY);
            if (saved) {
                window.__servicepilot_draft = JSON.parse(saved);
            }
        } catch (e) {
            console.warn('Failed to restore draft:', e);
        }
    }

    // Save to sessionStorage on every input event (with debounce)
    let saveTimeout;
    function saveDraft() {
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
            try {
                const inputs = document.querySelectorAll('input[type="text"], textarea, select');
                const draft = {};
                let count = 0;

                // Map visible inputs to field names
                inputs.forEach(input => {
                    if (input.value && count < 5) {
                        const label = input.previousElementSibling?.textContent ||
                                    input.parentElement?.textContent || '';

                        // Match field by value content or nearby label
                        if (label.includes('Customer') || input.placeholder?.includes('Customer')) {
                            draft['customer_name'] = input.value;
                        } else if (label.includes('Email') || input.placeholder?.includes('Email')) {
                            draft['email'] = input.value;
                        } else if (label.includes('Describe') || input.placeholder?.includes('problem')) {
                            draft['description'] = input.value;
                        }
                        count++;
                    }
                });

                // Get selectbox values (Service Type, Priority)
                const selects = document.querySelectorAll('[role="combobox"], select');
                let selectCount = 0;
                selects.forEach(select => {
                    const value = select.value || select.textContent?.trim();
                    if (value && selectCount === 0) {
                        draft['service_type'] = value;
                        selectCount++;
                    } else if (value && selectCount === 1) {
                        draft['priority'] = value;
                    }
                });

                if (Object.keys(draft).length > 0) {
                    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
                }
            } catch (e) {
                console.warn('Failed to save draft:', e);
            }
        }, 300); // Debounce 300ms
    }

    // Clear draft after successful submission
    window.clearTicketDraft = function() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch (e) {
            console.warn('Failed to clear draft:', e);
        }
    };

    // Listen for input changes
    document.addEventListener('input', saveDraft, true);
    document.addEventListener('change', saveDraft, true);

    // Restore on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', restoreDraft);
    } else {
        restoreDraft();
    }
})();
</script>
""", unsafe_allow_html=True)

# Fingerprints of tickets already created in this browser session, so a
# double click or page re-run does not create the same ticket twice.
submitted = st.session_state.setdefault("submitted", {})

# Get saved draft from sessionStorage via JavaScript (if available)
try:
    saved_draft = st.session_state.get("_saved_draft", {})
except:
    saved_draft = {}

# Initialize form state with saved values
st.session_state.setdefault("form_customer_name", saved_draft.get("customer_name", ""))
st.session_state.setdefault("form_email", saved_draft.get("email", ""))
st.session_state.setdefault("form_service_type", saved_draft.get("service_type", SERVICE_TYPES[0]))
st.session_state.setdefault("form_priority", saved_draft.get("priority", PRIORITIES[1]))
st.session_state.setdefault("form_description", saved_draft.get("description", ""))

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

# Auto-save form state to sessionStorage whenever it changes
_draft = {
    "customer_name": customer_name,
    "email": email,
    "service_type": service_type,
    "priority": priority,
    "description": description,
}

st.markdown(f"""
<script>
sessionStorage.setItem('servicepilot_ticket_draft_v1', {repr(_draft).replace("'", '"')});
</script>
""", unsafe_allow_html=True)

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
                # Clear sessionStorage
                st.markdown("""
                <script>
                sessionStorage.removeItem('servicepilot_ticket_draft_v1');
                </script>
                """, unsafe_allow_html=True)
                st.success("Service request submitted!")
                st.write(f"### Ticket Number: `{ticket_id}`")
                st.write("Save this ticket number for your records.")
