import ReactMarkdown from "react-markdown"
import type { AssistantPart } from "../types"

type AgentMessageProps = {
  parts: AssistantPart[]
  timestamp: string
  onOpenScreenshot: (src: string) => void
}

function resolveScreenshotSrc(raw?: string | null) {
  if (!raw) {
    return null
  }
  if (raw.startsWith("data:image") || raw.startsWith("/") || raw.startsWith("http://") || raw.startsWith("https://")) {
    return raw
  }
  return `data:image/png;base64,${raw}`
}

export function AgentMessage({ parts, timestamp, onOpenScreenshot }: AgentMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[72%] rounded-2xl border border-fog-200 bg-white/80 px-4 py-3 text-sm text-ink-900 shadow-sm">
        <div className="space-y-2">
          {parts.map((part, index) => {
            const key = `${part.kind}-${index}`
            if (part.kind === "thinking") {
              return (
                <div key={key} className="text-xs italic text-fog-400">
                  {part.text}
                </div>
              )
            }
            if (part.kind === "tool_group") {
              const hasDetails = part.lines.length > 0
              return (
                <details
                  key={part.id || key}
                  className="rounded-lg border border-fog-200/80 bg-fog-50/70 px-2 py-1 text-xs text-fog-600"
                >
                  <summary className="cursor-pointer list-none truncate whitespace-nowrap text-fog-500 [&::-webkit-details-marker]:hidden">
                    {part.label}
                  </summary>
                  {hasDetails ? (
                    <div className="mt-2 space-y-2">
                      {part.lines.map((line) => {
                        const screenshotSrc = resolveScreenshotSrc(line.screenshot)
                        return (
                          <div key={line.id} className="space-y-1">
                            <div>{line.label}</div>
                            {line.url ? <div className="truncate text-[11px] text-fog-400">{line.url}</div> : null}
                            {screenshotSrc ? (
                              <button
                                type="button"
                                onClick={() => onOpenScreenshot(screenshotSrc)}
                                className="overflow-hidden rounded-lg border border-fog-200"
                              >
                                <img src={screenshotSrc} alt="Tool screenshot" className="h-24 w-40 object-cover" />
                              </button>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                </details>
              )
            }
            return (
              <div key={key} className="prose prose-sm max-w-none text-ink-900 text-sm">
                <ReactMarkdown>{part.text}</ReactMarkdown>
              </div>
            )
          })}
        </div>
        <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-fog-400">
          {new Date(timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
