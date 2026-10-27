import { API_BASE_URL } from '../../../config/api'
import type { ConversationSummary } from '../types'
import type { AgentId } from '../../agents/types'

export type RemoteMessage = {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export type RemoteConversationDetail = ConversationSummary & {
  messages: RemoteMessage[]
}

/**
 * Fetches the paginated list of conversations from backend, ordered by updated_at desc.
 */
export async function fetchConversations(
  limit = 50,
  offset = 0,
): Promise<ConversationSummary[]> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/conversations?limit=${limit}&offset=${offset}`,
    )
    if (!res.ok) return []
    return (await res.json()) as ConversationSummary[]
  } catch {
    return []
  }
}

/**
 * Creates a new conversation with a title.
 */
export async function createRemoteConversation(
  title: string,
  agentId: AgentId = 'manager',
  signal?: AbortSignal,
): Promise<ConversationSummary | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      signal,
      body: JSON.stringify({
        title: title.slice(0, 150),
        agent_id: agentId,
      }),
    })
    if (!res.ok) return null
    return (await res.json()) as ConversationSummary
  } catch {
    return null
  }
}

/**
 * Fetches a single conversation with its message list.
 */
export async function fetchConversationDetails(
  id: number,
): Promise<RemoteConversationDetail | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/conversations/${id}`)
    if (!res.ok) return null
    return (await res.json()) as RemoteConversationDetail
  } catch {
    return null
  }
}

/**
 * Fetches chronological messages for a specific conversation.
 */
export async function fetchConversationMessages(
  conversationId: number,
  limit = 100,
  offset = 0,
): Promise<RemoteMessage[] | null> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`,
    )
    if (!res.ok) return null
    return (await res.json()) as RemoteMessage[]
  } catch {
    return null
  }
}

/**
 * Persists a user message to a remote conversation.
 */
export async function persistRemoteUserMessage(
  conversationId: number,
  content: string,
  signal?: AbortSignal,
): Promise<RemoteMessage | null> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/conversations/${conversationId}/messages`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        signal,
        body: JSON.stringify({ content }),
      },
    )
    if (!res.ok) return null
    return (await res.json()) as RemoteMessage
  } catch {
    return null
  }
}

/**
 * Deletes a conversation permanently.
 */
export async function deleteRemoteConversation(
  conversationId: number,
): Promise<boolean> {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/conversations/${conversationId}`,
      {
        method: 'DELETE',
      },
    )
    return res.status === 204
  } catch {
    return false
  }
}
