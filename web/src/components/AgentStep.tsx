type AgentStepProps = {
  step: number
  action: string
  url?: string
  screenshot?: string | null
  timestamp: string
  onOpenScreenshot: (src: string) => void
}

function resolveScreenshotSrc(raw?: string | null) {
  if (!raw) {
    return null
  }
  if (raw.startsWith("data:image")) {
    return raw
  }
  return `data:image/png;base64,${raw}`
}

export function AgentStep({
  step,
  action,
  url,
  screenshot,
  timestamp,
  onOpenScreenshot,
}: AgentStepProps) {
  const screenshotSrc = resolveScreenshotSrc(screenshot)

  return (
    <div className="flex justify-start">
      <div className="max-w-[78%] rounded-2xl border border-fog-200 bg-white/90 px-4 py-3 text-sm text-ink-900 shadow-sm">
        <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-fog-400">
          <span>Step {step}</span>
          <span>{new Date(timestamp).toLocaleTimeString()}</span>
        </div>
        <div className="mt-2 font-medium text-ink-800">{action}</div>
        {url ? <div className="mt-2 text-xs text-accent-600">{url}</div> : null}
        {screenshotSrc ? (
          <button
            type="button"
            onClick={() => onOpenScreenshot(screenshotSrc)}
            className="mt-3 w-full overflow-hidden rounded-xl border border-fog-200 bg-fog-50 shadow-sm transition hover:border-accent-500"
          >
            <img src={screenshotSrc} alt={`Step ${step} screenshot`} className="h-40 w-full object-cover" />
          </button>
        ) : null}
      </div>
    </div>
  )
}
