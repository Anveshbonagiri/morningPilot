import json
from pathlib import Path

DATA_FILE = Path(__file__).parent / "mock_data" / "graph_data.json"


def load_mock_data() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_emails():
    return load_mock_data()["emails"]


def get_meetings():
    return load_mock_data()["meetings"]


def get_teams_messages():
    return load_mock_data()["teams_messages"]


def get_user():
    return load_mock_data()["user"]
