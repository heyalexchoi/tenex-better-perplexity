type UserMessageProps = {
  content: string
  timestamp: string
}

export function UserMessage({ content, timestamp }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-2xl bg-ink-900 px-4 py-3 text-sm text-white shadow">
        <div className="whitespace-pre-wrap">{content}</div>
        <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-fog-200">
          {new Date(timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
