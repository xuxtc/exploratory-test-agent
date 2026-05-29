#!/usr/bin/env python3
"""
Smoke-test Google Drive OAuth token and Google Sheets service-account credentials.
Exits 0 on success, non-zero on failure. Prints one status line per check.

Usage:
  scripts/check-google-auth.py          # checks both Drive + Sheets
  scripts/check-google-auth.py --drive  # Drive only
  scripts/check-google-auth.py --sheets # Sheets only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN_PATH = REPO_ROOT / "config" / "google-oauth-token.json"
CLIENT_PATH = REPO_ROOT / "config" / "google-oauth-client.json"
SHEETS_CREDS = REPO_ROOT / "config" / "google-sheets-mcp-credentials.json"
SHEET_ID = "1mnWLqs4vhLBi2YzSeqNU1YwcfRFz_987PjbgI-3lf6g"

OK = "✅"
FAIL = "❌"


# ── Drive ─────────────────────────────────────────────────────────────────────

def _refresh_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Return a fresh access_token, or raise on failure."""
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def check_drive() -> bool:
    if not TOKEN_PATH.exists():
        print(f"{FAIL} Google Drive: token file not found ({TOKEN_PATH.relative_to(REPO_ROOT)})")
        print("       Fix: run  python3 exploratory-test-agent/scripts/google-drive.py auth")
        return False
    if not CLIENT_PATH.exists():
        print(f"{FAIL} Google Drive: client secrets not found ({CLIENT_PATH.relative_to(REPO_ROOT)})")
        return False

    token_data = json.loads(TOKEN_PATH.read_text())
    client_data = json.loads(CLIENT_PATH.read_text())
    installed = client_data.get("installed") or client_data.get("web") or {}
    client_id = installed.get("client_id", "")
    client_secret = installed.get("client_secret", "")
    refresh_token = token_data.get("refresh_token", "")

    if not refresh_token:
        print(f"{FAIL} Google Drive: no refresh_token in {TOKEN_PATH.name}")
        print("       Fix: run  python3 exploratory-test-agent/scripts/google-drive.py auth")
        return False

    # Check if current access_token is still valid, else refresh
    access_token = token_data.get("access_token", "")
    expires_at = token_data.get("expires_at", 0)
    if not access_token or time.time() > expires_at - 60:
        try:
            access_token = _refresh_token(client_id, client_secret, refresh_token)
        except Exception as e:
            print(f"{FAIL} Google Drive: token refresh failed — {e}")
            print("       Fix: run  python3 exploratory-test-agent/scripts/google-drive.py auth")
            return False

    # Probe Drive API with a simple files.list (limit 1)
    req = urllib.request.Request(
        "https://www.googleapis.com/drive/v3/files?pageSize=1",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            json.loads(r.read())
        print(f"{OK} Google Drive: OAuth token valid, Drive API reachable")
        return True
    except urllib.error.HTTPError as e:
        print(f"{FAIL} Google Drive: API probe returned HTTP {e.code} — {e.reason}")
        return False
    except Exception as e:
        print(f"{FAIL} Google Drive: API probe failed — {e}")
        return False


# ── Sheets ────────────────────────────────────────────────────────────────────

def check_sheets() -> bool:
    if not SHEETS_CREDS.exists():
        print(f"{FAIL} Google Sheets: credentials file not found ({SHEETS_CREDS.relative_to(REPO_ROOT)})")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print(f"{FAIL} Google Sheets: gspread not installed — run  pip install gspread google-auth")
        return False

    try:
        creds = Credentials.from_service_account_file(
            str(SHEETS_CREDS),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        sheet_names = [ws.title for ws in sh.worksheets()]
        print(f"{OK} Google Sheets: connected — {len(sheet_names)} sheet(s): {', '.join(sheet_names[:5])}")
        return True
    except Exception as e:
        print(f"{FAIL} Google Sheets: connection failed — {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Smoke-test Google auth for the QA pipeline.")
    parser.add_argument("--drive", action="store_true", help="Check Drive only")
    parser.add_argument("--sheets", action="store_true", help="Check Sheets only")
    args = parser.parse_args()

    check_all = not args.drive and not args.sheets
    ok = True
    if check_all or args.drive:
        ok = check_drive() and ok
    if check_all or args.sheets:
        ok = check_sheets() and ok

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
