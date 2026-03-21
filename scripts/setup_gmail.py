#!/usr/bin/env python3
"""
One-time Gmail OAuth setup. Run locally to authorize access and upload the token to GCS.

Prerequisites:
  1. Enable the Gmail API in GCP Console:
     https://console.cloud.google.com/apis/library/gmail.googleapis.com
  2. Create an OAuth 2.0 Client ID (type: Desktop app):
     GCP Console → APIs & Services → Credentials → Create Credentials → OAuth client ID
  3. Download the JSON and save it as gmail_credentials.json in the project root
  4. Run: source .env && python scripts/setup_gmail.py

The token will be uploaded to gs://{BUCKET_NAME}/config/gmail_token.json and
used by Cloud Run to send failure notifications via the Gmail API.
"""

import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

def main():
    bucket_name = os.environ.get("BUCKET_NAME")
    if not bucket_name:
        print("ERROR: BUCKET_NAME not set. Run: source .env")
        sys.exit(1)

    credentials_file = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
    if not os.path.exists(credentials_file):
        print(f"ERROR: {credentials_file} not found in project root.")
        print("Download it from GCP Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
        sys.exit(1)

    print("Opening browser for Gmail authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    # Save locally first
    local_path = "gmail_token.json"
    with open(local_path, "w") as f:
        json.dump(token_data, f)
    print(f"Token saved to {local_path}")

    # Upload to GCS using gcloud CLI (uses existing gcloud auth)
    import subprocess
    gcs_path = f"gs://{bucket_name}/config/gmail_token.json"
    subprocess.run(["gcloud", "storage", "cp", local_path, gcs_path], check=True)
    os.remove(local_path)

    print(f"Token uploaded to {gcs_path}")
    print("Gmail is ready. You can now deploy and test failure notifications.")


if __name__ == "__main__":
    main()
