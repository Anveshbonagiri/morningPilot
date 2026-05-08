"""Microsoft Graph device-code OAuth using MSAL.

Uses the Microsoft Graph PowerShell well-known public client ID, which works
without requiring you to register your own Entra ID app. You authenticate once
via https://microsoft.com/devicelogin and the token is cached to disk.
"""
from __future__ import annotations
import json
import os
import threading
from pathlib import Path
from typing import Optional

import msal

# Microsoft Graph PowerShell — well-known public client, pre-consented in most tenants
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
SCOPES = ["Mail.Read", "Calendars.Read", "Chat.Read", "User.Read"]
CACHE_FILE = Path(__file__).parent.parent / ".token_cache.bin"


_cache_lock = threading.Lock()
_pending_flow: dict | None = None
_pending_thread: threading.Thread | None = None


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text())
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_FILE.write_text(cache.serialize())


def _get_app(cache: msal.SerializableTokenCache | None = None) -> msal.PublicClientApplication:
    cache = cache or _load_cache()
    client_id = os.getenv("MS_GRAPH_CLIENT_ID", DEFAULT_CLIENT_ID)
    tenant = os.getenv("MS_GRAPH_TENANT_ID", "common")
    return msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )


def get_access_token() -> Optional[str]:
    """Return a valid access token from cache, or None if not authenticated."""
    with _cache_lock:
        cache = _load_cache()
        app = _get_app(cache)
        accounts = app.get_accounts()
        if not accounts:
            return None
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        _save_cache(cache)
        if result and "access_token" in result:
            return result["access_token"]
        return None


def get_signed_in_user() -> dict | None:
    """Return basic info about the signed-in user (from cache)."""
    cache = _load_cache()
    app = _get_app(cache)
    accounts = app.get_accounts()
    if not accounts:
        return None
    return {"username": accounts[0].get("username"), "name": accounts[0].get("username")}


def start_device_flow() -> dict:
    """Initiate a device-code flow. Returns user_code + verification_uri.

    A background thread completes the flow once the user enters the code.
    """
    global _pending_flow, _pending_thread

    cache = _load_cache()
    app = _get_app(cache)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to start device flow: {flow}")

    _pending_flow = flow

    def _complete():
        try:
            with _cache_lock:
                # Use a fresh app bound to the same cache
                local_cache = _load_cache()
                local_app = _get_app(local_cache)
                local_app.acquire_token_by_device_flow(flow)  # blocks until user signs in or times out
                _save_cache(local_cache)
        except Exception as e:
            print(f"Device flow error: {e}")

    _pending_thread = threading.Thread(target=_complete, daemon=True)
    _pending_thread.start()

    return {
        "user_code": flow["user_code"],
        "verification_uri": flow["verification_uri"],
        "message": flow.get("message"),
        "expires_in": flow.get("expires_in"),
    }


def is_authenticated() -> bool:
    return get_access_token() is not None


def logout() -> None:
    """Clear the token cache."""
    with _cache_lock:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
