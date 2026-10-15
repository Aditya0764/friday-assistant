import { useRef, useState } from 'react'
import { postJsonForBlob } from './api.js'

const MAX_SPEAK_CHARS = 3000
const SPEAK_FAILED = "Couldn't make the spoken reply."
const SOUND_BLOCKED = 'The browser blocked the sound. Click the page once and try again.'

// Speaks replies: asks the API for a WAV (/speak) and plays it in the browser.
// speak() returns a message to show when something went wrong, or '' when all is fine.
export function useSpeaker() {
  const [enabled, setEnabledState] = useState(true)
  const [speaking, setSpeaking] = useState(false)
  const enabledRef = useRef(true)
  const audioRef = useRef(null)
  const urlRef = useRef(null)
  const requestRef = useRef(null)

  function stop() {
    requestRef.current?.abort()
    requestRef.current = null
    const audio = audioRef.current
    audioRef.current = null
    if (audio) {
      audio.onended = null
      audio.onerror = null
      audio.pause()
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
    setSpeaking(false)
  }

  function setEnabled(value) {
    enabledRef.current = value
    setEnabledState(value)
    if (!value) stop()
  }

  async function speak(text) {
    stop()
    const clean = (text || '').trim()
    if (!enabledRef.current || !clean) return ''
    const controller = new AbortController()
    requestRef.current = controller
    setSpeaking(true)
    try {
      const blob = await postJsonForBlob(
        '/speak',
        { text: clean.slice(0, MAX_SPEAK_CHARS) },
        { signal: controller.signal, fallback: SPEAK_FAILED },
      )
      if (requestRef.current !== controller) return '' // stopped while waiting
      requestRef.current = null
      const url = URL.createObjectURL(blob)
      urlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      const finished = () => {
        if (audioRef.current === audio) stop()
      }
      audio.onended = finished
      audio.onerror = finished
      await audio.play()
      return ''
    } catch (err) {
      if (err.name === 'AbortError') return ''
      stop()
      return err.name === 'NotAllowedError' ? SOUND_BLOCKED : err.message
    }
  }

  return { enabled, setEnabled, speaking, speak, stop }
}