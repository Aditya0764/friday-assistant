import { useEffect, useRef, useState } from 'react'
import './App.css'
import DocsPanel from './DocsPanel.jsx'
import TracePanel from './TracePanel.jsx'
import { postJson, request } from './api.js'
import { useRecorder } from './useRecorder.js'
import { useSpeaker } from './useSpeaker.js'

const MAX_CHARS = 2000

function describe(data) {
  if (data.via === 'rule') return `skill: ${data.skill}`
  return data.provider ? `LLM: ${data.provider}` : 'LLM'
}

function fridayMessage(data) {
  return { role: 'friday', text: data.reply, meta: describe(data), sources: data.sources }
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
  const [busy, setBusy] = useState(false) // a typed message is waiting for its answer
  const [voiceBusy, setVoiceBusy] = useState(false) // a recording is being understood
  const endRef = useRef(null)
  const abortRef = useRef(null)
  const recorder = useRecorder()
  const speaker = useSpeaker()
  const locked = busy || voiceBusy || recorder.recording

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy, voiceBusy, view])

  function showError(message) {
    setMessages((m) => [...m, { role: 'friday', text: message, error: true }])
  }

  async function speakReply(reply) {
    const problem = await speaker.speak(reply)
    if (problem) showError(problem)
  }

  async function ask(message) {
    if (locked) return
    setView('chat')
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', text: message }])
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const data = await postJson('/chat', { text: message }, { signal: controller.signal })
      setMessages((m) => [...m, fridayMessage(data)])
      speakReply(data.reply)
    } catch (err) {
      if (err.name === 'AbortError') {
        setMessages((m) => [
          ...m,
          { role: 'friday', text: 'Stopped waiting for that answer.', meta: 'the server may still finish it' },
        ])
      } else {
        showError(err.message)
      }
    } finally {
      abortRef.current = null
      setBusy(false)
    }
  }

  async function sendVoice(blob) {
    setView('chat')
    setVoiceBusy(true)
    try {
      const form = new FormData()
      form.append('file', blob, 'recording')
      const data = await request(
        '/voice',
        { method: 'POST', body: form },
        "Couldn't understand that recording.",
      )
      setMessages((m) => [...m, { role: 'user', text: data.heard, voice: true }, fridayMessage(data)])
      speakReply(data.reply)
    } catch (err) {
      showError(err.message)
    } finally {
      setVoiceBusy(false)
    }
  }

  async function toggleMic() {
    if (recorder.recording) {
      const blob = await recorder.stop()
      if (blob && blob.size > 0) await sendVoice(blob)
      return
    }
    speaker.stop() // so Friday's own voice is not recorded
    try {
      await recorder.start()
    } catch (err) {
      showError(err.message)
    }
  }

  function submit(event) {
    event.preventDefault()
    const message = text.trim()
    if (!message || locked) return
    setText('')
    ask(message)
  }

  return (
    <div className="layout">
      <DocsPanel ask={ask} busy={locked} />

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
                <div className="empty">
                  Type, or click Talk. Try: what time is it, or: what&apos;s 18% of 2400
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`row ${m.role}${m.error ? ' error' : ''}`}>
                  <div className="bubble">{m.text}</div>
                  {m.voice && <div className="meta">heard from your voice</div>}
                  {m.meta && <div className="meta">{m.meta}</div>}
                  {m.sources?.length > 0 && <Sources sources={m.sources} />}
                </div>
              ))}
              {(busy || voiceBusy) && (
                <div className="row friday">
                  <div className="bubble">...</div>
                </div>
              )}
              <div ref={endRef} />
            </main>

            <div className="voice-bar">
              <label className="speak-toggle">
                <input
                  type="checkbox"
                  checked={speaker.enabled}
                  onChange={(e) => speaker.setEnabled(e.target.checked)}
                />
                Speak replies
              </label>
              {recorder.recording && (
                <span className="rec-note">
                  Recording... click Stop and send when you are done (60 seconds max).
                </span>
              )}
              {speaker.speaking && (
                <button type="button" className="mini" onClick={speaker.stop}>
                  Stop speaking
                </button>
              )}
            </div>

            <form className="composer" onSubmit={submit}>
              <button
                type="button"
                className={recorder.recording ? 'mic recording' : 'mic'}
                onClick={toggleMic}
                disabled={busy || voiceBusy}
              >
                {recorder.recording ? 'Stop and send' : 'Talk'}
              </button>
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={MAX_CHARS}
                placeholder="Type a message"
                disabled={voiceBusy || recorder.recording}
                autoFocus
              />
              {busy ? (
                <button type="button" className="stop" onClick={() => abortRef.current?.abort()}>
                  Stop
                </button>
              ) : (
                <button type="submit" disabled={!text.trim() || locked}>
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