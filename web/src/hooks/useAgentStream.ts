import { useCallback, useEffect, useRef, useState } from "react"
import type { AgentEvent } from "../types"
import type { LiveState } from "../lib/buildFeed"

type UseAgentStreamOptions = {
  authToken: string
  onDone: (result: string, timestamp: string, sessionId: string, runId: string) => void | Promise<void>
  onError: (message: string) => void
}

export function useAgentStream({ authToken, onDone, onError }: UseAgentStreamOptions) {
  const [streaming, setStreaming] = useState(false)
  const [liveState, setLiveState] = useState<LiveState | null>(null)
  const streamRef = useRef<EventSource | null>(null)
  const liveToolSeqRef = useRef(0)

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.close()
      streamRef.current = null
    }
    setStreaming(false)
  }, [])

  const resetLiveState = useCallback(() => {
    setLiveState(null)
  }, [])

  const startStream = useCallback(
    (sessionId: string, runId: string) => {
      if (streamRef.current) {
        streamRef.current.close()
      }

      const url = new URL(`/api/sessions/${sessionId}/stream`, window.location.origin)
      url.searchParams.set("run_id", runId)
      if (authToken) {
        url.searchParams.set("auth", authToken)
      }

      const source = new EventSource(url.toString())
      streamRef.current = source
      liveToolSeqRef.current = 0
      setStreaming(true)
      setLiveState({
        assistantText: "",
        thinkingText: "",
        timestamp: new Date().toISOString(),
        toolLines: [],
      })

      source.onmessage = (event) => {
        const parsed = JSON.parse(event.data) as AgentEvent

        if (parsed.type === "token") {
          const text = String(parsed.data?.text ?? "")
          if (!text) {
            return
          }
          setLiveState((prev) => ({
            assistantText: `${prev?.assistantText ?? ""}${text}`,
            thinkingText: prev?.thinkingText ?? "",
            timestamp: parsed.timestamp,
            toolLines: prev?.toolLines ?? [],
          }))
          return
        }

        if (parsed.type === "thinking") {
          const text = String(parsed.data?.text ?? "").trim()
          if (!text) {
            return
          }
          setLiveState((prev) => ({
            assistantText: prev?.assistantText ?? "",
            thinkingText: prev?.thinkingText
              ? `${prev.thinkingText}\n${text}`
              : text,
            timestamp: parsed.timestamp,
            toolLines: prev?.toolLines ?? [],
          }))
          return
        }

        if (parsed.type === "tool_start") {
          const name = String(parsed.data?.name ?? "tool")
          const id = `live-tool-${++liveToolSeqRef.current}`
          setLiveState((prev) => ({
            assistantText: prev?.assistantText ?? "",
            thinkingText: prev?.thinkingText ?? "",
            timestamp: parsed.timestamp,
            toolLines: [
              ...(prev?.toolLines ?? []),
              {
                id,
                label: `${name}: running...`,
                timestamp: parsed.timestamp,
              },
            ],
          }))
          return
        }

        if (parsed.type === "tool_progress") {
          const name = String(parsed.data?.name ?? "tool")
          const outputPreview = String(parsed.data?.output_preview ?? "").trim()
          const id = `live-tool-${++liveToolSeqRef.current}`
          setLiveState((prev) => ({
            assistantText: prev?.assistantText ?? "",
            thinkingText: prev?.thinkingText ?? "",
            timestamp: parsed.timestamp,
            toolLines: [
              ...(prev?.toolLines ?? []),
              {
                id,
                label: outputPreview ? `${name}: ${outputPreview}` : `${name}: running...`,
                url: parsed.data?.url ? String(parsed.data.url) : undefined,
                screenshot: parsed.data?.screenshot ? String(parsed.data.screenshot) : null,
                timestamp: parsed.timestamp,
              },
            ],
          }))
          return
        }

        if (parsed.type === "tool_end") {
          const name = String(parsed.data?.name ?? "tool")
          const outputPreview = String(parsed.data?.output_preview ?? "").trim()
          const id = `live-tool-${++liveToolSeqRef.current}`
          setLiveState((prev) => ({
            assistantText: prev?.assistantText ?? "",
            thinkingText: prev?.thinkingText ?? "",
            timestamp: parsed.timestamp,
            toolLines: [
              ...(prev?.toolLines ?? []),
              {
                id,
                label: outputPreview ? `${name}: ${outputPreview}` : `${name}: completed`,
                url: parsed.data?.url ? String(parsed.data.url) : undefined,
                screenshot: parsed.data?.screenshot ? String(parsed.data.screenshot) : null,
                timestamp: parsed.timestamp,
              },
            ],
          }))
          return
        }

        if (parsed.type === "done") {
          const result = String(parsed.data?.result ?? "")
          setStreaming(false)
          source.close()
          streamRef.current = null
          void Promise.resolve(onDone(result, parsed.timestamp, sessionId, runId)).catch((error) => {
            const message = error instanceof Error ? error.message : "Failed to reconcile completed run."
            onError(message)
          })
          return
        }

        if (parsed.type === "error") {
          setLiveState(null)
          setStreaming(false)
          onError(String(parsed.data?.error ?? "Agent error"))
          source.close()
          streamRef.current = null
        }
      }

      source.onerror = () => {
        onError("Stream disconnected.")
        setStreaming(false)
        source.close()
        streamRef.current = null
      }
    },
    [authToken, onDone, onError],
  )

  useEffect(() => stopStream, [stopStream])

  return {
    streaming,
    liveState,
    startStream,
    stopStream,
    resetLiveState,
  }
}
