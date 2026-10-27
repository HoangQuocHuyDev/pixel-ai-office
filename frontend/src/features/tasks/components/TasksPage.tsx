import { useEffect, useState, type FormEvent } from 'react'
import type { AgentId } from '../../agents/types'
import PlanningPanel from '../../planning/components/PlanningPanel'
import { deleteTask } from '../api/taskClient'
import { executeTask, fetchTaskExecutions } from '../api/taskExecutionClient'
import { useTasks } from '../hooks/useTasks'
import type { OfficeTask, TaskExecution, TaskInput, TaskPriority, TaskStatus } from '../types'

const columns: Array<{ status: TaskStatus; label: string }> = [
  { status: 'todo', label: 'To Do' },
  { status: 'in_progress', label: 'In Progress' },
  { status: 'done', label: 'Done' },
  { status: 'cancelled', label: 'Cancelled' },
]

const blank: TaskInput = {
  title: '',
  description: null,
  status: 'todo',
  priority: 'medium',
  assigned_agent_id: null,
}

export default function TasksPage({ onOpenArtifact }: { onOpenArtifact: (artifactId: number) => void }) {
  const state = useTasks()
  const [editing, setEditing] = useState<OfficeTask | null>(null)
  const [viewing, setViewing] = useState<OfficeTask | null>(null)
  const [form, setForm] = useState<TaskInput>(blank)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [executions, setExecutions] = useState<TaskExecution[]>([])
  const [executionLoading, setExecutionLoading] = useState(false)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const [runningTaskId, setRunningTaskId] = useState<number | null>(null)

  // Search & Priority Filter states
  const [searchQuery, setSearchQuery] = useState('')
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | ''>('')
  const [isCleaningDone, setIsCleaningDone] = useState(false)

  const openForm = (task?: OfficeTask) => {
    setEditing(task ?? null)
    setForm(
      task
        ? {
            title: task.title,
            description: task.description,
            status: task.status,
            priority: task.priority,
            assigned_agent_id: task.assigned_agent_id,
          }
        : blank,
    )
    setShowForm(true)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    try {
      await state.save(form, editing?.id)
      setShowForm(false)
    } finally {
      setSaving(false)
    }
  }

  const agentName = (id: AgentId | null) => state.agents.find((agent) => agent.id === id)?.name ?? 'Unassigned'
  const agentInfo = (id: AgentId | null) => {
    if (id === 'developer') return { name: 'Developer AI', icon: '💻', modifier: 'developer' }
    if (id === 'researcher') return { name: 'Researcher AI', icon: '🔍', modifier: 'researcher' }
    if (id === 'manager') return { name: 'Manager AI', icon: '📋', modifier: 'manager' }
    const name = agentName(id)
    return { name, icon: '👤', modifier: 'unassigned' }
  }
  const canRun = (task: OfficeTask) =>
    task.status === 'todo' && (task.assigned_agent_id === 'developer' || task.assigned_agent_id === 'researcher')

  useEffect(() => {
    if (!viewing) {
      setExecutions([])
      return
    }
    const controller = new AbortController()
    setExecutionLoading(true)
    setExecutionError(null)
    void fetchTaskExecutions(viewing.id, controller.signal)
      .then(setExecutions)
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setExecutionError(reason instanceof Error ? reason.message : 'Unable to load execution history.')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setExecutionLoading(false)
      })
    return () => controller.abort()
  }, [viewing?.id])

  const runTask = async (task: OfficeTask) => {
    if (runningTaskId !== null) return
    setRunningTaskId(task.id)
    setExecutionError(null)
    try {
      const execution = await executeTask(task.id)
      setExecutions((current) => [execution, ...current.filter((item) => item.id !== execution.id)])
      setViewing((current) =>
        current?.id === task.id
          ? {
              ...current,
              status: execution.status === 'completed' ? 'done' : 'todo',
              completed_at: execution.status === 'completed' ? execution.completed_at : null,
            }
          : current,
      )
    } catch (reason) {
      setExecutionError(
        reason instanceof Error
          ? `${reason.message} Check execution history for the persisted state.`
          : 'Execution request was interrupted. Check execution history.',
      )
      try {
        setExecutions(await fetchTaskExecutions(task.id))
      } catch {
        /* retain actionable request error */
      }
    } finally {
      setRunningTaskId(null)
      await state.load()
    }
  }

  // Client-side search and priority filtering on top of server filters
  const filteredTasks = state.tasks.filter((task) => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const titleMatches = task.title.toLowerCase().includes(q)
      const descMatches = (task.description ?? '').toLowerCase().includes(q)
      if (!titleMatches && !descMatches) return false
    }
    if (priorityFilter && task.priority !== priorityFilter) {
      return false
    }
    return true
  })

  const doneTasks = state.tasks.filter((t) => t.status === 'done')

  const handleCleanCompleted = async () => {
    if (doneTasks.length === 0) return
    if (!window.confirm(`Clean up and remove ${doneTasks.length} completed task(s)?`)) return

    setIsCleaningDone(true)
    try {
      await Promise.all(doneTasks.map((t) => deleteTask(t.id)))
      await state.load()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to clean up some completed tasks.')
    } finally {
      setIsCleaningDone(false)
    }
  }

  return (
    <section className="tasks-page" aria-labelledby="tasks-title">
      <header className="tasks-page__header">
        <div>
          <p className="page-eyebrow">Work management</p>
          <h1 id="tasks-title">Tasks</h1>
          <p className="page-description">Plan and track manual work across your AI office.</p>
        </div>
        <button className="tasks-primary-button" onClick={() => openForm()}>
          Create Task
        </button>
      </header>

      <PlanningPanel onApproved={state.load} onOpenArtifact={onOpenArtifact} />

      <div className="tasks-toolbar" role="toolbar" aria-label="Task board filters and actions">
        <label>
          Search
          <input
            type="search"
            className="tasks-search-input"
            placeholder="Filter by keyword..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search tasks by title or description"
          />
        </label>

        <label>
          Status
          <select
            value={state.statusFilter}
            onChange={(e) => state.setStatusFilter(e.target.value as TaskStatus | '')}
          >
            <option value="">All statuses</option>
            {columns.map((c) => (
              <option key={c.status} value={c.status}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Agent
          <select
            value={state.agentFilter}
            onChange={(e) => state.setAgentFilter(e.target.value as AgentId | '')}
          >
            <option value="">All agents</option>
            {state.agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Priority
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value as TaskPriority | '')}
          >
            <option value="">All priorities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>

        <button
          type="button"
          className="tasks-cleanup-button"
          disabled={doneTasks.length === 0 || isCleaningDone}
          onClick={handleCleanCompleted}
          title="Delete all completed tasks to declutter board"
        >
          🧹 {isCleaningDone ? 'Cleaning…' : `Clean Up Done (${doneTasks.length})`}
        </button>

        <span className="tasks-toolbar__meta">
          {filteredTasks.length} {filteredTasks.length === 1 ? 'task' : 'tasks'}
        </span>
      </div>

      {state.error && (
        <div className="tasks-state tasks-state--error" role="alert">
          {state.error}
          <button onClick={() => void state.load()}>Retry</button>
        </div>
      )}

      {state.loading ? (
        <div className="tasks-state">Loading tasks…</div>
      ) : (
        <div className="task-board">
          {columns.map((column) => {
            const columnTasks = filteredTasks.filter((t) => t.status === column.status)
            return (
              <section className={`task-column task-column--${column.status}`} key={column.status}>
                <header>
                  <div className="task-column__title">
                    <span className={`task-column__dot task-column__dot--${column.status}`} aria-hidden="true" />
                    <h2>{column.label}</h2>
                  </div>
                  <span className="task-column__badge">{columnTasks.length}</span>
                </header>
                <div className="task-column__list">
                  {columnTasks.map((task) => (
                    <article className="task-card" key={task.id} onClick={() => setViewing(task)}>
                      <div className="task-card__top">
                        <span className={`task-priority task-priority--${task.priority}`}>{task.priority}</span>
                        {(() => {
                          const agent = agentInfo(task.assigned_agent_id)
                          return (
                            <span className={`task-card__agent task-card__agent--${agent.modifier}`}>
                              <span className="task-card__agent-icon" aria-hidden="true">
                                {agent.icon}
                              </span>
                              <span>{agent.name}</span>
                            </span>
                          )
                        })()}
                      </div>
                      <h3>{task.title}</h3>
                      <p>{task.description || 'No description'}</p>
                      <div className="task-card__bottom">
                        <time>{new Date(task.created_at).toLocaleDateString()}</time>
                        <select
                          aria-label={`Change status for ${task.title}`}
                          value={task.status}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => void state.changeStatus(task.id, e.target.value as TaskStatus)}
                        >
                          {columns.map((c) => (
                            <option key={c.status} value={c.status}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </article>
                  ))}
                  {columnTasks.length === 0 && (
                    <div className="task-column__empty">
                      <span aria-hidden="true">📭</span>
                      <p>No tasks</p>
                    </div>
                  )}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {showForm && (
        <div className="task-dialog-backdrop" role="presentation">
          <form className="task-dialog" onSubmit={submit}>
            <header>
              <h2>{editing ? 'Edit Task' : 'Create Task'}</h2>
              <button type="button" aria-label="Close task form" onClick={() => setShowForm(false)}>
                ×
              </button>
            </header>
            <label>
              Title
              <input
                required
                maxLength={200}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label>
              Description
              <textarea
                maxLength={5000}
                value={form.description ?? ''}
                onChange={(e) => setForm({ ...form, description: e.target.value || null })}
              />
            </label>
            <div className="task-form-grid">
              <label>
                Status
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value as TaskStatus })}
                >
                  {columns.map((c) => (
                    <option key={c.status} value={c.status}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Priority
                <select
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value as TaskPriority })}
                >
                  {['low', 'medium', 'high'].map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Assigned Agent
              <select
                value={form.assigned_agent_id ?? ''}
                onChange={(e) =>
                  setForm({ ...form, assigned_agent_id: (e.target.value || null) as AgentId | null })
                }
              >
                <option value="">Unassigned</option>
                {state.agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <footer>
              <button type="button" onClick={() => setShowForm(false)}>
                Cancel
              </button>
              <button className="tasks-primary-button" disabled={saving}>
                {saving ? 'Saving…' : 'Save Task'}
              </button>
            </footer>
          </form>
        </div>
      )}

      {viewing && (
        <div className="task-dialog-backdrop" role="presentation">
          <section
            className="task-dialog task-details task-execution-details"
            role="dialog"
            aria-modal="true"
            aria-label="Task details"
          >
            <header>
              <h2>{viewing.title}</h2>
              <button aria-label="Close task details" onClick={() => setViewing(null)}>
                X
              </button>
            </header>
            <p>{viewing.description || 'No description.'}</p>
            <dl>
              <div>
                <dt>Status</dt>
                <dd>{viewing.status}</dd>
              </div>
              <div>
                <dt>Priority</dt>
                <dd>{viewing.priority}</dd>
              </div>
              <div>
                <dt>Agent</dt>
                <dd>{agentName(viewing.assigned_agent_id)}</dd>
              </div>
            </dl>
            <section className="execution-section" aria-labelledby="execution-history-title">
              <div className="execution-section__header">
                <h3 id="execution-history-title">Execution History</h3>
                {canRun(viewing) && (
                  <button
                    className="tasks-primary-button"
                    disabled={runningTaskId !== null}
                    onClick={() => void runTask(viewing)}
                  >
                    {runningTaskId === viewing.id
                      ? 'Agent is working...'
                      : executions[0]?.status === 'failed'
                        ? 'Retry Task'
                        : 'Run Task'}
                  </button>
                )}
              </div>
              {executionError && (
                <p className="planning-error" role="alert">
                  {executionError}
                </p>
              )}
              {executionLoading ? (
                <p className="execution-empty">Loading execution history...</p>
              ) : executions.length === 0 ? (
                <p className="execution-empty">This task has not been run.</p>
              ) : (
                <ol className="execution-list">
                  {executions.map((execution) => (
                    <li key={execution.id}>
                      <details open={execution.id === executions[0]?.id}>
                        <summary>
                          <span className={`execution-status execution-status--${execution.status}`}>
                            {execution.status}
                          </span>
                          <span>{agentName(execution.agent_id)}</span>
                          <time>{new Date(execution.started_at).toLocaleString()}</time>
                        </summary>
                        {execution.output_content && <pre>{execution.output_content}</pre>}
                        {execution.error_message && (
                          <p className="execution-error">
                            {execution.error_code}: {execution.error_message}
                          </p>
                        )}
                      </details>
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <footer>
              <button
                onClick={() => {
                  setViewing(null)
                  openForm(viewing)
                }}
              >
                Edit Task
              </button>
              <button
                className="task-delete-button"
                onClick={() => {
                  if (confirm(`Delete "${viewing.title}"?`)) {
                    void state.remove(viewing.id).then(() => setViewing(null))
                  }
                }}
              >
                Delete
              </button>
            </footer>
          </section>
        </div>
      )}
    </section>
  )
}
