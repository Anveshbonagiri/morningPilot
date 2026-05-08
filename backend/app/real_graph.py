"""Real Microsoft Graph data fetchers — emails, calendar events, Teams chats."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .auth import get_access_token

GRAPH = "https://graph.microsoft.com/v1.0"


def _headers() -> dict:
    token = get_access_token()
    if not token:
        raise RuntimeError("Not authenticated to Microsoft Graph")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _get(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_user() -> dict:
    me = _get(f"{GRAPH}/me")
    vips: list[str] = []  # could be enriched later
    return {
        "name": me.get("displayName") or me.get("userPrincipalName", "there"),
        "role": me.get("jobTitle") or "",
        "email": me.get("mail") or me.get("userPrincipalName"),
        "vip_contacts": vips,
    }


def get_emails(hours_back: int = 14, top: int = 25) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat().replace("+00:00", "Z")
    params = {
        "$top": str(top),
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments",
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since}",
    }
    data = _get(f"{GRAPH}/me/messages", params=params)
    out = []
    for m in data.get("value", []):
        sender = (m.get("from") or {}).get("emailAddress") or {}
        out.append({
            "id": m["id"],
            "from": sender.get("address", "unknown"),
            "from_name": sender.get("name", sender.get("address", "unknown")),
            "subject": m.get("subject") or "(no subject)",
            "received": m.get("receivedDateTime"),
            "preview": (m.get("bodyPreview") or "")[:400],
            "is_unread": not m.get("isRead", True),
            "has_attachments": bool(m.get("hasAttachments")),
        })
    return out


def get_meetings(hours_ahead: int = 14) -> list[dict]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours_ahead)
    params = {
        "startDateTime": now.isoformat().replace("+00:00", "Z"),
        "endDateTime": end.isoformat().replace("+00:00", "Z"),
        "$select": "id,subject,start,end,organizer,attendees,location,bodyPreview",
        "$orderby": "start/dateTime",
        "$top": "20",
    }
    data = _get(f"{GRAPH}/me/calendarView", params=params)
    out = []
    for ev in data.get("value", []):
        org = ((ev.get("organizer") or {}).get("emailAddress") or {})
        loc = (ev.get("location") or {}).get("displayName") or ""
        attendees = ev.get("attendees") or []
        out.append({
            "id": ev["id"],
            "subject": ev.get("subject") or "(no subject)",
            "start": (ev.get("start") or {}).get("dateTime"),
            "end": (ev.get("end") or {}).get("dateTime"),
            "organizer": org.get("address", "unknown"),
            "attendees": len(attendees),
            "location": loc or "Teams",
            "has_agenda": bool((ev.get("bodyPreview") or "").strip()),
            "notes": (ev.get("bodyPreview") or "")[:300],
        })
    return out


def get_teams_messages(hours_back: int = 14, top: int = 20) -> list[dict]:
    """Fetch recent Teams chat messages across the user's chats."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat().replace("+00:00", "Z")
    out: list[dict] = []
    try:
        chats = _get(f"{GRAPH}/me/chats", params={"$top": "20"}).get("value", [])
    except Exception:
        return out
    me_email = (get_user() or {}).get("email", "").lower()
    for chat in chats[:15]:
        cid = chat.get("id")
        if not cid:
            continue
        try:
            msgs = _get(f"{GRAPH}/me/chats/{cid}/messages", params={"$top": "5"}).get("value", [])
        except Exception:
            continue
        chat_topic = chat.get("topic") or ("Direct Message" if chat.get("chatType") == "oneOnOne" else "Group Chat")
        for m in msgs:
            ts = m.get("createdDateTime")
            if not ts or ts < since:
                continue
            sender = ((m.get("from") or {}).get("user") or {})
            preview = (m.get("body") or {}).get("content") or ""
            # crude HTML strip
            import re
            preview = re.sub(r"<[^>]+>", "", preview).strip()[:300]
            mentions = m.get("mentions") or []
            mentioned_emails = {
                ((mn.get("mentioned") or {}).get("user") or {}).get("userIdentityType", "")
                for mn in mentions
            }
            mentions_user = any(
                me_email in str((((mn.get("mentioned") or {}).get("user") or {}).get("displayName") or "")).lower()
                or me_email == str((((mn.get("mentioned") or {}).get("user") or {}).get("id") or "")).lower()
                for mn in mentions
            ) or (me_email and me_email in preview.lower())
            out.append({
                "id": m.get("id"),
                "from": sender.get("id") or sender.get("displayName", "unknown"),
                "from_name": sender.get("displayName", "unknown"),
                "channel": chat_topic,
                "timestamp": ts,
                "preview": preview,
                "mentions_user": mentions_user,
            })
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out[:top]
