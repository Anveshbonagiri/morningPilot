# MorningPilot 🌅

Your AI co-pilot for the first hour of work. Hackathon MVP.

Scans overnight email, meetings, and Teams messages → synthesizes a single ranked timeline so you walk in with a plan, not a backlog.

## Stack
- **Backend:** FastAPI + Azure OpenAI (deployment `gpt-4.1`)
- **Frontend:** React + Vite
- **Data:** Mock Microsoft Graph data (8 emails, 5 meetings, 5 Teams messages) baked in for demo. Swap `app/graph_client.py` for real Graph API later.

## Run

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env -> add AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

If you don't configure Azure OpenAI, the API automatically falls back to a heuristic classifier so the demo still works.

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Endpoints
- `GET /api/health` – status + whether AI is configured
- `GET /api/raw` – raw mock Graph data
- `GET /api/briefing` – the synthesized briefing (timeline + top priorities + focus rec)
- `GET /api/briefing?use_ai=false` – force heuristic mode

## What the briefing returns
```json
{
  "headline": "...",
  "top_priorities": ["e1","t2","m1"],
  "focus_recommendation": "...",
  "timeline": [
    { "id":"e1", "source":"email", "timestamp":"...",
      "title":"...", "summary":"...",
      "priority":"critical|high|medium|low",
      "action":"Reply by 9:30am",
      "reasoning":"VIP + hard deadline" }
  ]
}
```

## Demo script
1. Open the dashboard — show the headline, top 3, and focus block.
2. Scroll the timeline — point out how a CEO email is "low" (no urgency) while Sarah's roadmap email is "critical".
3. Hit **Refresh** to re-run synthesis live (great for showing the AI reasoning is dynamic).
4. Toggle `?use_ai=false` in the URL to compare heuristic vs LLM output.

## Roadmap (post-MVP)
- Real Microsoft Graph auth (MSAL delegated flow, scopes: Mail.Read, Calendars.Read, Chat.Read)
- Suggested draft replies (with "Approve & Send")
- Auto-decline low-value meetings
- Block focus time on calendar
- Feedback loop: thumbs up/down per item → fine-tune prompt
