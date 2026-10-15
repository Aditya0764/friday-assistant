import { useEffect, useRef, useState } from 'react'
import { postJson, request } from './api.js'

const ADD_FAILED = "Couldn't add that document."
const LOAD_FAILED = "Couldn't load the documents."
const ADDING_NOTE =
  'Adding... the first document loads the embedding model, so it can take a minute.'

export default function DocsPanel({ ask, busy }) {
  const [docs, setDocs] = useState([])
  const [note, setNote] = useState(null) // { kind: 'ok' | 'error' | 'busy', text }
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [pasted, setPasted] = useState('')
  const fileRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    request('/documents', {}, LOAD_FAILED)
      .then((list) => {
        if (!cancelled) setDocs(list)
      })
      .catch((err) => {
        if (!cancelled) setNote({ kind: 'error', text: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function reload() {
    setDocs(await request('/documents', {}, LOAD_FAILED))
  }

  async function addDoc(makeRequest) {
    setAdding(true)
    setNote({ kind: 'busy', text: ADDING_NOTE })
    try {
      const doc = await makeRequest()
      setNote({ kind: 'ok', text: `Added ${doc.name} (${doc.chunks} chunks).` })
      await reload()
      return true
    } catch (err) {
      setNote({ kind: 'error', text: err.message })
      return false
    } finally {
      setAdding(false)
    }
  }

  async function upload(event) {
    const file = event.target.files[0]
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    await addDoc(() => request('/documents', { method: 'POST', body: form }, ADD_FAILED))
    if (fileRef.current) fileRef.current.value = ''
  }

  async function addPasted(event) {
    event.preventDefault()
    if (!pasted.trim() || adding) return
    const ok = await addDoc(() =>
      postJson('/documents/text', { name, text: pasted }, { fallback: ADD_FAILED }),
    )
    if (ok) {
      setName('')
      setPasted('')
    }
  }

  return (
    <aside className="docs">
      <h2>Documents</h2>
      <p className="hint">
        Questions search all of them. &quot;Read it to me&quot; reads the latest one.
      </p>

      <label className="field-label" htmlFor="file">
        Upload a PDF, .txt or .md
      </label>
      <input
        id="file"
        type="file"
        accept=".pdf,.txt,.md"
        onChange={upload}
        disabled={adding}
        ref={fileRef}
      />

      <form onSubmit={addPasted} className="paste">
        <label className="field-label" htmlFor="paste-name">
          Or paste text
        </label>
        <input
          id="paste-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
          placeholder="Name (optional)"
        />
        <textarea
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          maxLength={200000}
          rows={5}
          placeholder="Paste the document text here"
        />
        <button type="submit" disabled={adding || !pasted.trim()}>
          Add pasted text
        </button>
      </form>

      {note && (
        <div className={`note ${note.kind}`} role="status">
          {note.text}
        </div>
      )}

      <div className="read-buttons">
        <button onClick={() => ask('read it to me')} disabled={busy || docs.length === 0}>
          Read it to me
        </button>
        <button onClick={() => ask('keep reading')} disabled={busy || docs.length === 0}>
          Keep reading
        </button>
      </div>

      <ul className="doc-list">
        {docs.length === 0 && <li className="doc-meta">No documents yet.</li>}
        {docs.map((d, i) => (
          <li key={d.id}>
            <span className="doc-name">{d.name}</span>
            <span className="doc-meta">
              {d.chunks} {d.chunks === 1 ? 'chunk' : 'chunks'}
              {i === 0 ? ' · latest' : ''}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  )
}