"""One-time step, run on your own computer: sign in to YouTube and print the refresh token.

    pip install google-auth-oauthlib
    python get_token.py client_secret.json

A browser opens. Sign in with the Google account that owns the channel,
pick the channel, and allow access. Copy the three values it prints into
GitHub secrets.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

with open(path, encoding="utf-8") as f:
    info = json.load(f)
info = info.get("installed") or info.get("web")

print("\nAdd these three secrets in GitHub (Settings > Secrets and variables > Actions):\n")
print(f"YT_CLIENT_ID      = {info['client_id']}")
print(f"YT_CLIENT_SECRET  = {info['client_secret']}")
print(f"YT_REFRESH_TOKEN  = {creds.refresh_token}")
