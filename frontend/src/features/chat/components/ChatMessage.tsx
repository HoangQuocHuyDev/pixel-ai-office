import type { ChatMessage as ChatMessageType } from '../types'

type ChatMessageProps = {
  message: ChatMessageType
}

function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const isStreaming = message.status === 'streaming'
  const isStopped = message.status === 'stopped'
  const isFailed = message.status === 'failed'

  return (
    <article
      className={`chat-message chat-message--${message.role}`}
      aria-label={`${isUser ? 'User message' : 'Manager AI message'} at ${message.timestamp}`}
    >
      <header className="chat-message__header">
        <div className="chat-message__author">
          <span
            className={`chat-message__avatar chat-message__avatar--${message.role}`}
            aria-hidden="true"
          >
            {isUser ? 'U' : 'M'}
          </span>
          <span className="chat-message__name">
            {isUser ? 'You' : 'Manager AI'}
          </span>
          {isStreaming && (
            <span className="chat-message__streaming-badge" aria-live="polite">
              Generating...
            </span>
          )}
          {isStopped && (
            <span className="chat-message__stopped-badge">
              Stopped
            </span>
          )}
        </div>
        <time className="chat-message__time" dateTime={new Date(message.createdAt).toISOString()}>
          {message.timestamp}
        </time>
      </header>

      <div className="chat-message__body">
        {message.content ? (
          <p className="chat-message__content">
            {message.content}
            {isStreaming && <span className="chat-message__cursor" aria-hidden="true" />}
          </p>
        ) : isStreaming ? (
          <div className="chat-message__loading" aria-label="Waiting for AI response">
            <span className="chat-message__dot" />
            <span className="chat-message__dot" />
            <span className="chat-message__dot" />
          </div>
        ) : null}

        {isFailed && message.error && (
          <div className="chat-message__error-notice" role="alert">
            <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <span>{message.error}</span>
          </div>
        )}
      </div>
    </article>
  )
}

export default ChatMessage
