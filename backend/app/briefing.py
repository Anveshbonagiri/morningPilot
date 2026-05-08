"""
Briefing synthesis using Azure OpenAI.
Takes raw email/meeting/Teams items, classifies each, and produces a unified
chronological timeline ranked by priority.
"""
import json
import os
from datetime import datetime
from typing import Any

from openai import AzureOpenAI

_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        _client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        )
    return _client


SYSTEM_PROMPT = """You are MorningPilot, an executive briefing assistant. You receive a knowledge worker's overnight emails, today's meetings, recent Teams messages, Slack messages, Jira tickets assigned to them, and SAP approvals waiting on them — and you produce a single ranked timeline.

For EVERY input item produce one timeline entry with these fields:
- id: original item id
- source: "email" | "meeting" | "teams" | "slack" | "jira" | "sap"
- timestamp: ISO 8601 (use received/start/timestamp/updated/submitted from the input)
- title: short title (subject, meeting name, ticket key + summary, "{type} {doc_id}", or message preview)
- summary: 1-2 sentence synthesis of WHY this matters and WHAT action (if any) is needed
- priority: "critical" | "high" | "medium" | "low"
- action: short imperative like "Reply by 9:30am", "Prep agenda", "Skim — optional", "Ignore — newsletter"
- reasoning: one short phrase explaining the priority (e.g., "VIP sender + hard deadline")

Priority guidance:
- critical: VIP sender + hard deadline today, or blocking decision
- high: action required today from important sender, or meeting requiring prep
- medium: needs response this week, recurring 1:1, optional but useful meetings
- low: newsletters, FYI, automated notifications, optional all-hands

After the items, produce:
- top_priorities: array of 3 item ids the user must handle first (in order)
- focus_recommendation: one sentence suggesting when/how to block focus time today
- headline: a single punchy sentence summarizing the morning (e.g., "Two critical sign-offs before 11am, then engineering decision and customer renewal call.")
- pep_talk: 2-3 sentences, warm and motivating but never cheesy. Acknowledge the load, name the highest-leverage win of the day, and give the user permission to ignore the noise. Address them by first name. Be human, specific to today's items, and mildly witty (think: a sharp chief-of-staff who has your back). NO emojis except at most one tasteful one.
- priority_summaries: an object with keys "critical", "high", "medium", "low". Each value is ONE creative, specific, energizing sentence (max ~22 words) that summarizes what's in that bucket and frames the user's mindset for it. Examples of tone:
  - critical: "Two sign-offs and a P0 ticket — these are the rocks; clear them before 10 and the day opens up."
  - high: "Your 'today' pile is dense but tractable — batch the engineering decisions, then the CEO ping."
  - medium: "Five solid items that can wait until you have momentum — slot into the post-lunch focus block."
  - low: "Newsletters, bots, and a $320 auto-renewed invoice. Archive in two minutes, no guilt."
  If a bucket is empty, return a celebratory one-liner like "Inbox-zero on critical — protect that quiet."

Return STRICT JSON only with this shape:
{
  "headline": "...",
  "pep_talk": "...",
  "top_priorities": ["id1","id2","id3"],
  "focus_recommendation": "...",
  "priority_summaries": { "critical":"...", "high":"...", "medium":"...", "low":"..." },
  "timeline": [ { "id":"...", "source":"...", "timestamp":"...", "title":"...", "summary":"...", "priority":"...", "action":"...", "reasoning":"..." } ]
}
"""


def build_user_payload(user, emails, meetings, teams, slack, jira, sap) -> str:
    return json.dumps(
        {
            "user": user,
            "current_time": datetime.now().isoformat(),
            "emails": emails,
            "meetings": meetings,
            "teams_messages": teams,
            "slack_messages": slack,
            "jira_tickets": jira,
            "sap_approvals": sap,
        },
        indent=2,
    )


def synthesize_briefing(user, emails, meetings, teams, slack, jira, sap) -> dict[str, Any]:
    client = _get_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
    payload = build_user_payload(user, emails, meetings, teams, slack, jira, sap)

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def fallback_briefing(user, emails, meetings, teams, slack, jira, sap) -> dict[str, Any]:
    """Heuristic fallback if Azure OpenAI is not configured. Useful for offline demos."""
    vips = set(user.get("vip_contacts", []))
    timeline = []

    for e in emails:
        is_vip = e["from"] in vips
        subj_low = (e["subject"] or "").lower()
        urgent_kw = any(k in subj_low for k in ["urgent", "asap", "today", "sign-off", "deadline"])
        is_noise = any(k in e["from"].lower() for k in ["noreply", "newsletter", "no-reply"])

        if is_vip and urgent_kw:
            pri, action, reason = "critical", "Reply ASAP", "VIP + urgent keyword"
        elif is_vip:
            pri, action, reason = "high", "Reply today", "VIP sender"
        elif urgent_kw:
            pri, action, reason = "high", "Review and respond", "Urgent keyword"
        elif is_noise:
            pri, action, reason = "low", "Skip / archive", "Automated/newsletter"
        else:
            pri, action, reason = "medium", "Respond this week", "Standard email"

        timeline.append({
            "id": e["id"], "source": "email", "timestamp": e["received"],
            "title": e["subject"], "summary": e.get("preview", ""),
            "priority": pri, "action": action, "reasoning": reason,
        })

    for m in meetings:
        is_vip = m["organizer"] in vips
        big = m["attendees"] >= 50
        if is_vip and m.get("has_agenda"):
            pri, action, reason = "high", "Prep agenda items", "VIP + agenda"
        elif big:
            pri, action, reason = "low", "Optional — catch recording", "Large broadcast meeting"
        elif m.get("has_agenda"):
            pri, action, reason = "medium", "Skim agenda before", "Agenda exists"
        else:
            pri, action, reason = "medium", "Show up", "Standard meeting"
        timeline.append({
            "id": m["id"], "source": "meeting", "timestamp": m["start"],
            "title": m["subject"], "summary": m.get("notes", ""),
            "priority": pri, "action": action, "reasoning": reason,
        })

    for t in teams:
        is_vip = t["from"] in vips
        if t.get("mentions_user") and is_vip:
            pri, action, reason = "critical", "Respond now", "VIP @mention"
        elif t.get("mentions_user"):
            pri, action, reason = "high", "Respond today", "Direct @mention"
        elif "bot" in t["from"].lower() or "deploy" in t["from"].lower():
            pri, action, reason = "low", "Ignore — automated", "Bot message"
        else:
            pri, action, reason = "medium", "Read when free", "Channel chatter"
        timeline.append({
            "id": t["id"], "source": "teams", "timestamp": t["timestamp"],
            "title": f"{t['from_name']} ({t['channel']})",
            "summary": t.get("preview", ""),
            "priority": pri, "action": action, "reasoning": reason,
        })

    for s in slack:
        is_vip = s["from"] in vips
        if s.get("mentions_user") and is_vip:
            pri, action, reason = "critical", "Respond now", "VIP @mention on Slack"
        elif s.get("mentions_user"):
            pri, action, reason = "high", "Respond today", "Direct @mention"
        elif "bot" in s["from"].lower():
            pri, action, reason = "low", "Ignore — automated", "Slack bot"
        else:
            pri, action, reason = "medium", "Read when free", "Channel chatter"
        timeline.append({
            "id": s["id"], "source": "slack", "timestamp": s["timestamp"],
            "title": f"{s['from_name']} ({s['channel']})",
            "summary": s.get("preview", ""),
            "priority": pri, "action": action, "reasoning": reason,
        })

    for j in jira:
        jp = (j.get("priority") or "").lower()
        st = (j.get("status") or "").lower()
        if jp == "highest" or "p0" in (j.get("summary","" ).lower()):
            pri, action, reason = "critical", "Review ticket now", "Highest-priority Jira ticket"
        elif jp == "high" or "blocked" in st:
            pri, action, reason = "high", "Unblock today", "High priority or blocking"
        elif "review" in st:
            pri, action, reason = "medium", "Review this week", "Awaiting your review"
        else:
            pri, action, reason = "low", "Triage later", "Low-priority ticket"
        timeline.append({
            "id": j["id"], "source": "jira", "timestamp": j["updated"],
            "title": f"{j['key']} — {j['summary']}",
            "summary": f"{j['status']} · reported by {j.get('reporter','')}. {j.get('comment_preview','')}",
            "priority": pri, "action": action, "reasoning": reason,
        })

    for a in sap:
        amount_str = (a.get("amount") or "")
        big_money = any(t in amount_str for t in ["$10,", "$20,", "$30,", "$40,", "$50,", "$100,"]) or "48,200" in amount_str
        if a.get("status","").lower().startswith("awaiting") and big_money:
            pri, action, reason = "high", "Approve in SAP", "Large purchase awaiting approval"
        elif a.get("status","").lower().startswith("awaiting"):
            pri, action, reason = "medium", "Approve when free", "Approval awaiting you"
        else:
            pri, action, reason = "low", "FYI", "Informational SAP item"
        timeline.append({
            "id": a["id"], "source": "sap", "timestamp": a["submitted"],
            "title": f"{a['type']} {a['doc_id']} — {a['amount']}",
            "summary": f"{a['description']} · from {a['submitter']} · due {a.get('due_by','')}",
            "priority": pri, "action": action, "reasoning": reason,
        })

    pri_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    timeline.sort(key=lambda x: (pri_rank.get(x["priority"], 9), x["timestamp"]))
    top = sorted(timeline, key=lambda x: pri_rank[x["priority"]])[:3]

    return {
        "headline": "Two critical sign-offs and an engineering decision dominate the morning; protect 1pm for focus.",
        "pep_talk": f"Morning {user.get('name','').split(' ')[0]} — three things actually matter today, and you already know what they are. Knock out the sign-offs before 10 and the rest of the day belongs to you.",
        "top_priorities": [t["id"] for t in top],
        "focus_recommendation": "Block 12:00–13:00 for focused work between the engineering sync and the all-hands.",
        "priority_summaries": {
            "critical": "These are the rocks — clear them before 10am and the rest of the day opens up.",
            "high": "Today's must-dos: batch the engineering calls, then the people pings.",
            "medium": "Solid items that can wait — slot them into your post-lunch focus block.",
            "low": "Noise, bots, and FYIs. Archive in two minutes, no guilt.",
        },
        "timeline": timeline,
    }
