import { Fragment } from 'react'
import { useWorkflowTimeline } from '../hooks/useWorkflowTimeline'
import WorkflowFinalReport from './WorkflowFinalReport'
import WorkflowHandoffCard from './WorkflowHandoffCard'
import WorkflowProgress from './WorkflowProgress'
import WorkflowStepCard from './WorkflowStepCard'

export default function WorkflowTimeline({
  workflowId,
  onClose,
  onOpenArtifact,
  onRetryRun,
}: {
  workflowId: number
  onClose: () => void
  onOpenArtifact: (id: number) => void
  onRetryRun?: (runId: number) => Promise<void> | void
}) {
  const state = useWorkflowTimeline(workflowId)
  const data = state.data

  return (
    <div
      className="task-dialog-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <section
        className="task-dialog workflow-timeline"
        role="dialog"
        aria-modal="true"
        aria-labelledby="timeline-title"
      >
        <header>
          <div>
            <span className="page-eyebrow">Workflow Run #{workflowId}</span>
            <h2 id="timeline-title">{data?.plan.title ?? 'Execution Timeline'}</h2>
          </div>
          <button aria-label="Close workflow timeline" onClick={onClose}>
            ×
          </button>
        </header>

        {state.error && (
          <div className="workflow-timeline__state workflow-timeline__state--error" role="alert">
            {state.error}
            <button onClick={state.refresh}>Retry</button>
          </div>
        )}

        {state.loading && !data ? (
          <div className="workflow-timeline__state">Loading execution timeline…</div>
        ) : (
          data && (
            <>
              <div className="workflow-timeline__meta">
                <span className={`execution-status execution-status--${data.status}`}>
                  {data.status}
                </span>
                <span>Started {new Date(data.started_at).toLocaleString()}</span>
                <span>Plan approved, but a distinct approval timestamp is not stored.</span>
                {data.retried_from_run_id && (
                  <span className="workflow-lineage-tag">
                    Retried from Run #{data.retried_from_run_id}
                  </span>
                )}
                {data.retry_run_ids && data.retry_run_ids.length > 0 && (
                  <span className="workflow-lineage-tag">
                    Retried in Run #{data.retry_run_ids.join(', #')}
                  </span>
                )}
              </div>

              <WorkflowProgress progress={data.progress} />

              {data.failed_task_title && data.status === 'failed' && (
                <p className="workflow-failed-task">
                  <strong>Failed step:</strong> {data.failed_task_title}
                </p>
              )}

              {data.error_message && (
                <div className="workflow-timeline__error-banner">
                  <p className="execution-error">
                    {data.error_code}: {data.error_message}
                  </p>
                  {data.can_retry && onRetryRun && (
                    <button
                      className="tasks-primary-button workflow-retry-inline-btn"
                      onClick={() => {
                        if (confirm('Retry this failed workflow? Completed steps will be preserved.')) {
                          void onRetryRun(data.workflow_id)
                        }
                      }}
                    >
                      Retry Workflow
                    </button>
                  )}
                  {!data.can_retry && data.retry_block_reason && (
                    <p className="workflow-retry-blocked">
                      <em>{data.retry_block_reason}</em>
                    </p>
                  )}
                </div>
              )}

              <ol className="workflow-timeline__steps">
                {data.steps.map((step) => {
                  const stepHandoffs =
                    data.handoffs?.filter((h) => h.source_task_id === step.task_id) ?? []
                  return (
                    <Fragment key={step.task_id}>
                      <WorkflowStepCard step={step} onOpenArtifact={onOpenArtifact} />
                      {stepHandoffs.map((handoff) => (
                        <WorkflowHandoffCard
                          key={handoff.id}
                          handoff={handoff}
                          onOpenArtifact={onOpenArtifact}
                        />
                      ))}
                    </Fragment>
                  )
                })}
              </ol>

              <WorkflowFinalReport
                finalization={data.finalization}
                onOpenArtifact={onOpenArtifact}
              />

              <p className="workflow-timeline__scope">{data.execution_scope_note}</p>
            </>
          )
        )}
      </section>
    </div>
  )
}
