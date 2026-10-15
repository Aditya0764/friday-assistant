import { useRef, useState } from 'react'

const NO_RECORDING = "This browser can't record audio."
const MIC_BLOCKED = "Couldn't use the microphone. Allow it in the browser and try again."

// Click-to-talk recording. start() asks for the mic and begins; stop() ends and
// resolves with the recorded audio (a Blob), or null if nothing was recording.
export function useRecorder() {
  const [recording, setRecording] = useState(false)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const resolveRef = useRef(null)

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error(NO_RECORDING)
    }
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      throw new Error(MIC_BLOCKED, { cause: err })
    }
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop()) // releases the mic
      setRecording(false)
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      resolveRef.current?.(blob)
      resolveRef.current = null
    }
    recorderRef.current = recorder
    recorder.start()
    setRecording(true)
  }

  function stop() {
    return new Promise((resolve) => {
      const recorder = recorderRef.current
      if (!recorder || recorder.state === 'inactive') {
        resolve(null)
        return
      }
      resolveRef.current = resolve
      recorder.stop()
    })
  }

  return { recording, start, stop }
}