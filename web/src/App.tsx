import { useEffect, useMemo, useRef, useState } from "react"
import { ChatInput } from "./components/ChatInput"
import { MessageFeed } from "./components/MessageFeed"
import { ScreenshotModal } from "./components/ScreenshotModal"
import { StatusIndicator } from "./components/StatusIndicator"
import type { AgentEvent, FeedItem, Message, SessionStatus } from "./types"

const LOCAL_AUTH_KEY = "bp_auth_token"
const LOCAL_SESSION_KEY = "bp_session_id"

function buildFeed(messages: Message[], events: AgentEvent[]): FeedItem[] {
  const messageItems: FeedItem[] = messages.map((message) => {
    if (message.role === "tool") {
      let meta: Record<string, unknown> = {}
      try {
        meta = message.meta_json ? (JSON.parse(message.meta_json) as Record<string, unknown>) : {}
      } catch {
        meta = {}
      }
      return {
        kind: "step",
        id: message.id,
        step: 0,
        action: `Tool: ${String(meta.tool_name ?? "tool")}`,
        url: meta.url ? String(meta.url) : undefined,
        screenshot: meta.screenshot ? String(meta.screenshot) : null,
        timestamp: message.timestamp,
      }
    }
    return {
      kind: message.role === "assistant" ? "assistant" : "user",
      id: message.id,
      content: message.content,
      timestamp: message.timestamp,
    }
  })

  const eventItems: FeedItem[] = []
  let stepCounter = 0
  let liveAssistantText = ""
  let liveTimestamp = ""

  for (const event of events) {
    if (event.type === "token") {
      liveAssistantText += String(event.data.text ?? "")
      liveTimestamp = event.timestamp
      continue
    }
    if (event.type === "done") {
      const result = String(event.data.result ?? "").trim()
      if (result) {
        liveAssistantText = result
      }
      liveTimestamp = event.timestamp
      continue
    }
    if (event.type === "thinking") {
      stepCounter += 1
      eventItems.push({
        kind: "step",
        id: `event-${event.id ?? crypto.randomUUID()}`,
        step: stepCounter,
        action: `Thinking: ${String(event.data.text ?? "").trim()}`,
        timestamp: event.timestamp,
      })
      continue
    }
    if (event.type === "tool_start") {
      stepCounter += 1
      eventItems.push({
        kind: "step",
        id: `event-${event.id ?? crypto.randomUUID()}`,
        step: stepCounter,
        action: `Tool start: ${String(event.data.name ?? "tool")}`,
        timestamp: event.timestamp,
      })
      continue
    }
    if (event.type === "tool_end") {
      stepCounter += 1
      eventItems.push({
        kind: "step",
        id: `event-${event.id ?? crypto.randomUUID()}`,
        step: stepCounter,
        action: `Tool done: ${String(event.data.name ?? "tool")}`,
        url: event.data.url ? String(event.data.url) : undefined,
        screenshot: event.data.screenshot ? String(event.data.screenshot) : null,
        timestamp: event.timestamp,
      })
      continue
    }
    if (event.type === "error") {
      eventItems.push({
        kind: "error",
        id: `event-${event.id ?? crypto.randomUUID()}`,
        error: String(event.data.error ?? "Unexpected error"),
        timestamp: event.timestamp,
      })
    }
  }

  if (liveAssistantText.trim()) {
    eventItems.push({
      kind: "assistant",
      id: "live-assistant",
      content: liveAssistantText,
      timestamp: liveTimestamp || new Date().toISOString(),
    })
  }

  return [...messageItems, ...eventItems].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  )
}

export default function App() {
  const [authToken, setAuthToken] = useState<string>("")
  const [authChecked, setAuthChecked] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [status, setStatus] = useState<SessionStatus>("idle")
  const [banner, setBanner] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [activeScreenshot, setActiveScreenshot] = useState<string | null>(null)

  const streamRef = useRef<EventSource | null>(null)
  const feedEndRef = useRef<HTMLDivElement | null>(null)

  const feed = useMemo(() => buildFeed(messages, events), [messages, events])

  const apiFetch = async (path: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers)
    if (!headers.has("content-type") && options.method && options.method !== "GET") {
      headers.set("content-type", "application/json")
    }
    if (authToken) {
      headers.set("x-auth", authToken)
    }
    return fetch(path, { ...options, headers })
  }

  const checkAuth = async (token: string, showErrors = true) => {
    setAuthError(null)
    const res = await fetch("/api/auth/check", {
      method: "POST",
      headers: token ? { "x-auth": token } : {},
    })
    if (res.ok) {
      setAuthToken(token)
      if (token) {
        localStorage.setItem(LOCAL_AUTH_KEY, token)
      } else {
        localStorage.removeItem(LOCAL_AUTH_KEY)
      }
      setAuthChecked(true)
      return true
    }
    if (showErrors) {
      setAuthError("Password incorrect. Try again.")
    }
    setAuthChecked(false)
    return false
  }

  const ensureSession = async () => {
    setLoading(true)
    const existing = localStorage.getItem(LOCAL_SESSION_KEY)
    if (existing) {
      const res = await apiFetch(`/api/sessions/${existing}`)
      if (res.ok) {
        const data = await res.json()
        setSessionId(data.id)
        setStatus(data.status)
        setMessages(data.messages ?? [])
        setEvents([])
        setLoading(false)
        return existing
      }
    }

    const createRes = await apiFetch("/api/sessions", { method: "POST" })
    const session = await createRes.json()
    localStorage.setItem(LOCAL_SESSION_KEY, session.id)
    setSessionId(session.id)
    setStatus(session.status)
    setMessages([])
    setEvents([])
    setLoading(false)
    return session.id
  }

  const startStream = (id: string) => {
    if (streamRef.current) {
      streamRef.current.close()
    }
    const url = new URL(`/api/sessions/${id}/stream`, window.location.origin)
    if (authToken) {
      url.searchParams.set("auth", authToken)
    }
    const source = new EventSource(url.toString())
    streamRef.current = source
    setStreaming(true)

    source.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as AgentEvent
      if (parsed.type === "done") {
        const result = String(parsed.data?.result ?? "").trim()
        if (result) {
          setMessages((prev) => [
            ...prev,
            {
              id: `local-${crypto.randomUUID()}`,
              session_id: id,
              role: "assistant",
              content: result,
              timestamp: parsed.timestamp,
            },
          ])
        }
        setEvents([])
        setStatus("idle")
        setStreaming(false)
        source.close()
        return
      }
      if (parsed.type === "error") {
        setEvents((prev) => [...prev, parsed])
        setStatus("error")
        setBanner(String(parsed.data?.error ?? "Agent error"))
        setStreaming(false)
        source.close()
        return
      }
      setEvents((prev) => [...prev, parsed])
    }
    source.onerror = () => {
      setBanner("Stream disconnected.")
      setStreaming(false)
      source.close()
    }
  }

  const handleSend = async (text: string) => {
    setBanner(null)
    const id = sessionId ?? (await ensureSession())
    setEvents([])
    setStatus("running")

    const res = await apiFetch(`/api/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: text }),
    })
    if (!res.ok) {
      if (res.status === 409) {
        setBanner("Agent is already running.")
      } else if (res.status === 401) {
        setBanner("Unauthorized. Check your password.")
      } else {
        setBanner("Failed to send message.")
      }
      setStatus("error")
      return
    }
    const message = (await res.json()) as Message
    setMessages((prev) => [...prev, message])
    startStream(id)
  }

  const handleCancel = async () => {
    if (!sessionId) {
      return
    }
    await apiFetch(`/api/sessions/${sessionId}`, { method: "DELETE" })
    setStatus("idle")
    setStreaming(false)
  }

  useEffect(() => {
    const saved = localStorage.getItem(LOCAL_AUTH_KEY) ?? ""
    if (!saved) {
      setAuthChecked(false)
      setAuthError(null)
      return
    }
    checkAuth(saved, false)
  }, [])

  useEffect(() => {
    if (!authChecked) {
      return
    }
    ensureSession()
  }, [authChecked])

  useEffect(() => {
    if (sessionId && status === "running" && !streaming) {
      startStream(sessionId)
    }
  }, [sessionId, status, streaming])

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.close()
      }
    }
  }, [])

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [feed.length])

  return (
    <div className="min-h-screen px-6 py-10 text-ink-900">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.4em] text-fog-400">
              Better Perplexity
            </p>
            <h1 className="font-display text-3xl text-ink-900 md:text-4xl">Browser Agent</h1>
          </div>
          <div className="flex items-center gap-3">
            <StatusIndicator status={status} />
            {sessionId ? (
              <span className="text-xs uppercase tracking-[0.2em] text-fog-400">Session {sessionId.slice(0, 6)}</span>
            ) : null}
          </div>
        </header>

        {!authChecked ? (
          <div className="glass mx-auto w-full max-w-lg rounded-3xl p-8 shadow-glow">
            <h2 className="font-display text-2xl">Enter Access Password</h2>
            <p className="mt-2 text-sm text-fog-400">
              Single-field login for the private demo environment.
            </p>
            <form
              className="mt-6 flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault()
                const form = event.currentTarget
                const data = new FormData(form)
                const token = String(data.get("password") || "")
                checkAuth(token, true)
              }}
            >
              <input
                name="password"
                type="password"
                placeholder="Password"
                className="rounded-xl border border-fog-200 bg-white/80 px-4 py-3 text-sm outline-none focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20"
              />
              {authError ? <div className="text-sm text-red-500">{authError}</div> : null}
              <button
                type="submit"
                className="rounded-xl bg-ink-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-ink-800"
              >
                Unlock
              </button>
            </form>
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <section className="glass flex min-h-[60vh] flex-col gap-6 rounded-3xl p-6 shadow-glow">
              {banner ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {banner}
                </div>
              ) : null}
              {feed.length ? (
                <MessageFeed items={feed} onOpenScreenshot={setActiveScreenshot} />
              ) : (
                <div className="flex flex-1 items-center justify-center text-sm text-fog-400">
                  {loading ? "Loading session..." : "Start by asking the agent to browse or research something."}
                </div>
              )}
              <div ref={feedEndRef} />
            </section>
            <aside className="flex flex-col gap-4">
              <div className="glass rounded-3xl p-6 shadow-glow">
                <h3 className="text-sm font-semibold uppercase tracking-[0.3em] text-fog-400">Session</h3>
                <div className="mt-4 space-y-2 text-sm text-ink-800">
                  <div>Status: {status}</div>
                  <div>Messages: {messages.length}</div>
                  <div>Events: {events.length}</div>
                  <div>Streaming: {streaming ? "Yes" : "No"}</div>
                </div>
              </div>
              <ChatInput onSend={handleSend} onCancel={handleCancel} disabled={!sessionId || status === "running"} running={status === "running"} />
            </aside>
          </div>
        )}
      </div>
      <ScreenshotModal src={activeScreenshot} onClose={() => setActiveScreenshot(null)} />
    </div>
  )
}
