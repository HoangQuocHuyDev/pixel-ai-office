import { useState } from 'react'
import type { WorkflowHandoff } from '../types'

interface WorkflowHandoffCardProps {
  handoff: WorkflowHandoff
  onOpenArtifact: (id: number) => void
}

export default function WorkflowHandoffCard({ handoff, onOpenArtifact }: WorkflowHandoffCardProps) {
  const [expanded, setExpanded] = useState(false)
  const sourceName = handoff.source_agent_name ?? handoff.source_agent_id
  const targetName = handoff.target_agent_name ?? handoff.target_agent_id
  const hasDetails = (handoff.key_findings && handoff.key_findings.length > 0) ||
    (handoff.deliverables && handoff.deliverables.length > 0) ||
    Boolean(handoff.next_steps) ||
    (handoff.artifacts && handoff.artifacts.length > 0)

  return (
    <li className="timeline-handoff" data-testid="timeline-handoff">
      <div className="timeline-handoff__connector">
        <span className="timeline-handoff__badge">Handoff</span>
      </div>
      <article className="timeline-handoff__content">
        <header className="timeline-handoff__header">
          <div className="timeline-handoff__agents">
            <span className="timeline-handoff__agent timeline-handoff__agent--source">{sourceName}</span>
            <span className="timeline-handoff__arrow" aria-hidden="true">➔</span>
            <span className="timeline-handoff__agent timeline-handoff__agent--target">{targetName}</span>
          </div>
          <span className="timeline-handoff__target-task">For: {handoff.target_task_title}</span>
        </header>
        <p className="timeline-handoff__summary">{handoff.summary}</p>

        {hasDetails && (
          <details
            className="timeline-handoff__details"
            open={expanded}
            onToggle={(e) => setExpanded((e.currentTarget as HTMLDetailsElement).open)}
          >
            <summary className="timeline-handoff__summary-toggle">
              {expanded ? 'Hide handoff details' : 'View handoff details'}
              {handoff.key_findings?.length ? ` (${handoff.key_findings.length} findings` : ''}
              {handoff.deliverables?.length ? `, ${handoff.deliverables.length} deliverables` : ''}
              {handoff.key_findings?.length || handoff.deliverables?.length ? ')' : ''}
            </summary>

            <div className="timeline-handoff__body">
              {handoff.key_findings && handoff.key_findings.length > 0 && (
                <section className="timeline-handoff__section">
                  <h4>Key Findings</h4>
                  <ul>
                    {handoff.key_findings.map((finding, idx) => (
                      <li key={idx}>{finding}</li>
                    ))}
                  </ul>
                </section>
              )}

              {handoff.deliverables && handoff.deliverables.length > 0 && (
                <section className="timeline-handoff__section">
                  <h4>Deliverables</h4>
                  <ul>
                    {handoff.deliverables.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}

              {handoff.next_steps && (
                <section className="timeline-handoff__section">
                  <h4>Next Steps</h4>
                  <p>{handoff.next_steps}</p>
                </section>
              )}

              {handoff.artifacts && handoff.artifacts.length > 0 && (
                <section className="timeline-handoff__section">
                  <h4>Referenced Artifacts</h4>
                  <div className="timeline-artifacts">
                    {handoff.artifacts.map((artifact) => (
                      <button
                        key={artifact.id}
                        type="button"
                        onClick={() => onOpenArtifact(artifact.id)}
                      >
                        Open artifact: {artifact.title}
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </details>
        )}
      </article>
    </li>
  )
}

