import type { FeedItem, Message, ToolLine } from "../types"

export type LiveState = {
  assistantText: string
  thinkingText: string
  timestamp: string
  activeToolLine: ToolLine | null
}

export function buildFeed(messages: Message[], live: LiveState | null): FeedItem[] {
  const timeline: Array<
    | { type: "user"; id: string; timestamp: string; content: string }
    | { type: "assistant"; id: string; timestamp: string; content: string }
    | { type: "tool"; id: string; timestamp: string; line: ToolLine }
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
      continue
    }

    assistantGroup.content = assistantGroup.content
      ? `${assistantGroup.content}\n${item.content}`
      : item.content
    assistantGroup.timestamp = item.timestamp
  }

  flushAssistantGroup()

  if (live && (live.assistantText.trim() || live.thinkingText.trim() || live.activeToolLine)) {
    feed.push({
      kind: "assistant",
      id: "live-assistant",
      content: live.assistantText.trim(),
      thinking: live.thinkingText.trim() || undefined,
      toolLines: live.activeToolLine ? [live.activeToolLine] : undefined,
      timestamp: live.timestamp || new Date().toISOString(),
    })
  }

  return feed
}
