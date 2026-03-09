import { useCallback, useEffect, useState } from "react"
import type { SessionStatus } from "../types"
import { useAgentStream } from "./useAgentStream"
import { useSession } from "./useSession"

export function useChatSession(authToken: string, authChecked: boolean) {
  const {
    sessionId,
    messages,
    loading,
    ensureSession,
    createNewSession,
    sendUserMessage,
    cancelRun,
    refreshMessages,
  } = useSession(authToken)
  const [status, setStatus] = useState<SessionStatus>("idle")
  const [error, setError] = useState<string | null>(null)

  const { liveState, startStream, stopStream, resetLiveState } = useAgentStream(authToken)

  const streamCallbacks = useCallback(
    () => ({
      onDone: async () => {
        await refreshMessages()
        resetLiveState()
        setStatus("idle")
      },
      onError: (message: string) => {
        setError(message)
        setStatus("error")
      },
    }),
    [refreshMessages, resetLiveState],
  )

  const send = useCallback(
    async (text: string) => {
      setError(null)
      resetLiveState()

      const { sessionId: resolvedSessionId, runId, error: sendError } = await sendUserMessage(text)
      if (sendError || !resolvedSessionId || !runId) {
        setError(sendError ?? "Failed to send message.")
        setStatus("error")
        return
      }

      setStatus("running")
      startStream(resolvedSessionId, runId, streamCallbacks())
    },
    [resetLiveState, sendUserMessage, startStream, streamCallbacks],
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
    setError(null)
    const created = await createNewSession()
    setStatus(created.status)
  }, [createNewSession, resetLiveState, stopStream])

  useEffect(() => {
    if (!authChecked || sessionId) return
    resetLiveState()
    void (async () => {
      const resolved = await ensureSession()
      setStatus(resolved.status)
      if (resolved.status === "running" && resolved.activeRunId) {
        startStream(resolved.id, resolved.activeRunId, streamCallbacks())
      }
    })()
  }, [authChecked, ensureSession, resetLiveState, sessionId, startStream, streamCallbacks])

  return {
    sessionId,
    messages,
    loading,
    status,
    error,
    liveState,
    send,
    cancel,
    newSession,
  }
}
