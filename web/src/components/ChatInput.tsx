import { useState } from "react"
import type { FormEvent } from "react"

type ChatInputProps = {
  onSend: (text: string) => void
  onCancel: () => void
  disabled?: boolean
  running?: boolean
}

export function ChatInput({ onSend, onCancel, disabled, running }: ChatInputProps) {
  const [value, setValue] = useState("")

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) {
      return
    }
    onSend(trimmed)
    setValue("")
  }

  return (
    <form onSubmit={handleSubmit} className="glass flex items-end gap-3 rounded-2xl p-4 shadow-glow">
      <div className="flex-1">
        <label className="text-xs font-semibold uppercase tracking-[0.2em] text-fog-400">
          Ask the agent
        </label>
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          rows={2}
          placeholder="Ask me to browse, compare, or summarize..."
          className="mt-2 w-full resize-none rounded-xl border border-fog-200 bg-white/70 px-4 py-3 text-sm text-ink-900 outline-none transition focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20"
          disabled={disabled}
        />
      </div>
      <div className="flex flex-col gap-2">
        <button
          type="submit"
          disabled={disabled}
          className="rounded-xl bg-ink-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-ink-800 disabled:cursor-not-allowed disabled:bg-fog-200 disabled:text-fog-400"
        >
          Send
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={!running}
          className="rounded-xl border border-fog-200 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-ink-700 transition hover:border-accent-500 hover:text-accent-600 disabled:cursor-not-allowed disabled:border-fog-200 disabled:text-fog-200"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
