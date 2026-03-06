import { useCallback, useEffect, useMemo, useState } from "react"
import type { SessionStatus } from "../types"
import { useAgentStream } from "./useAgentStream"
import { useSession } from "./useSession"

type ChatError = {
  source: "session" | "stream"
  message: string
  timestamp: string
}

export function useChatSession(authToken: string, authChecked: boolean) {
  const {
    sessionId,
    messages,
    loading,
    ensureSession,
    createNewSession,
    sendUserMessage,
    cancelRun,
  } = useSession(authToken)
  const [status, setStatus] = useState<SessionStatus>("idle")
  const [errors, setErrors] = useState<ChatError[]>([])

  const pushError = useCallback((source: ChatError["source"], message: string) => {
    setErrors((prev) => [...prev, { source, message, timestamp: new Date().toISOString() }])
  }, [])

  const clearErrors = useCallback(() => {
    setErrors([])
  }, [])

  const handleStreamDone = useCallback(
    async (_result: string, _timestamp: string, _id: string, _runId: string) => {
      setStatus("idle")
    },
    [],
  )

  const handleStreamError = useCallback(
    (message: string) => {
      pushError("stream", message)
      setStatus("error")
    },
    [pushError],
  )

  const { streaming, liveState, startStream, stopStream, resetLiveState } = useAgentStream({
    authToken,
    onDone: handleStreamDone,
    onError: handleStreamError,
  })

  const send = useCallback(
    async (text: string) => {
      clearErrors()
      resetLiveState()

      const { sessionId: resolvedSessionId, runId, error } = await sendUserMessage(text)
      if (error || !resolvedSessionId || !runId) {
        pushError("session", error ?? "Failed to send message.")
        setStatus("error")
        return
      }

      setStatus("running")
      startStream(resolvedSessionId, runId)
    },
    [clearErrors, pushError, resetLiveState, sendUserMessage, startStream],
  )

  const cancel = useCallback(async () => {
    stopStream()
    resetLiveState()
    await cancelRun()
    setStatus("idle")
  }, [cancelRun, resetLiveState, stopStream])

  const newSession = useCallback(async () => {
    stopStream()
    resetLiveState()
    clearErrors()
    const created = await createNewSession()
    setStatus(created.status)
  }, [clearErrors, createNewSession, resetLiveState, stopStream])

  useEffect(() => {
    if (!authChecked || sessionId) {
      return
    }
    resetLiveState()
    void (async () => {
      const resolved = await ensureSession()
      setStatus(resolved.status)
      if (resolved.status === "running" && resolved.activeRunId) {
        startStream(resolved.id, resolved.activeRunId)
      }
    })()
  }, [authChecked, ensureSession, resetLiveState, sessionId, startStream])

  const banner = useMemo(() => {
    if (!errors.length) {
      return null
    }
    return errors[errors.length - 1]?.message ?? null
  }, [errors])

  return {
    sessionId,
    messages,
    loading,
    status,
    banner,
    errors,
    streaming,
    liveState,
    send,
    cancel,
    newSession,
  }
}
