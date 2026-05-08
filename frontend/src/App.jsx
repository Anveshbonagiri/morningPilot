import { useEffect, useState } from 'react'

function fmtTime(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function todayStr() {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric'
  })
}

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authStatus, setAuthStatus] = useState({ authenticated: false })
  const [deviceFlow, setDeviceFlow] = useState(null)
  const [useReal, setUseReal] = useState(false)

  const load = async (real = useReal) => {
    setLoading(true); setError(null)
    try {
      const r = await fetch(`/api/briefing?real=${real}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch (e) {
      setError(e.message)
    } finally { setLoading(false) }
  }

  const checkAuth = async () => {
    try {
      const r = await fetch('/api/auth/status')
      const j = await r.json()
      setAuthStatus(j)
      return j.authenticated
    } catch { return false }
  }

  const startConnect = async () => {
    const r = await fetch('/api/auth/start', { method: 'POST' })
    const flow = await r.json()
    setDeviceFlow(flow)
    // poll auth status every 3s
    const poll = setInterval(async () => {
      const ok = await checkAuth()
      if (ok) {
        clearInterval(poll)
        setDeviceFlow(null)
        setUseReal(true)
        load(true)
      }
    }, 3000)
  }

  const disconnect = async () => {
    await fetch('/api/auth/logout', { method: 'POST' })
    setAuthStatus({ authenticated: false })
    setUseReal(false)
    load(false)
  }

  useEffect(() => {
    checkAuth().then(ok => { if (ok) setUseReal(true); load(ok) })
  }, [])

  if (loading) return <div className="app"><div className="loading">Synthesizing your morning briefing…</div></div>
  if (error) return <div className="app"><div className="error">Failed to load briefing: {error}</div></div>
  if (!data) return null

  const titleById = Object.fromEntries((data.timeline || []).map(t => [t.id, t.title]))

  return (
    <div className="app">
      <div className="toolbar">
        <div className="header">
          <h1>Good morning, {data.user?.name?.split(' ')[0] || 'there'} ☀️</h1>
          <p>{todayStr()} · MorningPilot briefing</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          {authStatus.authenticated ? (
            <>
              <button onClick={() => load(true)}>↻ Refresh</button>
              <button onClick={disconnect} className="btn-secondary" style={{ marginLeft: 8 }}>Disconnect</button>
              <div className="engine-tag" style={{ marginTop: 6 }}>
                engine: {data._engine} · data: <strong>{data._data_source}</strong>
                {authStatus.user?.username && <> · {authStatus.user.username}</>}
              </div>
            </>
          ) : (
            <>
              <button onClick={startConnect} className="btn-primary">🔐 Connect Microsoft 365</button>
              <button onClick={() => load(false)} className="btn-secondary" style={{ marginLeft: 8 }}>↻ Refresh</button>
              <div className="engine-tag" style={{ marginTop: 6 }}>engine: {data._engine} · data: <strong>mock</strong></div>
            </>
          )}
        </div>
      </div>

      {deviceFlow && (
        <div className="device-modal">
          <div className="device-modal-inner">
            <h3>Connect to Microsoft 365</h3>
            <p>1. Open this URL:</p>
            <a href={deviceFlow.verification_uri} target="_blank" rel="noopener noreferrer" className="device-link">
              {deviceFlow.verification_uri} ↗
            </a>
            <p>2. Enter this code:</p>
            <div className="device-code">{deviceFlow.user_code}</div>
            <p className="device-hint">Sign in with anbonagi@microsoft.com. This window will close automatically when you're connected.</p>
            <button onClick={() => setDeviceFlow(null)} className="btn-secondary">Cancel</button>
          </div>
        </div>
      )}

      <div className="headline">
        <span className="label">✨ AI briefing · Today's headline</span>
        {data.headline}
      </div>

      {data.pep_talk && (
        <div className="pep-talk">
          <span className="ai-tag">AI co-pilot</span>
          <p>{data.pep_talk}</p>
        </div>
      )}

      <div className="top-row">
        <div className="card">
          <h3>✨ AI · Top 3 priorities</h3>
          <ol>
            {(data.top_priorities || []).map(id => (
              <li key={id}>{titleById[id] || id}</li>
            ))}
          </ol>
        </div>
        <div className="card">
          <h3>✨ AI · Focus recommendation</h3>
          <div className="focus">{data.focus_recommendation}</div>
        </div>
      </div>

      <div className="section-title">Your day, ranked by priority</div>

      {(() => {
        const order = ['critical', 'high', 'medium', 'low']
        const labels = {
          critical: 'Critical · Handle now',
          high: 'High · Today',
          medium: 'Medium · This week',
          low: 'Low · Skim or skip',
        }
        const shortLabels = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' }
        const sublabels = {
          critical: 'Handle now',
          high: 'Today',
          medium: 'This week',
          low: 'Skim or skip',
        }
        const groups = Object.fromEntries(order.map(k => [k, []]))
        ;(data.timeline || []).forEach(it => {
          if (groups[it.priority]) groups[it.priority].push(it)
        })
        Object.values(groups).forEach(arr =>
          arr.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
        )

        const scrollTo = (pri) => {
          const el = document.getElementById(`pri-${pri}`)
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }

        return (
          <>
            <div className="quick-view">
              {order.map(pri => (
                <button
                  key={pri}
                  className={`quick-card ${pri}`}
                  onClick={() => scrollTo(pri)}
                  aria-label={`Jump to ${shortLabels[pri]} items`}
                >
                  <div className="quick-card-count">{groups[pri].length}</div>
                  <div className="quick-card-label">{shortLabels[pri]}</div>
                  <div className="quick-card-sub">{sublabels[pri]}</div>
                </button>
              ))}
            </div>

            {order.map(pri => (
              <div className={`priority-card ${pri}`} key={pri} id={`pri-${pri}`}>
                <div className="priority-card-header">
                  <span className="priority-card-title">{labels[pri]}</span>
                  <span className="priority-card-count">{groups[pri].length}</span>
                </div>
                {data.priority_summaries?.[pri] && (
                  <div className="ai-summary">
                    <span className="ai-summary-tag">✨ AI</span>
                    <span>{data.priority_summaries[pri]}</span>
                  </div>
                )}
                {groups[pri].length === 0 ? (
                  <div className="priority-card-empty">Nothing here — nice.</div>
                ) : (
                  groups[pri].map(item => (
                    <div className="timeline-item" key={`${item.source}-${item.id}`}>
                      <div className="time">{fmtTime(item.timestamp)}</div>
                      <div className={`dot ${item.priority}`} />
                      <div className="item-body">
                        <div className="row1">
                          <span className={`source-badge src-${item.source}`}>{item.source}</span>
                        </div>
                        <div className="title">{item.title}</div>
                        <div className="summary">{item.summary}</div>
                        <div className="action-row">
                          <span className="action">→ {item.action}</span>
                          <span className="reasoning">· {item.reasoning}</span>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            ))}
          </>
        )
      })()}
      {data.sources && (
        <div className="sources-line">
          Pulled from {data.sources.emails} emails · {data.sources.meetings} meetings · {data.sources.teams} Teams · {data.sources.slack} Slack · {data.sources.jira} Jira · {data.sources.sap} SAP approvals
        </div>
      )}
    </div>
  )
}
