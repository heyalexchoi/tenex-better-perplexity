import { useEffect, useMemo, useRef, useState } from "react"
import { ChatInput } from "./components/ChatInput"
import { MessageFeed } from "./components/MessageFeed"
import { ScreenshotModal } from "./components/ScreenshotModal"
import { StatusIndicator } from "./components/StatusIndicator"
import { useAuth } from "./hooks/useAuth"
import { useChatSession } from "./hooks/useChatSession"
import { buildFeed } from "./lib/buildFeed"

export default function App() {
  const { authToken, authChecked, authError, checkAuth } = useAuth()
  const { sessionId, messages, status, error, loading, liveState, send, cancel, newSession } =
    useChatSession(authToken, authChecked)

  const [activeScreenshot, setActiveScreenshot] = useState<string | null>(null)
  const feedEndRef = useRef<HTMLDivElement | null>(null)

  const feed = useMemo(() => buildFeed(messages, liveState), [messages, liveState])

  const handleSend = async (text: string) => send(text)

  const handleCancel = async () => cancel()

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
            <button
              type="button"
              onClick={() => void newSession()}
              className="rounded-xl border border-fog-200 bg-white/80 px-3 py-2 text-xs font-semibold text-ink-800 transition hover:bg-white disabled:opacity-50"
              disabled={!authChecked || status === "running"}
            >
              New Session
            </button>
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
                void checkAuth(token, true)
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
              {error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
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
