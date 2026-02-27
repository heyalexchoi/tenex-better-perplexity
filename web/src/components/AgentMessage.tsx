type AgentMessageProps = {
  content: string
  timestamp: string
}

export function AgentMessage({ content, timestamp }: AgentMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[72%] rounded-2xl border border-fog-200 bg-white/80 px-4 py-3 text-sm text-ink-900 shadow-sm">
        <div className="whitespace-pre-wrap">{content}</div>
        <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-fog-400">
          {new Date(timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
