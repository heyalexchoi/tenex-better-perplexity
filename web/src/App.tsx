import { useEffect, useMemo, useRef, useState } from "react"
import { ChatInput } from "./components/ChatInput"
import { MessageFeed } from "./components/MessageFeed"
import { ScreenshotModal } from "./components/ScreenshotModal"
import { StatusIndicator } from "./components/StatusIndicator"
import type { AgentEvent, FeedItem, Message, SessionStatus, ToolLine } from "./types"

const LOCAL_AUTH_KEY = "bp_auth_token"
const LOCAL_SESSION_KEY = "bp_session_id"

function buildFeed(messages: Message[], events: AgentEvent[]): FeedItem[] {
  const timeline: Array<
    | { type: "user"; id: string; timestamp: string; content: string }
    | { type: "assistant"; id: string; timestamp: string; content: string }
    | { type: "tool"; id: string; timestamp: string; line: ToolLine }
    | { type: "error"; id: string; timestamp: string; error: string }
  > = []

  for (const message of messages) {
    if (message.role === "tool") {
      let meta: Record<string, unknown> = {}
      try {
        meta = message.meta_json ? (JSON.parse(message.meta_json) as Record<string, unknown>) : {}
      } catch {
        meta = {}
      }
      const toolName = String(meta.tool_name ?? "tool")
      const outputPreview = message.content.trim()
      const label = outputPreview ? `${toolName}: ${outputPreview}` : `${toolName}: completed`
      timeline.push({
        type: "tool",
        id: message.id,
        timestamp: message.timestamp,
        line: {
          id: message.id,
          label,
          url: meta.url ? String(meta.url) : undefined,
          screenshot: meta.screenshot ? String(meta.screenshot) : null,
          timestamp: message.timestamp,
        },
      })
      continue
    }
    timeline.push({
      type: message.role === "assistant" ? "assistant" : "user",
      id: message.id,
      timestamp: message.timestamp,
      content: message.content,
    })
  }

  let stepCounter = 0
  let liveAssistantText = ""
  let liveTimestamp = ""
  const pendingToolStarts: Record<string, { id: string; timestamp: string }> = {}

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
      timeline.push({
        type: "tool",
        id: `event-${event.id ?? crypto.randomUUID()}-${stepCounter}`,
        timestamp: event.timestamp,
        line: {
          id: `event-${event.id ?? crypto.randomUUID()}-thinking-${stepCounter}`,
          label: `thinking: ${String(event.data.text ?? "").trim()}`,
          timestamp: event.timestamp,
        },
      })
      continue
    }
    if (event.type === "tool_start") {
      const name = String(event.data.name ?? "tool")
      pendingToolStarts[name] = {
        id: `event-${event.id ?? crypto.randomUUID()}-start`,
        timestamp: event.timestamp,
      }
      continue
    }
    if (event.type === "tool_end") {
      stepCounter += 1
      const outputPreview = String(event.data.output_preview ?? "").trim()
      const name = String(event.data.name ?? "tool")
      delete pendingToolStarts[name]
      timeline.push({
        type: "tool",
        id: `event-${event.id ?? crypto.randomUUID()}-${stepCounter}`,
        timestamp: event.timestamp,
        line: {
          id: `event-${event.id ?? crypto.randomUUID()}-tool-${stepCounter}`,
          label: outputPreview ? `${name}: ${outputPreview}` : `${name}: completed`,
          url: event.data.url ? String(event.data.url) : undefined,
          screenshot: event.data.screenshot ? String(event.data.screenshot) : null,
          timestamp: event.timestamp,
        },
      })
      continue
    }
    if (event.type === "error") {
      timeline.push({
        type: "error",
        id: `event-${event.id ?? crypto.randomUUID()}`,
        error: String(event.data.error ?? "Unexpected error"),
        timestamp: event.timestamp,
      })
    }
  }

  for (const [name, pending] of Object.entries(pendingToolStarts)) {
    timeline.push({
      type: "tool",
      id: pending.id,
      timestamp: pending.timestamp,
      line: {
        id: `${pending.id}-line`,
        label: `${name}: started...`,
        timestamp: pending.timestamp,
      },
    })
  }

  if (liveAssistantText.trim()) {
    timeline.push({
      type: "assistant",
      id: "live-assistant",
      content: liveAssistantText,
      timestamp: liveTimestamp || new Date().toISOString(),
    })
  }

  timeline.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

  const feed: FeedItem[] = []
  let assistantGroup:
    | {
        id: string
        timestamp: string
        content: string
        toolLines: ToolLine[]
      }
    | null = null

  const flushAssistantGroup = () => {
    if (!assistantGroup) {
      return
    }
    feed.push({
      kind: "assistant",
      id: assistantGroup.id,
      content: assistantGroup.content,
      toolLines: assistantGroup.toolLines.length ? assistantGroup.toolLines : undefined,
      timestamp: assistantGroup.timestamp,
    })
    assistantGroup = null
  }

  for (const item of timeline) {
    if (item.type === "user") {
      flushAssistantGroup()
      feed.push({
        kind: "user",
        id: item.id,
        content: item.content,
        timestamp: item.timestamp,
      })
      continue
    }
    if (item.type === "error") {
      flushAssistantGroup()
      feed.push({
        kind: "error",
        id: item.id,
        error: item.error,
        timestamp: item.timestamp,
      })
      continue
    }
    if (!assistantGroup) {
      assistantGroup = {
        id: `assistant-group-${item.id}`,
        timestamp: item.timestamp,
        content: "",
        toolLines: [],
      }
    }
    if (item.type === "tool") {
      assistantGroup.toolLines.push(item.line)
    } else if (item.type === "assistant") {
      assistantGroup.content = assistantGroup.content
        ? `${assistantGroup.content}\n${item.content}`
        : item.content
      assistantGroup.timestamp = item.timestamp
    }
  }
  flushAssistantGroup()
  return feed
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
    <div className="h-screen px-4 py-4 text-ink-900 md:px-6 md:py-6">
      <div className="mx-auto flex h-full w-full max-w-5xl flex-col gap-4">
        <header className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.4em] text-fog-400">
              Better Perplexity
            </p>
            <h1 className="font-display text-2xl text-ink-900 md:text-3xl">Browser Agent</h1>
          </div>
          <div className="flex items-center gap-2">
            <StatusIndicator status={status} />
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
          <section className="glass flex min-h-0 flex-1 flex-col rounded-3xl shadow-glow">
            <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-5 md:px-6">
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
            </div>
            <div className="sticky bottom-0 border-t border-fog-100 bg-white/75 p-3 backdrop-blur md:p-4">
              <ChatInput
                onSend={handleSend}
                onCancel={handleCancel}
                disabled={!sessionId || status === "running"}
                running={status === "running"}
              />
            </div>
          </section>
        )}
      </div>
      <ScreenshotModal src={activeScreenshot} onClose={() => setActiveScreenshot(null)} />
    </div>
  )
}
