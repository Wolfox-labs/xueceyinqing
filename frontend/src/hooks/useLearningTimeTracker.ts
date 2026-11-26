import { useEffect, useRef } from 'react'
import { sendLearningHeartbeat, sendLearningHeartbeatKeepalive } from '../api/activity'

const HEARTBEAT_MS = 30_000
const MAX_TICK_SECONDS = 30

export function useLearningTimeTracker(enabled: boolean) {
  const pendingSeconds = useRef(0)
  const lastTickAt = useRef(Date.now())
  const active = useRef(document.visibilityState === 'visible')

  useEffect(() => {
    if (!enabled) return

    pendingSeconds.current = 0
    lastTickAt.current = Date.now()
    active.current = document.visibilityState === 'visible'

    const captureElapsed = () => {
      const now = Date.now()
      const elapsed = Math.floor((now - lastTickAt.current) / 1000)
      lastTickAt.current = now
      if (active.current && elapsed > 0) {
        pendingSeconds.current += Math.min(elapsed, MAX_TICK_SECONDS)
      }
    }

    const flush = (beacon = false) => {
      captureElapsed()
      const seconds = Math.floor(pendingSeconds.current)
      if (seconds <= 0) return
      pendingSeconds.current -= seconds
      const payloadSeconds = Math.min(seconds, 120)
      if (beacon) {
        sendLearningHeartbeatKeepalive(payloadSeconds)
      } else {
        void sendLearningHeartbeat(payloadSeconds).catch(() => {
          pendingSeconds.current += payloadSeconds
        })
      }
    }

    const interval = window.setInterval(() => flush(false), HEARTBEAT_MS)
    const onVisibilityChange = () => {
      const nextVisible = document.visibilityState === 'visible'
      if (!nextVisible) {
        flush(true)
      }
      active.current = nextVisible
      lastTickAt.current = Date.now()
    }
    const onBeforeUnload = () => flush(true)

    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('beforeunload', onBeforeUnload)

    return () => {
      flush(false)
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('beforeunload', onBeforeUnload)
    }
  }, [enabled])
}