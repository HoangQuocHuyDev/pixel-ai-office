import { useEffect, useState } from 'react'
import { fetchArtifact } from '../api/artifactClient'
import { useArtifacts } from '../hooks/useArtifacts'
import type { ArtifactDetail, ArtifactType } from '../types'
import ArtifactViewer from './ArtifactViewer'

const types: Array<ArtifactType | ''> = ['', 'document', 'code', 'research', 'report']

export default function WorkspacePage({ onOpenTasks, initialArtifactId = null }: { onOpenTasks: () => void; initialArtifactId?: number | null }) {
  const state = useArtifacts()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [selected, setSelected] = useState<ArtifactDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailRefresh, setDetailRefresh] = useState(0)
  useEffect(() => { if (initialArtifactId !== null) setSelectedId(initialArtifactId) }, [initialArtifactId])
  useEffect(() => {
    if (selectedId === null) { setSelected(null); return }
    const controller = new AbortController(); setDetailError(null)
    void fetchArtifact(selectedId, controller.signal).then(setSelected).catch((reason) => { if (!controller.signal.aborted) setDetailError(reason instanceof Error ? reason.message : 'Unable to load artifact.') })
    return () => controller.abort()
  }, [selectedId, detailRefresh])
  const page = Math.floor(state.filters.offset / 12) + 1
  const pages = Math.max(1, Math.ceil((state.data?.total ?? 0) / 12))
  return <section className="workspace-page" aria-labelledby="workspace-page-title">
    <header className="workspace-page__header"><div><p className="page-eyebrow">Generated knowledge</p><h1 id="workspace-page-title">Workspace</h1><p className="page-description">Browse AI-generated documents, code and reports.</p></div><div><strong>{state.summary?.total_artifacts ?? 0}</strong><span>artifacts</span><button onClick={state.refresh}>Refresh</button></div></header>
    {state.summary && <div className="workspace-summary">{[['Total Artifacts', state.summary.total_artifacts], ['Documents', state.summary.documents], ['Code', state.summary.code], ['Research', state.summary.research], ['Reports', state.summary.reports]].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</div>}
    <div className="workspace-toolbar"><label>Search<input type="search" placeholder="Search artifact titles…" value={state.filters.search} onChange={(event) => state.updateFilters({ search: event.target.value })}/></label><label>Type<select value={state.filters.artifactType} onChange={(event) => state.updateFilters({ artifactType: event.target.value as ArtifactType | '' })}>{types.map((type) => <option key={type || 'all'} value={type}>{type || 'All types'}</option>)}</select></label><label>Agent<select value={state.filters.agentId} onChange={(event) => state.updateFilters({ agentId: event.target.value as typeof state.filters.agentId })}><option value="">All agents</option><option value="manager">Manager AI</option><option value="developer">Developer AI</option><option value="researcher">Researcher AI</option></select></label></div>
    {state.error && <div className="workspace-state workspace-state--error" role="alert">{state.error}<button onClick={state.refresh}>Retry</button></div>}
    {detailError && <div className="workspace-state workspace-state--error" role="alert">{detailError}</div>}
    {state.loading ? <div className="workspace-state">Loading artifacts…</div> : !state.data?.items.length ? <div className="workspace-empty"><h2>No artifacts yet</h2><p>Artifacts appear here after an AI agent successfully completes a task or Manager produces a final report.</p></div> : <div className="artifact-list">{state.data.items.map((artifact) => <button key={artifact.id} className="artifact-card" onClick={() => setSelectedId(artifact.id)}><span className="artifact-card__top"><span className={`artifact-type artifact-type--${artifact.artifact_type}`}>{artifact.artifact_type}</span><time>{new Date(artifact.created_at).toLocaleString()}</time></span><strong>{artifact.title}</strong><p>{artifact.preview}</p><span>{artifact.agent_name ?? 'Unknown agent'} · {artifact.task_title ?? artifact.workflow_title ?? 'Workflow artifact'}</span><small>{artifact.content_size.toLocaleString()} characters</small></button>)}</div>}
    {(state.data?.total ?? 0) > 0 && <nav className="workspace-pagination" aria-label="Artifact pages"><button disabled={page <= 1} onClick={() => state.updateFilters({ offset: Math.max(0, state.filters.offset - 12) })}>Previous</button><span>Page {page} of {pages}</span><button disabled={page >= pages} onClick={() => state.updateFilters({ offset: state.filters.offset + 12 })}>Next</button></nav>}
    {selected && <ArtifactViewer artifact={selected} onClose={() => setSelectedId(null)} onOpenTasks={onOpenTasks} onUpdated={() => { setDetailRefresh((value) => value + 1); state.refresh() }}/>} 
  </section>
}
