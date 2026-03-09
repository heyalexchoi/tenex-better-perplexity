import { useCallback, useEffect, useRef, useState } from "react"
import type { AgentEvent } from "../types"
import type { LiveState } from "../lib/buildFeed"

type StreamCallbacks = {
  onDone: () => void | Promise<void>
  onError: (message: string) => void
}

export function useAgentStream(authToken: string) {
  const [liveState, setLiveState] = useState<LiveState | null>(null)
  const streamRef = useRef<EventSource | null>(null)
  const liveToolSeqRef = useRef(0)

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.close()
      streamRef.current = null
    }
  }, [])

  const resetLiveState = useCallback(() => {
    setLiveState(null)
  }, [])

  const startStream = useCallback(
    (sessionId: string, runId: string, { onDone, onError }: StreamCallbacks) => {
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
          if (!text) return
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
          if (!text) return
          setLiveState((prev) => ({
            assistantText: prev?.assistantText ?? "",
            thinkingText: prev?.thinkingText ? `${prev.thinkingText}\n${text}` : text,
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
            toolLines: [...(prev?.toolLines ?? []), { id, label: `${name}: running...`, timestamp: parsed.timestamp }],
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
          source.close()
          streamRef.current = null
          void Promise.resolve(onDone()).catch((err) => {
            onError(err instanceof Error ? err.message : "Failed to reconcile completed run.")
          })
          return
        }

        if (parsed.type === "error") {
          setLiveState(null)
          onError(String(parsed.data?.error ?? "Agent error"))
          source.close()
          streamRef.current = null
        }
      }

      source.onerror = () => {
        onError("Stream disconnected.")
        source.close()
        streamRef.current = null
      }
    },
    [authToken],
  )

  useEffect(() => stopStream, [stopStream])

  return { liveState, startStream, stopStream, resetLiveState }
}
