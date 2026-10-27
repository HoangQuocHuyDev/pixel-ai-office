import type { WorkflowTimelineData } from '../types'

export default function WorkflowProgress({ progress }: { progress: WorkflowTimelineData['progress'] }) {
  return <section className="timeline-progress" aria-label="Workflow progress"><div><strong>{progress.completed_tasks}/{progress.total_tasks} tasks completed</strong><span>{progress.progress_percentage}%</span></div><div className="workflow-progress"><span style={{ width: `${progress.progress_percentage}%` }}/></div><ul><li>{progress.running_tasks} running</li><li>{progress.pending_tasks} pending</li><li>{progress.failed_tasks} failed</li><li>{progress.cancelled_tasks} cancelled</li></ul></section>
}
