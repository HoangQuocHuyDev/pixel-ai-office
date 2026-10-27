import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchAgents } from '../../agents/api/agentClient'
import type { AgentId, AgentMetadata } from '../../agents/types'
import { streamChatResponse } from '../api/chatStreamClient'
import {
  createRemoteConversation,
  deleteRemoteConversation,
  fetchConversationMessages,
  fetchConversations,
  persistRemoteUserMessage,
  type RemoteMessage,
} from '../api/conversationClient'
import type { ChatMessage, ConversationSummary, StreamError } from '../types'

export const MAX_MESSAGE_LENGTH = 4000
const ACTIVE_CONVERSATION_STORAGE_KEY = 'pixel-ai-office.active-conversation-id'

function mapRemoteMessages(remoteMessages: RemoteMessage[]): ChatMessage[] {
  return remoteMessages.map((message) => {
    const date = new Date(message.created_at)
    return {
      id: `msg-${message.id}`,
      role: message.role,
      content: message.content,
      timestamp: date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      createdAt: date.getTime(),
      status: 'completed',
      conversationId: message.conversation_id,
      remoteId: message.id,
    }
  })
}

export function useChat() {
  const [agents, setAgents] = useState<AgentMetadata[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<AgentId>('manager')
  const [agentError, setAgentError] = useState<string | null>(null)
  const [isLoadingAgents, setIsLoadingAgents] = useState(true)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoadingConversations, setIsLoadingConversations] = useState(false)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const activeConversationIdRef = useRef<number | null>(null)
  const selectedAgentIdRef = useRef<AgentId>('manager')
  const selectionVersionRef = useRef(0)

  const stopGenerating = useCallback(() => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setMessages((previous) => previous.map((message) =>
      message.status === 'streaming' ? { ...message, status: 'stopped' } : message,
    ))
    setIsStreaming(false)
  }, [])

  useEffect(() => () => abortControllerRef.current?.abort(), [])

  const loadConversationMessages = useCallback(async (
    conversationId: number,
    version: number,
  ) => {
    setIsLoadingMessages(true)
    const remoteMessages = await fetchConversationMessages(conversationId)
    if (remoteMessages && selectionVersionRef.current === version
      && activeConversationIdRef.current === conversationId) {
      setMessages(mapRemoteMessages(remoteMessages))
    } else if (!remoteMessages && selectionVersionRef.current === version) {
      setHistoryError('Unable to load messages for this conversation.')
    }
    if (selectionVersionRef.current === version) setIsLoadingMessages(false)
  }, [])

  const activateConversation = useCallback(async (conversation: ConversationSummary) => {
    stopGenerating()
    const version = ++selectionVersionRef.current
    selectedAgentIdRef.current = conversation.agent_id
    setSelectedAgentId(conversation.agent_id)
    activeConversationIdRef.current = conversation.id
    localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, String(conversation.id))
    setActiveConversationId(conversation.id)
    setMessages([])
    setHistoryError(null)
    await loadConversationMessages(conversation.id, version)
  }, [loadConversationMessages, stopGenerating])

  const loadConversations = useCallback(async () => {
    setIsLoadingConversations(true)
    setHistoryError(null)
    const list = await fetchConversations(50, 0)
    setConversations(list)
    if (activeConversationIdRef.current === null && list.length > 0) {
      const savedId = Number.parseInt(
        localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY) ?? '',
        10,
      )
      const restored = Number.isFinite(savedId)
        ? list.find((conversation) => conversation.id === savedId)
        : undefined
      await activateConversation(restored ?? list[0])
    }
    setIsLoadingConversations(false)
  }, [activateConversation])

  const loadAgentList = useCallback(async () => {
    setIsLoadingAgents(true)
    setAgentError(null)
    try {
      setAgents(await fetchAgents())
    } catch {
      setAgentError('Unable to load AI agents.')
    } finally {
      setIsLoadingAgents(false)
    }
  }, [])

  useEffect(() => {
    void Promise.all([loadAgentList(), loadConversations()])
  }, [loadAgentList, loadConversations])

  const selectAgent = useCallback(async (agentId: AgentId) => {
    if (agentId === selectedAgentIdRef.current || isStreaming) return
    stopGenerating()
    selectedAgentIdRef.current = agentId
    setSelectedAgentId(agentId)
    const latest = conversations.find((conversation) => conversation.agent_id === agentId)
    if (latest) {
      await activateConversation(latest)
    } else {
      ++selectionVersionRef.current
      activeConversationIdRef.current = null
      localStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY)
      setActiveConversationId(null)
      setMessages([])
      setHistoryError(null)
      setIsLoadingMessages(false)
    }
  }, [activateConversation, conversations, isStreaming, stopGenerating])

  const selectConversation = useCallback(async (conversationId: number) => {
    const conversation = conversations.find((item) => item.id === conversationId)
    if (!conversation || conversation.id === activeConversationIdRef.current) return
    await activateConversation(conversation)
  }, [activateConversation, conversations])

  const createNewConversation = useCallback(() => {
    stopGenerating()
    ++selectionVersionRef.current
    activeConversationIdRef.current = null
    localStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY)
    setActiveConversationId(null)
    setMessages([])
    setHistoryError(null)
    setIsLoadingMessages(false)
  }, [stopGenerating])

  const deleteConversation = useCallback(async (conversationId: number) => {
    const isActive = activeConversationIdRef.current === conversationId
    if (isActive) stopGenerating()
    if (!await deleteRemoteConversation(conversationId)) {
      setHistoryError('Failed to delete conversation on server.')
      return false
    }
    const nextList = conversations.filter((conversation) => conversation.id !== conversationId)
    setConversations(nextList)
    if (isActive) {
      const nextForAgent = nextList.find(
        (conversation) => conversation.agent_id === selectedAgentIdRef.current,
      )
      if (nextForAgent) await activateConversation(nextForAgent)
      else createNewConversation()
    }
    return true
  }, [activateConversation, conversations, createNewConversation, stopGenerating])

  const sendMessage = useCallback(async (content: string): Promise<boolean> => {
    const trimmed = content.trim()
    if (!trimmed || isStreaming) return false

    const controller = new AbortController()
    abortControllerRef.current?.abort()
    abortControllerRef.current = controller
    setIsStreaming(true)
    setHistoryError(null)
    const targetAgentId = selectedAgentIdRef.current
    let targetConversationId = activeConversationIdRef.current

    if (!targetConversationId) {
      const title = trimmed.length > 50 ? `${trimmed.slice(0, 47)}...` : trimmed
      const created = await createRemoteConversation(title, targetAgentId, controller.signal)
      if (!created || controller.signal.aborted) {
        setIsStreaming(false)
        abortControllerRef.current = null
        if (!controller.signal.aborted) setHistoryError('Unable to create conversation on backend server.')
        return false
      }
      targetConversationId = created.id
      activeConversationIdRef.current = created.id
      localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, String(created.id))
      setActiveConversationId(created.id)
      setConversations((previous) => [created, ...previous])
    }

    const persisted = await persistRemoteUserMessage(
      targetConversationId,
      trimmed,
      controller.signal,
    )
    if (!persisted || controller.signal.aborted) {
      setIsStreaming(false)
      abortControllerRef.current = null
      if (!controller.signal.aborted) setHistoryError('Failed to persist user message to database.')
      return false
    }

    const now = new Date()
    const timestamp = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const assistantMessageId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    setMessages((previous) => [...previous, {
      id: `user-${persisted.id}`,
      role: 'user',
      content: trimmed.slice(0, MAX_MESSAGE_LENGTH),
      timestamp,
      createdAt: now.getTime(),
      status: 'completed',
      conversationId: targetConversationId,
      remoteId: persisted.id,
    }, {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp,
      createdAt: now.getTime() + 1,
      status: 'streaming',
      conversationId: targetConversationId,
    }])

    await streamChatResponse({
      agentId: targetAgentId,
      prompt: trimmed,
      conversationId: targetConversationId,
      signal: controller.signal,
      callbacks: {
        onChunk: (chunk) => {
          if (activeConversationIdRef.current !== targetConversationId) return
          setMessages((previous) => previous.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: message.content + chunk }
              : message,
          ))
        },
        onDone: (data) => {
          if (activeConversationIdRef.current === targetConversationId) {
            setMessages((previous) => previous.map((message) =>
              message.id === assistantMessageId
                ? { ...message, status: 'completed', remoteId: data?.messageId }
                : message,
            ))
          }
          setIsStreaming(false)
          abortControllerRef.current = null
          void fetchConversations(50, 0).then(setConversations)
        },
        onError: (error: StreamError) => {
          if (activeConversationIdRef.current === targetConversationId) {
            setMessages((previous) => previous.map((message) =>
              message.id === assistantMessageId
                ? { ...message, status: 'failed', error: error.message }
                : message,
            ))
          }
          setIsStreaming(false)
          abortControllerRef.current = null
        },
        onAbort: () => {
          if (activeConversationIdRef.current === targetConversationId) {
            setMessages((previous) => previous.map((message) =>
              message.id === assistantMessageId ? { ...message, status: 'stopped' } : message,
            ))
          }
          setIsStreaming(false)
          abortControllerRef.current = null
        },
      },
    })
    return true
  }, [isStreaming])

  return {
    agents,
    selectedAgentId,
    agentError,
    isLoadingAgents,
    conversations,
    activeConversationId,
    messages,
    isStreaming,
    isLoadingConversations,
    isLoadingMessages,
    historyError,
    sendMessage,
    stopGenerating,
    selectAgent,
    selectConversation,
    createNewConversation,
    deleteConversation,
    loadConversations,
    loadAgentList,
  }
}
