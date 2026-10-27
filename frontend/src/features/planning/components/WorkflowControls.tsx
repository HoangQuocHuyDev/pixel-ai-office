import { useState } from 'react'
import WorkflowTimeline from '../../workflows/components/WorkflowTimeline'
import { useWorkflow } from '../hooks/useWorkflow'

export default function WorkflowControls({ planId, onTerminal, onOpenArtifact }: { planId: number; onTerminal: () => void | Promise<void>; onOpenArtifact: (artifactId: number) => void }) {
  const workflow = useWorkflow(planId, onTerminal)
  const [timelineRunId, setTimelineRunId] = useState<number | null>(null)
  const run = workflow.run
  const isActive = run?.status === 'pending' || run?.status === 'running'
  const isFailed = run?.status === 'failed'
  const percent = run && run.total_tasks ? Math.round((run.completed_tasks / run.total_tasks) * 100) : 0

  const handleRetry = async () => {
    if (!run || !run.can_retry || workflow.retrying || isActive) return
    const confirmed = confirm(
      'Retry this failed workflow? Completed steps will be preserved, and execution will resume from the failed step.'
    )
    if (!confirmed) return
    const newRun = await workflow.retry(run.id)
    if (newRun) {
      setTimelineRunId(newRun.id)
    }
  }

  return <section className="workflow-controls" aria-labelledby="workflow-title">
    <div className="workflow-controls__header">
      <div>
        <span className="page-eyebrow">Manager orchestration</span>
        <h3 id="workflow-title">Automatic Workflow</h3>
      </div>
      <div className="workflow-controls__actions">
        {isActive ? (
          <button className="workflow-cancel" onClick={() => { if (confirm('Cancel this workflow? Completed steps will remain saved.')) void workflow.cancel() }}>Cancel Workflow</button>
        ) : (
          <>
            {isFailed && run.can_retry && (
              <button
                className="workflow-retry-button tasks-primary-button"
                disabled={workflow.retrying || workflow.starting}
                onClick={() => void handleRetry()}
              >
                {workflow.retrying ? 'Retrying...' : 'Retry Workflow'}
              </button>
            )}
            <button
              className="tasks-primary-button"
              disabled={workflow.starting || workflow.loading || workflow.retrying}
              onClick={() => void workflow.start()}
            >
              {workflow.starting ? 'Starting...' : run ? 'Start New Run' : 'Start Workflow'}
            </button>
          </>
        )}
      </div>
    </div>
    {workflow.error && <p className="planning-error" role="alert">{workflow.error}</p>}
    {workflow.loading ? <p className="workflow-empty">Loading workflow status...</p> : !run ? <p className="workflow-empty">No workflow has been started. Tasks will only run after explicit confirmation.</p> : <div className="workflow-status">
      <div className="workflow-status__row">
        <span className={`execution-status execution-status--${run.status}`}>{run.status}</span>
        <strong>{run.completed_tasks}/{run.total_tasks} tasks</strong>
        <span>{percent}%</span>
        {run.retried_from_run_id && <span className="workflow-lineage-tag">Retried from Run #{run.retried_from_run_id}</span>}
      </div>
      <div className="workflow-progress"><span style={{ width: `${percent}%` }} /></div>
      {run.current_task_title && <p><strong>Current task:</strong> {run.current_task_title}{run.current_agent_id ? ` · ${run.current_agent_id}` : ''}</p>}
      {run.failed_task_title && isFailed && <p className="workflow-failed-task"><strong>Failed step:</strong> {run.failed_task_title}</p>}
      {run.error_message && <p className="execution-error">{run.error_code}: {run.error_message}</p>}
      {isFailed && !run.can_retry && run.retry_block_reason && (
        <p className="workflow-retry-blocked"><em>{run.retry_block_reason}</em></p>
      )}
      {run.final_report && <section className="workflow-report"><h4>Manager Final Report</h4><pre>{run.final_report}</pre></section>}
      <button className="workflow-timeline-button" onClick={() => setTimelineRunId(run.id)}>View Execution Timeline</button>
    </div>}
    {workflow.history.length > 1 && <details className="workflow-history"><summary>Previous runs ({workflow.history.length - 1})</summary><ul>{workflow.history.slice(1).map((item) => <li key={item.id}><span>Run #{item.id}: {item.status} · {item.completed_tasks}/{item.total_tasks}{item.retried_from_run_id ? ` (retried from #${item.retried_from_run_id})` : ''}</span><button onClick={() => setTimelineRunId(item.id)}>View timeline</button></li>)}</ul></details>}
    {timelineRunId !== null && <WorkflowTimeline workflowId={timelineRunId} onClose={() => setTimelineRunId(null)} onOpenArtifact={onOpenArtifact} onRetryRun={async (rid) => { const created = await workflow.retry(rid); if (created) setTimelineRunId(created.id); }} />} 
  </section>
}
