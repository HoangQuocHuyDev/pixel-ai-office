import { useEffect, useState } from 'react'
import { artifactDownloadUrl } from '../api/artifactClient'
import type { ArtifactDetail } from '../types'
import ArtifactEditor from './ArtifactEditor'
import ArtifactVersionHistory from './ArtifactVersionHistory'

const MAX_RENDER_CHARS = 200_000

export default function ArtifactViewer({ artifact, onClose, onOpenTasks, onUpdated }: { artifact: ArtifactDetail; onClose: () => void; onOpenTasks: () => void; onUpdated: () => void }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const [mode, setMode] = useState<'view' | 'edit' | 'history'>('view')
  const [dirty, setDirty] = useState(false)
  const visibleContent = artifact.content.slice(0, MAX_RENDER_CHARS)
  const copy = async () => {
    try { await navigator.clipboard.writeText(artifact.content); setCopyState('copied') }
    catch { setCopyState('failed') }
  }
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  const safely = (action: () => void) => { if (!dirty || confirm('Discard unsaved changes?')) { setDirty(false); action() } }
  return <div className="task-dialog-backdrop" role="presentation"><section className="task-dialog artifact-viewer" role="dialog" aria-modal="true" aria-labelledby="artifact-title">
    <header><div><span className={`artifact-type artifact-type--${artifact.artifact_type}`}>{artifact.artifact_type}</span><h2 id="artifact-title">{artifact.title}</h2></div><button aria-label="Close artifact" onClick={() => safely(onClose)}>×</button></header>
    <dl><div><dt>Agent</dt><dd>{artifact.agent_name ?? 'Unknown'}</dd></div><div><dt>Format</dt><dd>{artifact.content_format}{artifact.language ? ` · ${artifact.language}` : ''}</dd></div><div><dt>Created</dt><dd>{new Date(artifact.created_at).toLocaleString()}</dd></div><div><dt>Size</dt><dd>{(artifact.content_size ?? artifact.content?.length ?? 0).toLocaleString()} characters</dd></div></dl>
    <nav className="artifact-viewer__tabs" aria-label="Artifact modes"><button className={mode === 'view' ? 'active' : ''} onClick={() => safely(() => setMode('view'))}>View</button><button className={mode === 'edit' ? 'active' : ''} onClick={() => setMode('edit')}>Edit</button><button className={mode === 'history' ? 'active' : ''} onClick={() => safely(() => setMode('history'))}>Version History</button><span>Version {artifact.current_version_number}</span></nav>
    {mode === 'view' && <><div className="artifact-viewer__actions"><button onClick={() => void copy()}>{copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed — retry' : 'Copy content'}</button><a href={artifactDownloadUrl(artifact.id)}>Download current version</a>{(artifact.task_id || artifact.workflow_run_id) && <button onClick={onOpenTasks}>Open related work</button>}</div><pre className={`artifact-content artifact-content--${artifact.content_format}`}>{visibleContent}</pre>{artifact.content.length > MAX_RENDER_CHARS && <p className="artifact-viewer__notice">Preview limited to {MAX_RENDER_CHARS.toLocaleString()} characters. Download to view the complete artifact.</p>}</>}
    {mode === 'edit' && <ArtifactEditor artifact={artifact} onDirtyChange={setDirty} onCancel={() => safely(() => setMode('view'))} onReloadLatest={() => safely(() => { onUpdated(); setMode('view') })} onSaved={() => { setDirty(false); onUpdated(); setMode('view') }}/>} 
    {mode === 'history' && <ArtifactVersionHistory artifact={artifact} onUpdated={onUpdated}/>} 
  </section></div>
}
