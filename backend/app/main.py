import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .graph_client import (
    get_emails as mock_emails,
    get_meetings as mock_meetings,
    get_teams_messages as mock_teams,
    get_user as mock_user,
)
from .external_clients import get_jira_tickets, get_slack_messages, get_sap_approvals
from .briefing import synthesize_briefing, fallback_briefing
from . import auth
from . import real_graph

load_dotenv()

app = FastAPI(title="MorningPilot API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "openai_configured": bool(os.getenv("AZURE_OPENAI_API_KEY")),
        "graph_authenticated": auth.is_authenticated(),
    }


@app.get("/api/auth/status")
def auth_status():
    if auth.is_authenticated():
        u = auth.get_signed_in_user() or {}
        return {"authenticated": True, "user": u}
    return {"authenticated": False}


@app.post("/api/auth/start")
def auth_start():
    try:
        flow = auth.start_device_flow()
        return flow
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/auth/logout")
def auth_logout():
    auth.logout()
    return {"ok": True}


@app.get("/api/raw")
def raw_data(real: bool = False):
    use_real = real and auth.is_authenticated()
    if use_real:
        try:
            return {
                "user": real_graph.get_user(),
                "emails": real_graph.get_emails(),
                "meetings": real_graph.get_meetings(),
                "teams_messages": real_graph.get_teams_messages(),
                "slack_messages": get_slack_messages(),
                "jira_tickets": get_jira_tickets(),
                "sap_approvals": get_sap_approvals(),
                "_source": "microsoft-graph",
            }
        except Exception as e:
            raise HTTPException(502, f"Graph error: {e}")
    return {
        "user": mock_user(),
        "emails": mock_emails(),
        "meetings": mock_meetings(),
        "teams_messages": mock_teams(),
        "slack_messages": get_slack_messages(),
        "jira_tickets": get_jira_tickets(),
        "sap_approvals": get_sap_approvals(),
        "_source": "mock",
    }


@app.get("/api/briefing")
def briefing(use_ai: bool = True, real: bool = False):
    use_real = real and auth.is_authenticated()
    data_source = "mock"
    if use_real:
        try:
            user = real_graph.get_user()
            emails = real_graph.get_emails()
            meetings = real_graph.get_meetings()
            teams = real_graph.get_teams_messages()
            data_source = "microsoft-graph"
        except Exception as e:
            user = mock_user(); emails = mock_emails(); meetings = mock_meetings(); teams = mock_teams()
            data_source = f"mock (graph error: {type(e).__name__})"
    else:
        user = mock_user(); emails = mock_emails(); meetings = mock_meetings(); teams = mock_teams()

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
    result["_data_source"] = data_source
    result["sources"] = {
        "emails": len(emails), "meetings": len(meetings), "teams": len(teams),
        "slack": len(slack), "jira": len(jira), "sap": len(sap),
    }
    return result
