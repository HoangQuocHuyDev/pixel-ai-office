export type MessageRole = 'user' | 'assistant'

export type MessageStatus =
  | 'pending'
  | 'streaming'
  | 'completed'
  | 'stopped'
  | 'failed'

export type ChatMessage = {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  createdAt: number
  status?: MessageStatus
  error?: string
  conversationId?: number
  remoteId?: number
}

export type ConversationSummary = {
  id: number
  title: string
  agent_id: AgentId
  created_at: string
  updated_at: string
}

export type StreamError = {
  code: string
  message: string
}
import type { AgentId } from '../agents/types'

