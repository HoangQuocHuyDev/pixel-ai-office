import { useState, type FormEvent } from 'react'
import { usePlanning } from '../hooks/usePlanning'
import WorkflowControls from './WorkflowControls'

export default function PlanningPanel({ onApproved, onOpenArtifact }: { onApproved: () => void | Promise<void>; onOpenArtifact: (artifactId: number) => void }) {
  const [objective, setObjective] = useState('')
  const planning = usePlanning(onApproved)
  const submit = (event: FormEvent) => { event.preventDefault(); if (objective.trim().length >= 10) void planning.generate(objective) }

  return <section className="planning-panel" aria-labelledby="planning-title">
    <header><div><p className="page-eyebrow">Manager AI planning</p><h2 id="planning-title">Turn an objective into an approved plan</h2><p>This structured workflow is separate from regular Manager chat. Nothing is saved until approval.</p></div></header>
    <form className="planning-request" onSubmit={submit}>
      <label htmlFor="planning-objective">Objective</label>
      <div><textarea id="planning-objective" required minLength={10} maxLength={5000} value={objective} disabled={planning.generating || planning.approving} onChange={(event) => setObjective(event.target.value)} placeholder="Describe the outcome you want Manager AI to plan..."/><button className="tasks-primary-button" disabled={planning.generating || planning.approving || objective.trim().length < 10}>{planning.generating ? 'Manager is analyzing...' : planning.proposal ? 'Regenerate Plan' : 'Generate Plan'}</button></div>
    </form>
    {planning.error && <p className="planning-error" role="alert">{planning.error}</p>}
    {planning.proposal && <section className="plan-proposal" aria-label="Plan proposal">
      <header><div><span>Draft proposal</span><h3>{planning.proposal.title}</h3><p>{planning.proposal.objective}</p></div><span>{planning.proposal.tasks.length} tasks</span></header>
      <ol>{planning.proposal.tasks.map((task) => <li key={task.sequence_order}><span className="plan-sequence">{task.sequence_order}</span><div><h4>{task.title}</h4><p>{task.description}</p><div className="plan-task-meta"><span className={`task-priority task-priority--${task.priority}`}>{task.priority}</span><span>{task.assigned_agent_id === 'developer' ? 'Developer AI' : 'Researcher AI'}</span></div></div></li>)}</ol>
      <footer><button type="button" onClick={planning.cancel} disabled={planning.approving}>Cancel</button><button type="button" className="tasks-primary-button" onClick={() => void planning.approve()} disabled={planning.approving}>{planning.approving ? 'Approving...' : 'Approve Plan'}</button></footer>
    </section>}
    {planning.plans.length > 0 && <div className="approved-plans"><h3>Approved plans</h3><div>{planning.plans.map((plan) => <button type="button" key={plan.id} onClick={() => void planning.selectPlan(plan.id)}><span>{plan.title}</span><time>{new Date(plan.created_at).toLocaleDateString()}</time></button>)}</div></div>}
    {planning.selectedPlan && <div className="task-dialog-backdrop" role="presentation"><section className="task-dialog plan-details" role="dialog" aria-modal="true" aria-label="Approved plan details"><header><div><span className="plan-status">Approved</span><h2>{planning.selectedPlan.title}</h2></div><button aria-label="Close plan details" onClick={() => planning.setSelectedPlan(null)}>X</button></header><p>{planning.selectedPlan.objective}</p><ol>{planning.selectedPlan.tasks.map((task) => <li key={task.id}><strong>{task.sequence_order}. {task.title}</strong><span>{task.assigned_agent_id} / {task.priority}</span></li>)}</ol><WorkflowControls planId={planning.selectedPlan.id} onTerminal={onApproved} onOpenArtifact={onOpenArtifact}/><footer><button onClick={() => planning.setSelectedPlan(null)}>Close</button></footer></section></div>}
  </section>
}
