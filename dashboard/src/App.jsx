import { useEffect, useRef, useState } from 'react'
import './App.css'
import DocsPanel from './DocsPanel.jsx'
import TracePanel from './TracePanel.jsx'
import { postJson } from './api.js'

const MAX_CHARS = 2000

function describe(data) {
  if (data.via === 'rule') return `skill: ${data.skill}`
  return data.provider ? `LLM: ${data.provider}` : 'LLM'
}

function Sources({ sources }) {
  return (
    <details className="sources">
      <summary>
        Sources ({sources.length})
      </summary>
      {sources.map((s, i) => (
        <div className="source" key={i}>
          <div className="source-head">
            {s.doc_name} · part {s.idx + 1} · match {s.score.toFixed(2)}
          </div>
          <div className="source-text">{s.text}</div>
        </div>
      ))}
    </details>
  )
}

export default function App() {
  const [view, setView] = useState('chat') // 'chat' or 'trace'
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy, view])

  async function ask(message) {
    if (busy) return
    setView('chat')
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', text: message }])
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const data = await postJson('/chat', { text: message }, { signal: controller.signal })
      setMessages((m) => [
        ...m,
        {
          role: 'friday',
          text: data.reply,
          meta: describe(data),
          sources: data.sources,
        },
      ])
    } catch (err) {
      if (err.name === 'AbortError') {
        setMessages((m) => [
          ...m,
          { role: 'friday', text: 'Stopped waiting for that answer.', meta: 'the server may still finish it' },
        ])
      } else {
        setMessages((m) => [...m, { role: 'friday', text: err.message, error: true }])
      }
    } finally {
      abortRef.current = null
      setBusy(false)
    }
  }

  function submit(event) {
    event.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    setText('')
    ask(message)
  }

  return (
    <div className="layout">
      <DocsPanel ask={ask} busy={busy} />

      <div className="app">
        <header className="app-header">
          <div>
            <h1>Friday</h1>
            <p>Same brain as the voice loop and Telegram.</p>
          </div>
          <nav className="tabs">
            <button
              type="button"
              className={view === 'chat' ? 'tab active' : 'tab'}
              onClick={() => setView('chat')}
            >
              Chat
            </button>
            <button
              type="button"
              className={view === 'trace' ? 'tab active' : 'tab'}
              onClick={() => setView('trace')}
            >
              Trace
            </button>
          </nav>
        </header>

        {view === 'trace' ? (
          <TracePanel />
        ) : (
          <>
            <main className="messages">
              {messages.length === 0 && (
                <div className="empty">Try: what time is it, or: what&apos;s 18% of 2400</div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`row ${m.role}${m.error ? ' error' : ''}`}>
                  <div className="bubble">{m.text}</div>
                  {m.meta && <div className="meta">{m.meta}</div>}
                  {m.sources?.length > 0 && <Sources sources={m.sources} />}
                </div>
              ))}
              {busy && (
                <div className="row friday">
                  <div className="bubble">...</div>
                </div>
              )}
              <div ref={endRef} />
            </main>

            <form className="composer" onSubmit={submit}>
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={MAX_CHARS}
                placeholder="Type a message"
                autoFocus
              />
              {busy ? (
                <button type="button" className="stop" onClick={() => abortRef.current?.abort()}>
                  Stop
                </button>
              ) : (
                <button type="submit" disabled={!text.trim()}>
                  Send
                </button>
              )}
            </form>
          </>
        )}
      </div>
    </div>
  )
}