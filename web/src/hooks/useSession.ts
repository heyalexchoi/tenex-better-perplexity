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

  const fetchSession = useCallback(
    async (id: string) => {
      const res = await apiFetch(`/api/sessions/${id}`, {}, authToken)
      if (!res.ok) return null
      return (await res.json()) as Record<string, unknown>
    },
    [authToken],
  )

  const sessionResult = (data: Record<string, unknown>): EnsureSessionResult => ({
    id: data.id as string,
    status: (data.status as SessionStatus) ?? "idle",
    activeRunId: (data.active_run_id as string | null) ?? null,
  })

  const createNewSession = useCallback(async (): Promise<EnsureSessionResult> => {
    const createRes = await apiFetch("/api/sessions", { method: "POST" }, authToken)
    if (!createRes.ok) throw new Error("Failed to create session")
    const session = await createRes.json()
    localStorage.setItem(LOCAL_SESSION_KEY, session.id)
    setSessionId(session.id)
    setMessages([])
    return sessionResult(session)
  }, [authToken])

  const ensureSession = useCallback(async (): Promise<EnsureSessionResult> => {
    setLoading(true)
    try {
      const existing = localStorage.getItem(LOCAL_SESSION_KEY)
      if (existing) {
        const data = await fetchSession(existing)
        if (data) {
          setSessionId(data.id as string)
          setMessages((data.messages as Message[]) ?? [])
          return sessionResult(data)
        }
      }
      return await createNewSession()
    } finally {
      setLoading(false)
    }
  }, [createNewSession, fetchSession])

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

  const refreshMessages = useCallback(async () => {
    if (!sessionId) return
    const data = await fetchSession(sessionId)
    if (data) {
      setMessages((data.messages as Message[]) ?? [])
    }
  }, [fetchSession, sessionId])

  return {
    sessionId,
    messages,
    loading,
    ensureSession,
    sendUserMessage,
    cancelRun,
    createNewSession,
    refreshMessages,
  }
}
