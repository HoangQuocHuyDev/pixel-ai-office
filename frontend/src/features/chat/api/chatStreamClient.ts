import { API_BASE_URL } from '../../../config/api'
import type { StreamError } from '../types'
import type { AgentId } from '../../agents/types'

export type StreamChatDoneData = {
  status?: string
  messageId?: number
  conversationId?: number
}

export type StreamChatCallbacks = {
  onChunk: (content: string) => void
  onDone: (data?: StreamChatDoneData) => void
  onError: (error: StreamError) => void
  onAbort?: () => void
}

export type StreamChatOptions = {
  agentId: AgentId
  prompt: string
  conversationId?: number
  signal?: AbortSignal
  callbacks: StreamChatCallbacks
}

function parseSSEBlock(block: string, callbacks: StreamChatCallbacks): boolean {
  const lines = block.split(/\r?\n/)
  let eventType = ''
  let dataStr = ''

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataStr = line.slice(5).trim()
    }
  }

  if (!eventType && !dataStr) {
    return false
  }

  if (eventType === 'chunk') {
    try {
      const parsed = JSON.parse(dataStr) as { content?: string }
      if (typeof parsed.content === 'string' && parsed.content.length > 0) {
        callbacks.onChunk(parsed.content)
      }
    } catch {
      // Discard malformed JSON chunk
    }
    return false
  }

  if (eventType === 'done') {
    let doneData: StreamChatDoneData | undefined
    try {
      const parsed = JSON.parse(dataStr) as {
        status?: string
        message_id?: number
        conversation_id?: number
      }
      doneData = {
        status: parsed.status,
        messageId: parsed.message_id,
        conversationId: parsed.conversation_id,
      }
    } catch {
      // Discard malformed JSON
    }
    callbacks.onDone(doneData)
    return true
  }

  if (eventType === 'error') {
    let errorCode = 'AI_PROVIDER_ERROR'
    let errorMessage = 'AI service returned an error.'
    try {
      const parsed = JSON.parse(dataStr) as { code?: string; message?: string }
      if (parsed.code) errorCode = parsed.code
      if (parsed.message) errorMessage = parsed.message
    } catch {
      if (dataStr) errorMessage = dataStr
    }
    callbacks.onError({ code: errorCode, message: errorMessage })
    return true
  }

  return false
}

export async function streamChatResponse({
  agentId,
  prompt,
  conversationId,
  signal,
  callbacks,
}: StreamChatOptions): Promise<void> {
  const trimmed = prompt.trim()
  if (!trimmed) {
    callbacks.onError({
      code: 'VALIDATION_ERROR',
      message: 'Prompt cannot be empty.',
    })
    return
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/agents/${agentId}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: trimmed,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
      signal,
    })
  } catch (err: unknown) {
    if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      callbacks.onAbort?.()
      return
    }
    const targetUrl = `${API_BASE_URL}/api/v1/agents/${agentId}/stream`
    callbacks.onError({
      code: 'NETWORK_ERROR',
      message: `Unable to connect to the backend server at ${targetUrl}. Please verify FastAPI is running and CORS is configured.`,
    })
    return
  }

  if (!response.ok) {
    let code = `HTTP_${response.status}`
    let message = response.statusText || 'Request failed'
    try {
      const errJson = (await response.json()) as { error?: { code?: string; message?: string } }
      if (errJson.error?.code) code = errJson.error.code
      if (errJson.error?.message) message = errJson.error.message
    } catch {
      // Fallback to status text
    }

    callbacks.onError({
      code,
      message: `Server returned error (${response.status}): ${message}`,
    })
    return
  }

  if (!response.body) {
    callbacks.onError({
      code: 'EMPTY_BODY',
      message: 'Backend server returned an empty response stream.',
    })
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let streamFinished = false

  try {
    while (true) {
      const { done, value } = await reader.read()

      if (done) {
        buffer += decoder.decode() // Flush remaining bytes
        if (buffer.trim()) {
          const terminal = parseSSEBlock(buffer.trim(), callbacks)
          if (terminal) streamFinished = true
        }
        break
      }

      buffer += decoder.decode(value, { stream: true })

      while (true) {
        const boundaryMatch = buffer.match(/\r?\n\r?\n/)
        if (!boundaryMatch || boundaryMatch.index === undefined) {
          break
        }

        const block = buffer.slice(0, boundaryMatch.index)
        buffer = buffer.slice(boundaryMatch.index + boundaryMatch[0].length)

        if (block.trim()) {
          const terminal = parseSSEBlock(block.trim(), callbacks)
          if (terminal) {
            streamFinished = true
            break
          }
        }
      }

      if (streamFinished) {
        break
      }
    }

    // Verify stream reached 'done' or 'error' normally
    if (!streamFinished) {
      if (signal?.aborted) {
        callbacks.onAbort?.()
      } else {
        callbacks.onError({
          code: 'STREAM_INCOMPLETE',
          message: 'The stream ended unexpectedly before completion.',
        })
      }
    }
  } catch (err: unknown) {
    if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      callbacks.onAbort?.()
      return
    }
    callbacks.onError({
      code: 'STREAM_READ_ERROR',
      message: 'Connection was lost while reading the AI response stream.',
    })
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // Ignore release lock error on closed stream
    }
  }
}

