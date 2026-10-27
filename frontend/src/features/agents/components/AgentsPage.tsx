import { useEffect, useState } from 'react'
import { fetchAgents } from '../api/agentClient'
import { useAgentActivities } from '../hooks/useAgentActivities'
import { useAgentMonitoring } from '../hooks/useAgentMonitoring'
import type { AgentExecution, AgentId, AgentMetadata } from '../types'

const formatTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : 'No activity yet'
const formatDuration = (value: number | null) => value === null ? '—' : `${value.toFixed(value < 10 ? 1 : 0)}s`

export default function AgentsPage({ onOpenTasks }: { onOpenTasks: () => void }) {
  const [selectedId, setSelectedId] = useState<AgentId>('manager')
  const [agents, setAgents] = useState<AgentMetadata[]>([])
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [result, setResult] = useState<AgentExecution | null>(null)
  const activities = useAgentActivities()
  const state = useAgentMonitoring(selectedId)

  useEffect(() => {
    const controller = new AbortController()
    void fetchAgents(controller.signal).then(setAgents).catch((reason) => {
      if (!controller.signal.aborted) setAgentsError(reason instanceof Error ? reason.message : 'Unable to load agents.')
    })
    return () => controller.abort()
  }, [])
  useEffect(() => setResult(null), [selectedId])

  const selected = state.monitoring
  return <section className="agents-page" aria-labelledby="agents-title">
    <header className="agents-page__header">
      <div><p className="page-eyebrow">Operations overview</p><h1 id="agents-title">Agent Monitoring</h1><p className="page-description">Monitor AI agents and their execution history.</p></div>
      <div className="agents-connection"><span className={`agents-status-dot agents-status-dot--${activities.connection}`} />{activities.connection}<small>Last updated {selected ? formatTime(selected.current_activity.updated_at) : '—'}</small><button onClick={state.refresh}>Refresh</button></div>
    </header>

    {state.summary && <div className="agents-summary" aria-label="Monitoring summary">
      {[['Total Agents', state.summary.total_agents], ['Working', state.summary.working_agents], ['Completed Executions', state.summary.completed_executions], ['Active Workflows', state.summary.active_workflows]].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}
    </div>}
    {(agentsError || state.error) && <div className="agents-state agents-state--error" role="alert">{agentsError || state.error}<button onClick={state.refresh}>Retry</button></div>}
    {state.loading && !selected && <div className="agents-state">Loading monitoring data…</div>}

    <div className="agents-grid">
      {agents.map((agent) => {
        const activity = activities.activities.find((item) => item.agent_id === agent.id)
        return <button key={agent.id} className={`agent-monitor-card${selectedId === agent.id ? ' agent-monitor-card--selected' : ''}`} onClick={() => setSelectedId(agent.id)}>
          <span className="agent-monitor-card__top"><span className="agent-avatar">{agent.name.charAt(0)}</span><span className={`agent-status-badge agent-status-badge--${activity?.status ?? 'idle'}`}>{activity?.status ?? 'idle'}</span></span>
          <strong>{agent.name}</strong><small>{agent.role}</small><p>{agent.description}</p>
          <span>Current task: {activity?.current_task_title ?? 'None'}</span><span>Workflow: {activity?.workflow_run_id ? `#${activity.workflow_run_id}` : 'None'}</span>
        </button>
      })}
    </div>

    {selected && <div className="agent-detail">
      <section className="agent-detail__overview">
        <div><p className="page-eyebrow">Selected agent</p><h2>{selected.agent.name}</h2><p>{selected.agent.description}</p></div>
        <span className={`agent-status-badge agent-status-badge--${selected.current_activity.status}`}>{selected.current_activity.status}</span>
        <dl className="agent-current-grid">
          <div><dt>Current task</dt><dd>{selected.current_task?.title ?? 'No active task'}</dd></div>
          <div><dt>Current workflow</dt><dd>{selected.current_workflow ? `${selected.current_workflow.plan_title} (#${selected.current_workflow.id})` : 'No active workflow'}</dd></div>
          <div><dt>Last active</dt><dd>{formatTime(selected.statistics.last_active_at)}</dd></div>
          <div><dt>Role</dt><dd>{selected.agent.role}</dd></div>
        </dl>
        {(selected.current_task || selected.current_workflow) && <button className="agents-link-button" onClick={onOpenTasks}>Open related work in Tasks</button>}
      </section>

      <section className="agent-statistics" aria-label="Agent execution statistics">
        {[['Total', selected.statistics.total_executions], ['Completed', selected.statistics.completed_executions], ['Failed', selected.statistics.failed_executions], ['Cancelled', selected.statistics.cancelled_executions], ['Success rate', selected.statistics.success_rate === null ? '—' : `${selected.statistics.success_rate}%`], ['Avg. duration', formatDuration(selected.statistics.average_duration_seconds)]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </section>

      <div className="agent-monitoring-columns">
        <section className="agent-history"><header><h2>Execution History</h2><span>{selected.recent_executions.length} recent</span></header>
          {selected.recent_executions.length === 0 ? <p className="agents-empty">No executions for this agent.</p> : <ol>{selected.recent_executions.map((execution) => <li key={execution.id}><div><span className={`execution-status execution-status--${execution.status}`}>{execution.status}</span><strong>{execution.task_title}</strong><time>{formatTime(execution.started_at)}</time></div><span>{formatDuration(execution.duration_seconds)}</span><button onClick={() => setResult(execution)}>View result</button></li>)}</ol>}
        </section>
        <section className="agent-timeline"><header><h2>Activity Timeline</h2><span>{state.timeline?.total ?? 0} events</span></header>
          {!state.timeline?.items.length ? <p className="agents-empty">No recorded activity.</p> : <ol>{state.timeline.items.map((event) => <li key={event.event_id} className={`agent-timeline__event agent-timeline__event--${event.status}`}><span className="agent-timeline__marker"/><div><strong>{event.description}</strong><span>{event.event_type.replaceAll('_', ' ')}</span><time>{formatTime(event.timestamp)}</time></div></li>)}</ol>}
        </section>
      </div>
    </div>}

    {result && <div className="task-dialog-backdrop" role="presentation"><section className="task-dialog agent-result-viewer" role="dialog" aria-modal="true" aria-labelledby="result-title"><header><h2 id="result-title">Execution Result</h2><button aria-label="Close result viewer" onClick={() => setResult(null)}>×</button></header><dl><div><dt>Task</dt><dd>{result.task_title}</dd></div><div><dt>Status</dt><dd>{result.status}</dd></div><div><dt>Execution</dt><dd>#{result.id}</dd></div></dl>{result.output_content ? <pre>{result.output_content}</pre> : result.error_message ? <p className="agents-result-error">{result.error_code}: {result.error_message}</p> : <p className="agents-empty">No result content is available.</p>}<footer><button onClick={() => setResult(null)}>Close</button><button className="tasks-primary-button" onClick={onOpenTasks}>Open Tasks</button></footer></section></div>}
  </section>
}
