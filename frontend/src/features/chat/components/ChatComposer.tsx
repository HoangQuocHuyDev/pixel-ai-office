import { useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from 'react'

import { MAX_MESSAGE_LENGTH } from '../hooks/useChat'

type ChatComposerProps = {
  disabled?: boolean
  isStreaming?: boolean
  onSendMessage: (content: string) => boolean | Promise<boolean>
  onStopGenerating?: () => void
}

function ChatComposer({
  disabled = false,
  isStreaming = false,
  onSendMessage,
  onStopGenerating,
}: ChatComposerProps) {
  const [content, setContent] = useState('')

  const handleTextChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setContent(event.target.value)
  }

  const handleSubmit = (event?: FormEvent) => {
    if (event) {
      event.preventDefault()
    }

    if (disabled || isStreaming) return

    const trimmed = content.trim()
    if (!trimmed) return

    const sent = onSendMessage(trimmed)
    if (sent) {
      setContent('')
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSubmit()
    }
  }

  const trimmedLength = content.trim().length
  const isSendDisabled = disabled || isStreaming || trimmedLength === 0

  return (
    <form
      className="chat-composer"
      onSubmit={handleSubmit}
      aria-label="Send message to Manager AI"
    >
      <div className="chat-composer__input-wrapper">
        <textarea
          className="chat-composer__textarea"
          value={content}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder={
            isStreaming
              ? 'Manager AI is generating response...'
              : 'Assign a task to Manager AI... (Shift+Enter for newline)'
          }
          rows={3}
          disabled={disabled || isStreaming}
          aria-label="Message prompt for Manager AI"
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
        />
      </div>

      <div className="chat-composer__footer">
        <div className="chat-composer__meta">
          <span className="chat-composer__counter" aria-live="polite">
            {content.length > 0 ? `${content.length}/${MAX_MESSAGE_LENGTH}` : ''}
          </span>
        </div>

        {isStreaming ? (
          <button
            className="chat-composer__stop-button"
            type="button"
            aria-label="Stop generating response"
            onClick={onStopGenerating}
          >
            <span className="chat-composer__stop-icon" aria-hidden="true" />
            <span>Stop generating</span>
          </button>
        ) : (
          <button
            className="chat-composer__send-button"
            type="submit"
            disabled={isSendDisabled}
            aria-label="Send message"
          >
            <span>Send</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        )}
      </div>

      <p className="chat-composer__disclaimer">
        Powered by Google Gemini. Responses stream live from backend.
      </p>
    </form>
  )
}

export default ChatComposer
