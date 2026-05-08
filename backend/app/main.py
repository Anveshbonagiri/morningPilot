import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .graph_client import get_emails, get_meetings, get_teams_messages, get_user
from .external_clients import get_jira_tickets, get_slack_messages, get_sap_approvals
from .briefing import synthesize_briefing, fallback_briefing

load_dotenv()

app = FastAPI(title="MorningPilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "openai_configured": bool(os.getenv("AZURE_OPENAI_API_KEY"))}


@app.get("/api/raw")
def raw_data():
    return {
        "user": get_user(),
        "emails": get_emails(),
        "meetings": get_meetings(),
        "teams_messages": get_teams_messages(),
        "slack_messages": get_slack_messages(),
        "jira_tickets": get_jira_tickets(),
        "sap_approvals": get_sap_approvals(),
    }


@app.get("/api/briefing")
def briefing(use_ai: bool = True):
    user = get_user()
    emails = get_emails()
    meetings = get_meetings()
    teams = get_teams_messages()
    slack = get_slack_messages()
    jira = get_jira_tickets()
    sap = get_sap_approvals()

    if use_ai and os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        try:
            result = synthesize_briefing(user, emails, meetings, teams, slack, jira, sap)
            result["_engine"] = "azure-openai"
        except Exception as e:
            result = fallback_briefing(user, emails, meetings, teams, slack, jira, sap)
            result["_engine"] = f"fallback (ai error: {type(e).__name__})"
    else:
        result = fallback_briefing(user, emails, meetings, teams, slack, jira, sap)
        result["_engine"] = "fallback-heuristic"

    result["user"] = user
    result["sources"] = {
        "emails": len(emails), "meetings": len(meetings), "teams": len(teams),
        "slack": len(slack), "jira": len(jira), "sap": len(sap),
    }
    return result
