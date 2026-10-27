import { useEffect, useState } from 'react'
import { ArtifactApiError, saveArtifactVersion } from '../api/artifactClient'
import type { ArtifactDetail, ArtifactVersionDetail, ContentFormat } from '../types'

export default function ArtifactEditor({ artifact, onCancel, onSaved, onDirtyChange, onReloadLatest }: { artifact: ArtifactDetail; onCancel: () => void; onSaved: (version: ArtifactVersionDetail) => void; onDirtyChange: (dirty: boolean) => void; onReloadLatest: () => void }) {
  const [content, setContent] = useState(artifact.content)
  const [format, setFormat] = useState<ContentFormat>(artifact.content_format)
  const [language, setLanguage] = useState(artifact.language ?? '')
  const [summary, setSummary] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const dirty = content !== artifact.content || format !== artifact.content_format || (format === 'code' ? language : '') !== (artifact.language ?? '')
  useEffect(() => { onDirtyChange(dirty); return () => onDirtyChange(false) }, [dirty, onDirtyChange])
  const save = async () => {
    if (saving || !dirty) return
    setSaving(true); setError(null); setConflict(false)
    try {
      const version = await saveArtifactVersion(artifact.id, { content, content_format: format, language: format === 'code' ? language || null : null, change_summary: summary || null, expected_version_number: artifact.current_version_number })
      onSaved(version)
    } catch (reason) {
      if (reason instanceof ArtifactApiError && reason.status === 409) { setConflict(true); setError('A newer version was saved elsewhere. Your draft is preserved; reload latest before editing again.') }
      else setError(reason instanceof Error ? reason.message : 'Unable to save this version.')
    } finally { setSaving(false) }
  }
  return <section className="artifact-editor" aria-label="Edit artifact">
    <div className="artifact-editor__meta"><label>Format<select value={format} onChange={(event) => setFormat(event.target.value as ContentFormat)}><option value="plain_text">Plain text</option><option value="markdown">Markdown</option><option value="json">JSON</option><option value="code">Code</option></select></label>{format === 'code' && <label>Language<input maxLength={50} value={language} onChange={(event) => setLanguage(event.target.value)}/></label>}<label>Change summary<input maxLength={500} placeholder="Optional summary" value={summary} onChange={(event) => setSummary(event.target.value)}/></label></div>
    <label className="artifact-editor__content">Content<textarea maxLength={1_000_000} value={content} onChange={(event) => setContent(event.target.value)} spellCheck={false}/><span>{content.length.toLocaleString()} / 1,000,000 characters {dirty && '· Unsaved changes'}</span></label>
    {error && <div className="workspace-state workspace-state--error" role="alert">{error}{conflict && <button onClick={onReloadLatest}>Reload latest version</button>}</div>}
    <footer><button onClick={onCancel}>Cancel editing</button><button className="tasks-primary-button" disabled={saving || !dirty || !content.trim()} onClick={() => void save()}>{saving ? 'Saving…' : 'Save Version'}</button></footer>
  </section>
}
