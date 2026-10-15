import { useEffect, useRef, useState } from 'react'
import './App.css'

const MAX_CHARS = 2000
const COULDNT_ANSWER = "Friday couldn't answer right now."
const CANT_REACH = "Can't reach Friday. Is the API running?"

async function askFriday(text) {
  let res
  try {
    res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
  } catch {
    throw new Error(CANT_REACH)
  }
  if (!res.ok) {
    let detail = COULDNT_ANSWER
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep the default message
    }
    throw new Error(detail)
  }
  return res.json()
}

function describe(data) {
  if (data.via === 'rule') return `skill: ${data.skill}`
  return data.provider ? `LLM: ${data.provider}` : 'LLM'
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  async function send(event) {
    event.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    setText('')
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', text: message }])
    try {
      const data = await askFriday(message)
      setMessages((m) => [
        ...m,
        { role: 'friday', text: data.reply, meta: describe(data) },
      ])
    } catch (err) {
      setMessages((m) => [...m, { role: 'friday', text: err.message, error: true }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Friday</h1>
        <p>Typed chat. Same brain as the voice loop and Telegram.</p>
      </header>

      <main className="messages">
        {messages.length === 0 && (
          <div className="empty">Try: what time is it, or: what&apos;s 18% of 2400</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`row ${m.role}${m.error ? ' error' : ''}`}>
            <div className="bubble">{m.text}</div>
            {m.meta && <div className="meta">{m.meta}</div>}
          </div>
        ))}
        {busy && (
          <div className="row friday">
            <div className="bubble">...</div>
          </div>
        )}
        <div ref={endRef} />
      </main>

      <form className="composer" onSubmit={send}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={MAX_CHARS}
          placeholder="Type a message"
          autoFocus
        />
        <button type="submit" disabled={busy || !text.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}