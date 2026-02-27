import type { FeedItem } from "../types"
import { AgentMessage } from "./AgentMessage"
import { AgentStep } from "./AgentStep"
import { UserMessage } from "./UserMessage"

type MessageFeedProps = {
  items: FeedItem[]
  onOpenScreenshot: (src: string) => void
}

export function MessageFeed({ items, onOpenScreenshot }: MessageFeedProps) {
  return (
    <div className="flex flex-col gap-4">
      {items.map((item) => {
        if (item.kind === "user") {
          return <UserMessage key={item.id} content={item.content} timestamp={item.timestamp} />
        }
        if (item.kind === "assistant") {
          return <AgentMessage key={item.id} content={item.content} timestamp={item.timestamp} />
        }
        if (item.kind === "step") {
          return (
            <AgentStep
              key={item.id}
              step={item.step}
              action={item.action}
              url={item.url}
              screenshot={item.screenshot}
              timestamp={item.timestamp}
              onOpenScreenshot={onOpenScreenshot}
            />
          )
        }
        return (
          <div key={item.id} className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {item.error}
          </div>
        )
      })}
    </div>
  )
}
