import type { ToolLine } from "../types"

type AgentMessageProps = {
  content: string
  thinking?: string
  toolLines?: ToolLine[]
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

export function AgentMessage({ content, thinking, toolLines, timestamp, onOpenScreenshot }: AgentMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[72%] rounded-2xl border border-fog-200 bg-white/80 px-4 py-3 text-sm text-ink-900 shadow-sm">
        {thinking?.trim() ? (
          <div className="mb-3 rounded-lg bg-fog-50 px-3 py-2 text-xs italic text-fog-400">{thinking}</div>
        ) : null}
        {toolLines?.length ? (
          <div className="mb-3 space-y-2 border-b border-fog-100 pb-3 text-xs text-fog-500">
            {toolLines.map((line) => {
              const screenshotSrc = resolveScreenshotSrc(line.screenshot)
              return (
                <div key={line.id} className="space-y-1">
                  <div>{line.label}</div>
                  {line.url ? <div className="truncate text-[11px] text-fog-400">{line.url}</div> : null}
                  {screenshotSrc ? (
                    <button
                      type="button"
                      onClick={() => onOpenScreenshot(screenshotSrc)}
                      className="mt-1 overflow-hidden rounded-lg border border-fog-200"
                    >
                      <img src={screenshotSrc} alt="Tool screenshot" className="h-24 w-40 object-cover" />
                    </button>
                  ) : null}
                </div>
              )
            })}
          </div>
        ) : null}
        <div className="whitespace-pre-wrap">{content}</div>
        <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-fog-400">
          {new Date(timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
