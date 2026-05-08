"""Mock connectors for Jira, Slack, and SAP — same shape they'd return live."""
import json
from pathlib import Path

DATA_FILE = Path(__file__).parent / "mock_data" / "external_systems.json"


def _load() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_jira_tickets():
    return _load()["tickets"]


def get_slack_messages():
    return _load()["messages"]


def get_sap_approvals():
    return _load()["approvals"]
