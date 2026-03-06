import { useCallback, useState } from "react"
import { apiFetch } from "../lib/api"
import type { CreateMessageResponse, Message, SessionStatus } from "../types"

const LOCAL_SESSION_KEY = "bp_session_id"

type EnsureSessionResult = {
  id: string
  status: SessionStatus
  activeRunId: string | null
}

type SendMessageResult = {
  sessionId: string | null
  runId: string | null
  error: string | null
}

export function useSession(authToken: string) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)

  const createNewSession = useCallback(async (): Promise<EnsureSessionResult> => {
    const createRes = await apiFetch("/api/sessions", { method: "POST" }, authToken)
    const session = await createRes.json()
    localStorage.setItem(LOCAL_SESSION_KEY, session.id)
    setSessionId(session.id)
    setMessages([])
    return {
      id: session.id as string,
      status: (session.status as SessionStatus) ?? "idle",
      activeRunId: (session.active_run_id as string | null) ?? null,
    }
  }, [authToken])

  const ensureSession = useCallback(async (): Promise<EnsureSessionResult> => {
    setLoading(true)
    const existing = localStorage.getItem(LOCAL_SESSION_KEY)
    if (existing) {
      const res = await apiFetch(`/api/sessions/${existing}`, {}, authToken)
      if (res.ok) {
        const data = await res.json()
        setSessionId(data.id)
        setMessages(data.messages ?? [])
        setLoading(false)
        return {
          id: data.id as string,
          status: (data.status as SessionStatus) ?? "idle",
          activeRunId: (data.active_run_id as string | null) ?? null,
        }
      }
    }

    const session = await createNewSession()
    setLoading(false)
    return session
  }, [authToken, createNewSession])

  const sendUserMessage = useCallback(
    async (text: string): Promise<SendMessageResult> => {
      const resolved = sessionId ? { id: sessionId } : await ensureSession()
      const id = resolved.id

      const res = await apiFetch(
        `/api/sessions/${id}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ content: text }),
        },
        authToken,
      )

      if (!res.ok) {
        if (res.status === 409) {
          return { sessionId: null, runId: null, error: "Agent is already running." }
        }
        if (res.status === 401) {
          return { sessionId: null, runId: null, error: "Unauthorized. Check your password." }
        }
        return { sessionId: null, runId: null, error: "Failed to send message." }
      }

      const payload = (await res.json()) as CreateMessageResponse
      setMessages((prev) => [...prev, payload.user_message])
      return { sessionId: id, runId: payload.run_id, error: null }
    },
    [authToken, ensureSession, sessionId],
  )

  const cancelRun = useCallback(async () => {
    if (!sessionId) {
      return
    }
    await apiFetch(`/api/sessions/${sessionId}`, { method: "DELETE" }, authToken)
  }, [authToken, sessionId])

  return {
    sessionId,
    messages,
    loading,
    ensureSession,
    sendUserMessage,
    cancelRun,
    createNewSession,
  }
}
