"""Gmail API service and failure notifications."""

import os
import json

from config import storage_client, BUCKET_NAME


def get_gmail_service():
    """Load Gmail OAuth token from GCS and return an authenticated Gmail API service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    blob = storage_client.bucket(BUCKET_NAME).blob("config/gmail_token.json")
    token_data = json.loads(blob.download_as_string())

    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_data.update({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
        })
        blob.upload_from_string(json.dumps(token_data), content_type="application/json")

    return build("gmail", "v1", credentials=creds)


def send_failure_notification(subject, body):
    """Send a failure alert email via Gmail API. Silently skips if not configured."""
    import base64
    from email.mime.text import MIMEText

    email = os.environ.get("NOTIFY_EMAIL")
    if not email:
        return

    try:
        service = get_gmail_service()
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email
        msg["To"] = email
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"Failure notification sent to {email}")
    except Exception as e:
        print(f"WARNING: Could not send failure notification: {e}")
