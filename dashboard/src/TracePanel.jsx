import { useEffect, useState } from 'react'

const REPLAY = 30 // steps replayed when the page opens
const MAX_ROWS = 300 // oldest steps are dropped beyond this
const RETRY_MS = 2000

function socketUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/trace?last=${REPLAY}`
}

function fmtTime(ts) {
  // Accepts an ISO string or epoch seconds/milliseconds; falls back to the raw value.
  const date = typeof ts === 'number' ? new Date(ts < 1e11 ? ts * 1000 : ts) : new Date(ts)
  return Number.isNaN(date.getTime()) ? String(ts) : date.toLocaleTimeString()
}

function fmtMs(ms) {
  return typeof ms === 'number' ? `${Math.round(ms)} ms` : ''
}

function groupRuns(rows) {
  const runs = []
  const byId = new Map()
  for (const row of rows) {
    let run = byId.get(row.run_id)
    if (!run) {
      run = { id: row.run_id, rows: [] }
      byId.set(row.run_id, run)
      runs.push(run)
    }
    run.rows.push(row)
  }
  return runs.reverse() // newest run first
}

export default function TracePanel() {
  const [rows, setRows] = useState([])
  const [status, setStatus] = useState('connecting')

  useEffect(() => {
    let socket
    let retry
    let closed = false

    function connect() {
      socket = new WebSocket(socketUrl())
      socket.onopen = () => setStatus('live')
      socket.onmessage = (event) => {
        const row = JSON.parse(event.data)
        // A reconnect replays old steps, so drop any with the same id first.
        setRows((old) => [...old.filter((r) => r.id !== row.id), row].slice(-MAX_ROWS))
      }
      socket.onclose = () => {
        if (closed) return
        setStatus('reconnecting')
        retry = setTimeout(connect, RETRY_MS)
      }
    }

    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      socket?.close()
    }
  }, [])

  const runs = groupRuns(rows)

  return (
    <section className="trace">
      <div className="trace-bar">
        <span className={status === 'live' ? 'live' : 'waiting'}>
          {status === 'live' ? 'Live' : status === 'connecting' ? 'Connecting...' : 'Reconnecting...'}
        </span>
        <button type="button" onClick={() => setRows([])} disabled={rows.length === 0}>
          Clear
        </button>
      </div>

      {runs.length === 0 && (
        <div className="empty">
          No steps yet. Send Friday a message and its steps show up here as they happen.
        </div>
      )}

      {runs.map((run) => (
        <div className="run" key={run.id}>
          <div className="run-head">
            run {run.id} · {fmtTime(run.rows[0].ts)} · {run.rows.length}{' '}
            {run.rows.length === 1 ? 'step' : 'steps'}
          </div>
          {run.rows.map((row) => (
            <div className="step" key={row.id}>
              <div className="step-head">
                <span className="step-name">{row.step}</span>
                <span className="step-ms">{fmtMs(row.ms)}</span>
              </div>
              {row.input && (
                <div className="step-io">
                  <b>in</b> {row.input}
                </div>
              )}
              {row.output && (
                <div className="step-io">
                  <b>out</b> {row.output}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </section>
  )
}