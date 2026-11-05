# ServicePilot AI

Streamlit app for submitting and managing service requests.

- `app.py` – customer form; posts tickets to an AWS API Gateway endpoint.
- `pages/admin.py` – password-protected admin panel backed by DynamoDB (`ServicePilotTickets`, us-west-1).

## Run

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # set your admin password
streamlit run app.py
```

The admin page needs local AWS credentials with access to the DynamoDB table.
