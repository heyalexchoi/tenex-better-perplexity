import type { AssistantPart, FeedItem, Message, ToolLine } from "../types"

export type LiveState = {
  assistantText: string
  thinkingText: string
  timestamp: string
  toolLines: ToolLine[]
}

export function buildFeed(messages: Message[], live: LiveState | null): FeedItem[] {
  const previewText = (value: string, limit = 200) => {
    const text = value.trim()
    if (text.length <= limit) {
      return text
    }
    return `${text.slice(0, limit)}...`
  }

  const timeline: Array<
    | { type: "user"; id: string; timestamp: string; content: string; seq: number }
    | { type: "assistant"; id: string; timestamp: string; content: string; seq: number }
    | {
        type: "tool_group"
        id: string
        timestamp: string
        seq: number
        label: string
        lines: ToolLine[]
      }
  > = []

  for (const [seq, message] of messages.entries()) {
    if (message.role === "tool") {
      let meta: Record<string, unknown> = {}
      try {
        meta = message.meta_json ? (JSON.parse(message.meta_json) as Record<string, unknown>) : {}
      } catch {
        meta = {}
      }

      const report = (meta.report as Record<string, unknown> | undefined) ?? undefined
      const steps = Array.isArray(report?.steps) ? report.steps : []
      const baseSeq = seq * 1000
      const stepLines: ToolLine[] = []

      for (const [idx, rawStep] of steps.entries()) {
        if (!rawStep || typeof rawStep !== "object") {
          continue
        }
        const step = rawStep as Record<string, unknown>
        const action = String(step.action ?? "").trim() || "step completed"
        const stepNumber = step.step ?? idx + 1
        stepLines.push({
          id: `${message.id}-step-${idx}`,
          label: `Browser step ${stepNumber}: ${action}`,
          url: step.url ? String(step.url) : undefined,
          screenshot: step.screenshot ? String(step.screenshot) : null,
          timestamp: message.timestamp,
        })
      }

      const outputPreview = previewText(message.content, 200)
      timeline.push({
        type: "tool_group",
        id: message.id,
        timestamp: message.timestamp,
        seq: baseSeq + 999,
        label: outputPreview ? `Browser task completed: ${outputPreview}` : "Browser task completed.",
        lines: stepLines,
      })
      continue
    }

    timeline.push({
      type: message.role === "assistant" ? "assistant" : "user",
      id: message.id,
      timestamp: message.timestamp,
      seq,
      content: message.content,
    })
  }

  timeline.sort((a, b) => {
    const tsDelta = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    return tsDelta !== 0 ? tsDelta : a.seq - b.seq
  })

  const feed: FeedItem[] = []
  let assistantGroup:
    | {
        id: string
        timestamp: string
        parts: AssistantPart[]
      }
    | null = null

  const flushAssistantGroup = () => {
    if (!assistantGroup) {
      return
    }

    feed.push({
      kind: "assistant",
      id: assistantGroup.id,
      parts: assistantGroup.parts,
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

    if (item.type === "assistant" && !item.content.trim()) {
      continue
    }

    if (!assistantGroup) {
      assistantGroup = {
        id: item.type === "assistant" ? item.id : `assistant-group-${item.id}`,
        timestamp: item.timestamp,
        parts: [],
      }
    }

    if (item.type === "tool_group") {
      assistantGroup.parts.push({
        kind: "tool_group",
        id: item.id,
        label: item.label,
        lines: item.lines,
      })
      assistantGroup.timestamp = item.timestamp
      continue
    }

    const lastPart = assistantGroup.parts[assistantGroup.parts.length - 1]
    if (lastPart?.kind === "text") {
      lastPart.text = lastPart.text ? `${lastPart.text}\n${item.content}` : item.content
    } else {
      assistantGroup.parts.push({ kind: "text", text: item.content })
    }
    assistantGroup.timestamp = item.timestamp
  }

  flushAssistantGroup()

  if (live && (live.assistantText.trim() || live.thinkingText.trim() || live.toolLines.length)) {
    const parts: AssistantPart[] = []
    if (live.thinkingText.trim()) {
      parts.push({ kind: "thinking", text: live.thinkingText.trim() })
    }
    if (live.toolLines.length) {
      const label = live.toolLines[live.toolLines.length - 1]?.label || "Browser task running..."
      parts.push({
        kind: "tool_group",
        id: "live-tool-group",
        label,
        lines: [...live.toolLines],
      })
    }
    if (live.assistantText.trim()) {
      parts.push({ kind: "text", text: live.assistantText.trim() })
    }
    feed.push({
      kind: "assistant",
      id: "live-assistant",
      parts,
      timestamp: live.timestamp || new Date().toISOString(),
    })
  }

  return feed
}
