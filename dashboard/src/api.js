const COULDNT_ANSWER = "Friday couldn't answer right now."
const CANT_REACH = "Can't reach Friday. Is the API running?"

// One place for fetch + error handling. Throws Error(message) with a text that is safe to show.
// A cancelled request throws the browser's own AbortError so callers can tell it apart.
export async function request(url, options = {}, fallback = COULDNT_ANSWER) {
  let res
  try {
    res = await fetch(url, options)
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error(CANT_REACH, { cause: err })
  }
  if (!res.ok) {
    let detail = fallback
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep the fallback message
    }
    throw new Error(detail)
  }
  return res.json()
}

export function postJson(url, body, { signal, fallback } = {}) {
  return request(
    url,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    },
    fallback,
  )
}