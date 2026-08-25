#!/usr/bin/env python3
"""Generate a one-time Google Drive OAuth token for Railway.

Usage:
  python3 tools/google_drive_oauth_token.py /path/to/oauth-client.json

The output file contains the value for CLEANING_DRIVE_OAUTH_TOKEN_JSON.
Do not commit or share the generated token.
"""

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tools/google_drive_oauth_token.py /path/to/oauth-client.json")
        return 2

    client_path = Path(sys.argv[1]).expanduser()
    if not client_path.exists():
        print(f"OAuth client JSON not found: {client_path}")
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        authorization_prompt_message=(
            "Open this link in your browser if it did not open automatically:\n{url}\n"
        ),
        success_message="Google Drive access approved. You can close this tab and return to Codex.",
        open_browser=True,
    )

    token = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    out_path = Path(os.environ.get("OUJA_DRIVE_TOKEN_OUT", "/tmp/ouja_cleaning_drive_token.json"))
    out_path.write_text(json.dumps(token, ensure_ascii=False), encoding="utf-8")
    print(f"Token JSON written to: {out_path}")
    print("Put the full contents of that file into Railway as CLEANING_DRIVE_OAUTH_TOKEN_JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
