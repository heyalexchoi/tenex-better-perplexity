import type { SessionStatus } from "../types"

const STATUS_STYLES: Record<SessionStatus, string> = {
  idle: "bg-fog-100 text-fog-400",
  running: "bg-accent-500 text-white",
  error: "bg-red-500 text-white",
}

export function StatusIndicator({ status }: { status: SessionStatus }) {
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${STATUS_STYLES[status]}`}>
      {status}
    </span>
  )
}
