import { useEffect, useRef, useState, type RefObject } from 'react'

import { useChat } from '../hooks/useChat'
import type { AgentId } from '../../agents/types'
import ChatComposer from './ChatComposer'
import ChatMessage from './ChatMessage'

type ChatPanelProps = {
  isOpen: boolean
  toggleButtonRef?: RefObject<HTMLButtonElement | null>
  onClose: () => void
}

function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHour = Math.floor(diffMin / 60)
    const diffDay = Math.floor(diffHour / 24)

    if (diffSec < 60) return 'Just now'
    if (diffMin < 60) return `${diffMin}m ago`
    if (diffHour < 24) return `${diffHour}h ago`
    if (diffDay < 7) return `${diffDay}d ago`
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

function ChatPanel({ isOpen, toggleButtonRef, onClose }: ChatPanelProps) {
  const {
    agents,
    selectedAgentId,
    agentError,
    isLoadingAgents,
    conversations,
    activeConversationId,
    messages,
    sendMessage,
    stopGenerating,
    selectAgent,
    selectConversation,
    createNewConversation,
    deleteConversation,
    loadConversations,
    loadAgentList,
    isStreaming,
    isLoadingConversations,
    isLoadingMessages,
    historyError,
  } = useChat()

  const [isHistoryOpen, setIsHistoryOpen] = useState(false)

  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const wasOpenRef = useRef(false)
  const isNearBottomRef = useRef(true)

  // Track if user is scrolled near bottom
  const handleScroll = () => {
    const el = messagesContainerRef.current
    if (!el) return
    const threshold = 80 // pixels from bottom
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
  }

  // Scroll to bottom helper
  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    const el = messagesContainerRef.current
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior })
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior })
    }
  }

  // Auto-scroll to latest message if near bottom or while streaming
  useEffect(() => {
    if (isNearBottomRef.current || isStreaming) {
      scrollToBottom(isStreaming ? 'auto' : 'smooth')
    }
  }, [messages, isStreaming])

  // Reset scroll to bottom on conversation or agent switch
  useEffect(() => {
    isNearBottomRef.current = true
    scrollToBottom('auto')
  }, [activeConversationId, selectedAgentId])

  // Handle Escape key to close panel (accessible for keyboard and mobile drawer)
  useEffect(() => {
    if (!isOpen) {
      if (wasOpenRef.current) {
        toggleButtonRef?.current?.focus()
      }
      wasOpenRef.current = false
      return
    }

    wasOpenRef.current = true

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (isHistoryOpen) {
          setIsHistoryOpen(false)
          return
        }
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onClose, toggleButtonRef, isHistoryOpen])

  if (!isOpen) {
    return null
  }

  const activeConversation = conversations.find((c) => c.id === activeConversationId)
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId)
  const selectedAgentName = selectedAgent?.name ?? `${selectedAgentId[0].toUpperCase()}${selectedAgentId.slice(1)} AI`
  const specialtyLabels: Record<AgentId, string> = {
    manager: 'Planning',
    developer: 'Coding',
    researcher: 'Research',
  }

  return (
    <>
      <button
        className="chat-drawer-overlay"
        type="button"
        tabIndex={-1}
        aria-label="Close AI agent chat overlay"
        onClick={onClose}
      />

      <aside
        ref={panelRef}
        id="manager-ai-chat-panel"
        className="chat-panel"
        aria-label={`${selectedAgentName} Chat Panel`}
      >
        <header className="chat-panel__header">
          <div className="chat-panel__identity">
            <div className="chat-panel__title-wrapper">
              <h2 className="chat-panel__title">{selectedAgentName}</h2>
              <div
                className={`chat-panel__status chat-panel__status--${isStreaming ? 'streaming' : 'ready'}`}
                aria-label={`Status: ${isStreaming ? 'Streaming response' : 'Connected and ready'}`}
              >
                <span className="chat-panel__status-dot" aria-hidden="true" />
                <span>{isStreaming ? 'Streaming...' : 'Ready'}</span>
              </div>
            </div>
          </div>

          <div className="chat-panel__header-actions">
            <button
              className="icon-button chat-panel__close-button"
              type="button"
              aria-label="Close chat panel"
              onClick={onClose}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m6 6 12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
        </header>

        <div className="chat-panel__agent-selector">
          <label htmlFor="chat-agent-select">Agent</label>
          <select
            id="chat-agent-select"
            value={selectedAgentId}
            disabled={isLoadingAgents || isStreaming || agents.length === 0}
            onChange={(event) => void selectAgent(event.target.value as AgentId)}
          >
            {agents.length === 0 && <option value="manager">Manager AI — Planning</option>}
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} — {specialtyLabels[agent.id]}
              </option>
            ))}
          </select>
          <span>{isLoadingAgents ? 'Loading agents…' : specialtyLabels[selectedAgentId]}</span>
        </div>

        {/* Sub-navigation bar: New Chat & History toggle */}
        <div className="chat-panel__subnav" aria-label="Conversation controls">
          <div className="chat-panel__subnav-actions">
            <button
              className="chat-panel__subnav-btn chat-panel__subnav-btn--new"
              type="button"
              aria-label="Create new conversation"
              onClick={() => {
                createNewConversation()
                setIsHistoryOpen(false)
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <path d="M12 5v14M5 12h14" />
              </svg>
              <span>New</span>
            </button>

            <button
              className={`chat-panel__subnav-btn${isHistoryOpen ? ' chat-panel__subnav-btn--active' : ''}`}
              type="button"
              aria-expanded={isHistoryOpen}
              aria-label="Toggle conversation history"
              onClick={() => setIsHistoryOpen((prev) => !prev)}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />
              </svg>
              <span>History ({conversations.length})</span>
            </button>
          </div>

          <span className="chat-panel__subnav-title" title={activeConversation?.title || 'New Conversation'}>
            {activeConversation ? activeConversation.title : 'New Conversation'}
          </span>
        </div>

        {/* History Drawer */}
        {isHistoryOpen && (
          <div className="chat-panel__history-drawer" role="region" aria-label="Conversation history list">
            {isLoadingConversations ? (
              <div className="chat-panel__history-empty">Loading conversations...</div>
            ) : conversations.length === 0 ? (
              <div className="chat-panel__history-empty">No previous conversations yet.</div>
            ) : (
              conversations.map((conv) => {
                const isActive = conv.id === activeConversationId
                return (
                  <div
                    key={conv.id}
                    className={`chat-panel__history-item${isActive ? ' chat-panel__history-item--active' : ''}`}
                    role="button"
                    tabIndex={0}
                    aria-current={isActive ? 'true' : undefined}
                    onClick={() => {
                      selectConversation(conv.id)
                      setIsHistoryOpen(false)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        selectConversation(conv.id)
                        setIsHistoryOpen(false)
                      }
                    }}
                  >
                    <div className="chat-panel__history-item-info">
                      <span className="chat-panel__history-item-title">{conv.title}</span>
                      <span className="chat-panel__history-item-meta">
                        <span className={`chat-panel__agent-badge chat-panel__agent-badge--${conv.agent_id}`}>
                          {conv.agent_id}
                        </span>
                        <span className="chat-panel__history-item-time">{formatRelativeTime(conv.updated_at)}</span>
                      </span>
                    </div>

                    <button
                      className="chat-panel__history-item-delete"
                      type="button"
                      aria-label={`Delete conversation: ${conv.title}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteConversation(conv.id)
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M19 7l-.867 12.142A2 2 0 0 1 16.138 21H7.862a2 2 0 0 1-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* Error Feedback Banner */}
        {historyError && (
          <div className="chat-panel__error-banner" role="alert">
            <span>{historyError}</span>
            <button
              className="chat-panel__error-retry"
              type="button"
              onClick={() => loadConversations()}
            >
              Retry
            </button>
          </div>
        )}

        {agentError && (
          <div className="chat-panel__error-banner" role="alert">
            <span>{agentError}</span>
            <button className="chat-panel__error-retry" type="button" onClick={() => void loadAgentList()}>
              Retry
            </button>
          </div>
        )}

        {/* Messages Container */}
        <div
          ref={messagesContainerRef}
          className="chat-panel__messages"
          tabIndex={0}
          aria-label="Conversation messages"
          onScroll={handleScroll}
        >
          {isLoadingMessages ? (
            <div className="chat-panel__loading-state">
              <span className="chat-panel__status-dot chat-panel__status--streaming" aria-hidden="true" />
              <span>Loading messages...</span>
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-panel__empty-state">
              <div className="chat-panel__empty-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h3 className="chat-panel__empty-title">Talk to {selectedAgentName}</h3>
              <p className="chat-panel__empty-desc">
                Start a new {specialtyLabels[selectedAgentId].toLowerCase()} conversation with live streaming.
              </p>
              <div className="chat-panel__empty-example">
                <span className="chat-panel__empty-example-label">Example:</span>
                <code>"Create a personal portfolio website."</code>
              </div>
            </div>
          ) : (
            <div className="chat-panel__messages-list">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} aria-hidden="true" />
            </div>
          )}
        </div>

        <footer className="chat-panel__composer-area">
          <ChatComposer
            isStreaming={isStreaming}
            onSendMessage={sendMessage}
            onStopGenerating={stopGenerating}
          />
        </footer>
      </aside>
    </>
  )
}

export default ChatPanel
