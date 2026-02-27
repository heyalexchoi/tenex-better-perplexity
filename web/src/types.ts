export type SessionStatus = "idle" | "running" | "error"

export type Message = {
  id: string
  session_id: string
  role: "user" | "assistant"
  content: string
  timestamp: string
}

export type AgentEvent = {
  id?: number
  session_id?: string
  type: "step" | "done" | "error"
  data: Record<string, unknown>
  timestamp: string
}

export type FeedItem =
  | {
      kind: "user"
      id: string
      content: string
      timestamp: string
    }
  | {
      kind: "assistant"
      id: string
      content: string
      timestamp: string
    }
  | {
      kind: "step"
      id: string
      step: number
      action: string
      url?: string
      screenshot?: string | null
      timestamp: string
    }
  | {
      kind: "error"
      id: string
      error: string
      timestamp: string
    }
