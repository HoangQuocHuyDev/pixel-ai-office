import { useLayoutEffect, useRef, useState, type RefObject } from 'react'

import PhaserGame, { type PhaserGameHandle } from '../../../game/PhaserGame'
import { useAgentActivities } from '../../agents/hooks/useAgentActivities'
import type { AgentId } from '../../agents/types'
import type { GridCoord } from '../../../game/systems/PathfindingSystem'
import { retroSFX } from '../../../game/utils/sfx'

type OfficeViewportProps = {
  isChatOpen?: boolean
  chatButtonRef?: RefObject<HTMLButtonElement | null>
  onToggleChat?: () => void
}

function OfficeViewport({
  isChatOpen = false,
  chatButtonRef,
  onToggleChat,
}: OfficeViewportProps) {
  const gameRef = useRef<PhaserGameHandle>(null)
  const { activities, connection } = useAgentActivities()
  const names: Record<AgentId, string> = { manager: 'Manager', developer: 'Developer', researcher: 'Researcher' }
  const roles: Record<AgentId, string> = {
    manager: 'Workflow Orchestration',
    developer: 'Full-Stack Implementation',
    researcher: 'Deep Research & Analysis',
  }

  const [isEditingLayout, setIsEditingLayout] = useState(false)
  const [editorError, setEditorError] = useState<string | null>(null)
  const [editorNotification, setEditorNotification] = useState<string | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<AgentId | null>(null)
  const [relocateNotification, setRelocateNotification] = useState<string | null>(null)
  const [huddleNotification, setHuddleNotification] = useState<string | null>(null)
  const [isMuted, setIsMuted] = useState(() => retroSFX.isMuted())

  useLayoutEffect(() => {
    gameRef.current?.syncSize()
  }, [isChatOpen])

  const handleToggleSound = () => {
    const nextMuted = retroSFX.toggleMute()
    setIsMuted(nextMuted)
  }

  const handleSimulateHuddle = () => {
    const started = gameRef.current?.startHuddle('manager', 'developer', {
      topic: "Here's the plan for next task. Ready to coordinate?",
      response: "Understood! Starting development now.",
    })
    if (started) {
      setHuddleNotification('Meeting in progress: Manager & Developer collaborating at conference table.')
      setTimeout(() => setHuddleNotification(null), 6000)
    }
  }

  const handleAgentSelect = (agentId: AgentId | null) => {
    setSelectedAgentId(agentId)
  }

  const handleDeselectAgent = () => {
    setSelectedAgentId(null)
    gameRef.current?.selectAgent(null)
  }

  const handleAgentRelocate = (agentId: string, coord: GridCoord) => {
    const agentName = names[agentId as AgentId] ?? agentId
    setRelocateNotification(`Reassigned ${agentName} to workstation at (${coord.column}, ${coord.row})`)
    setTimeout(() => setRelocateNotification(null), 3500)
  }

  const handleStartEdit = () => {
    setSelectedAgentId(null)
    setIsEditingLayout(true)
    setEditorError(null)
    setEditorNotification(null)
    gameRef.current?.startLayoutEdit()
  }

  const handleCancelEdit = () => {
    setIsEditingLayout(false)
    setEditorError(null)
    setEditorNotification(null)
    gameRef.current?.cancelLayoutEdit()
  }

  const handleSaveEdit = () => {
    const result = gameRef.current?.saveLayoutEdit()
    if (result?.success) {
      setIsEditingLayout(false)
      setEditorError(null)
      setEditorNotification('Office layout saved successfully.')
      setTimeout(() => setEditorNotification(null), 3500)
    } else {
      setEditorError(result?.error ?? 'Failed to save layout')
    }
  }

  const handleResetDefault = () => {
    gameRef.current?.resetLayoutToDefault()
    setEditorError(null)
    setEditorNotification('Reset to default layout in editor. Click "Save Layout" to keep.')
    setTimeout(() => setEditorNotification(null), 3500)
  }

  const selectedActivity = selectedAgentId
    ? activities.find((a) => a.agent_id === selectedAgentId)
    : undefined

  return (
    <section className="office-viewport" aria-labelledby="office-viewport-title">
      <header className="office-viewport__header">
        <div>
          <p className="office-viewport__eyebrow">Office viewport</p>
          <h2 id="office-viewport-title">Pixel Office</h2>
        </div>
        <div className="office-viewport__actions">
          <span className="office-viewport__status">
            <span aria-hidden="true" />
            {isEditingLayout ? 'Editing layout' : 'Office online'}
          </span>
          <button
            className={`office-viewport__sound-toggle${isMuted ? ' office-viewport__sound-toggle--muted' : ''}`}
            type="button"
            aria-label={isMuted ? 'Unmute retro sound effects' : 'Mute retro sound effects'}
            onClick={handleToggleSound}
          >
            {isMuted ? '🔇 Sound Off' : '🔊 Sound On'}
          </button>
          <button
            className="office-viewport__huddle"
            type="button"
            aria-label="Simulate collaborative agent meeting huddle"
            onClick={handleSimulateHuddle}
          >
            🤝 Huddle
          </button>
          {!isEditingLayout ? (
            <button
              className="office-viewport__edit"
              type="button"
              aria-label="Edit office layout"
              onClick={handleStartEdit}
            >
              Edit Layout
            </button>
          ) : (
            <button
              className="office-viewport__edit office-viewport__edit--active"
              type="button"
              aria-label="Exit layout editing"
              onClick={handleCancelEdit}
            >
              Exit Edit
            </button>
          )}
          <button
            className="office-viewport__reset"
            type="button"
            aria-label="Reset office camera view"
            onClick={() => gameRef.current?.resetView()}
          >
            Reset View
          </button>
          {onToggleChat && (
            <button
              ref={chatButtonRef}
              className={`office-viewport__chat-toggle${isChatOpen ? ' office-viewport__chat-toggle--active' : ''}`}
              type="button"
              aria-label={isChatOpen ? 'Close AI agent chat panel' : 'Open AI agent chat panel'}
              aria-expanded={isChatOpen}
              aria-controls="manager-ai-chat-panel"
              onClick={onToggleChat}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span>{isChatOpen ? 'Hide Chat' : 'Chat'}</span>
            </button>
          )}
        </div>
      </header>

      <div className="office-viewport__stage">
        <PhaserGame
          ref={gameRef}
          activities={activities}
          onAgentSelect={handleAgentSelect}
          onAgentRelocate={handleAgentRelocate}
        />

        {selectedAgentId && (
          <aside className="agent-inspector-card" aria-label={`Agent inspector for ${names[selectedAgentId]}`}>
            <div className="agent-inspector-card__header">
              <div className="agent-inspector-card__title-box">
                <span className={`agent-inspector-avatar agent-inspector-avatar--${selectedAgentId}`} aria-hidden="true">
                  {selectedAgentId === 'manager' ? '📋' : selectedAgentId === 'developer' ? '⚡' : '🔍'}
                </span>
                <div>
                  <h3 className="agent-inspector-card__name">{names[selectedAgentId]}</h3>
                  <span className="agent-inspector-card__role">{roles[selectedAgentId]}</span>
                </div>
              </div>
              <button
                type="button"
                className="agent-inspector-card__close"
                onClick={handleDeselectAgent}
                aria-label="Close agent inspector"
              >
                ✕
              </button>
            </div>

            <div className="agent-inspector-card__body">
              <div className="agent-inspector-card__row">
                <span className="agent-inspector-label">Status</span>
                <span className={`agent-inspector-status-pill agent-inspector-status-pill--${selectedActivity?.status ?? 'idle'}`}>
                  ● {selectedActivity?.status ?? 'idle'}
                </span>
              </div>

              <div className="agent-inspector-card__row">
                <span className="agent-inspector-label">Active Task</span>
                <span className="agent-inspector-card__task-val">
                  {selectedActivity?.current_task_title ?? (selectedActivity?.status === 'working' ? 'Processing active task' : 'No active task')}
                </span>
              </div>

              {selectedActivity?.workflow_run_id && (
                <div className="agent-inspector-card__row">
                  <span className="agent-inspector-label">Workflow</span>
                  <span className="agent-inspector-card__mono">#{selectedActivity.workflow_run_id}</span>
                </div>
              )}

              <div className="agent-inspector-card__hint">
                💡 Click any workstation chair to relocate {names[selectedAgentId]}.
              </div>
            </div>

            <div className="agent-inspector-card__footer">
              {onToggleChat && (
                <button
                  type="button"
                  className="agent-inspector-card__btn agent-inspector-card__btn--chat"
                  onClick={() => {
                    if (!isChatOpen) onToggleChat()
                  }}
                >
                  Chat with {names[selectedAgentId]}
                </button>
              )}
              <button
                type="button"
                className="agent-inspector-card__btn agent-inspector-card__btn--secondary"
                onClick={handleDeselectAgent}
              >
                Deselect
              </button>
            </div>
          </aside>
        )}

        {isEditingLayout && (
          <div className="layout-editor-bar" role="toolbar" aria-label="Office layout editor controls">
            <div className="layout-editor-bar__info">
              <span className="layout-editor-badge">EDITING</span>
              <span>Click and drag furniture. Green = valid, Red = invalid.</span>
            </div>
            <div className="layout-editor-bar__actions">
              <button
                type="button"
                className="layout-editor-btn layout-editor-btn--secondary"
                onClick={handleResetDefault}
                aria-label="Reset to default office layout"
              >
                Default
              </button>
              <button
                type="button"
                className="layout-editor-btn layout-editor-btn--secondary"
                onClick={handleCancelEdit}
                aria-label="Cancel editing without saving"
              >
                Cancel
              </button>
              <button
                type="button"
                className="layout-editor-btn layout-editor-btn--primary"
                onClick={handleSaveEdit}
                aria-label="Save current office layout"
              >
                Save Layout
              </button>
            </div>
          </div>
        )}

        {editorError && (
          <div className="layout-editor-alert layout-editor-alert--error" role="alert">
            <span>{editorError}</span>
            <button type="button" onClick={() => setEditorError(null)} aria-label="Dismiss error">
              ✕
            </button>
          </div>
        )}

        {editorNotification && (
          <div className="layout-editor-alert layout-editor-alert--success" role="status">
            <span>{editorNotification}</span>
          </div>
        )}

        {relocateNotification && (
          <div className="layout-editor-alert layout-editor-alert--success" role="status">
            <span>{relocateNotification}</span>
          </div>
        )}

        {huddleNotification && (
          <div className="layout-editor-alert layout-editor-alert--huddle" role="status">
            <span>{huddleNotification}</span>
          </div>
        )}
      </div>

      <div className="agent-activity-strip" aria-label="Live agent activity">
        {connection !== 'online' ? (
          <p className={`agent-activity-connection agent-activity-connection--${connection}`}>
            {connection === 'loading' ? 'Loading agent activity...' : 'Agent activity connection unavailable'}
          </p>
        ) : (
          activities.map((activity) => (
            <article className={`agent-activity-card agent-activity-card--${activity.status}`} key={activity.agent_id}>
              <div>
                <span className="agent-activity-dot" />
                <strong>{names[activity.agent_id]}</strong>
                <span>{activity.status}</span>
              </div>
              <p>
                {activity.current_task_title ?? (activity.status === 'working' && activity.agent_id === 'manager' ? 'Creating final report' : 'No active task')}
              </p>
              {activity.workflow_run_id && <small>Workflow #{activity.workflow_run_id}</small>}
            </article>
          ))
        )}
      </div>
      <p className="office-viewport__help">
        Autonomous AI agent movement simulation. Click an agent to inspect and focus; click a workstation chair to relocate; zoom with mouse wheel; pan with middle-drag or Space + drag.
      </p>
    </section>
  )
}

export default OfficeViewport
