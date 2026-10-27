import { useEffect, useState } from 'react'
import { artifactVersionDownloadUrl, compareArtifactVersions, fetchArtifactVersion, restoreArtifactVersion } from '../api/artifactClient'
import { useArtifactVersions } from '../hooks/useArtifactVersions'
import type { ArtifactCompare, ArtifactDetail, ArtifactVersionDetail } from '../types'
import ArtifactDiffViewer from './ArtifactDiffViewer'

export default function ArtifactVersionHistory({ artifact, onUpdated }: { artifact: ArtifactDetail; onUpdated: () => void }) {
  const versions = useArtifactVersions(artifact.id)
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null)
  const [selected, setSelected] = useState<ArtifactVersionDetail | null>(null)
  const [comparison, setComparison] = useState<ArtifactCompare | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (selectedNumber === null) { setSelected(null); setComparison(null); return }
    const controller = new AbortController(); setError(null); setComparison(null)
    void fetchArtifactVersion(artifact.id, selectedNumber, controller.signal).then(setSelected).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load version.') })
    return () => controller.abort()
  }, [artifact.id, selectedNumber])
  const compare = async () => {
    if (selectedNumber === null) return; setBusy(true); setError(null)
    try { setComparison(await compareArtifactVersions(artifact.id, selectedNumber, artifact.current_version_number)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to compare versions.') }
    finally { setBusy(false) }
  }
  const restore = async () => {
    if (selectedNumber === null || !confirm(`Restore version ${selectedNumber} as a new version?`)) return
    setBusy(true); setError(null)
    try { await restoreArtifactVersion(artifact.id, selectedNumber, artifact.current_version_number); versions.refresh(); onUpdated() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to restore version.') }
    finally { setBusy(false) }
  }
  return <section className="artifact-history" aria-label="Version history">
    {versions.loading ? <p className="workspace-state">Loading version history…</p> : versions.error ? <p className="workspace-state workspace-state--error">{versions.error}</p> : !versions.data?.items.length ? <p className="workspace-state">No versions are available.</p> : <div className="artifact-history__layout"><ol>{versions.data.items.map((version) => <li key={version.id}><button className={selectedNumber === version.version_number ? 'selected' : ''} onClick={() => setSelectedNumber(version.version_number)}><span><strong>Version {version.version_number}</strong>{version.version_number === 1 && <em>Original</em>}{version.version_number === versions.data?.current_version_number && <em>Current</em>}</span><span>{version.source}{version.restored_from_version_number ? ` from v${version.restored_from_version_number}` : ''}</span><small>{version.change_summary ?? 'No change summary'}</small><time>{new Date(version.created_at).toLocaleString()}</time></button></li>)}</ol><div className="artifact-history__detail">{selected ? <><div className="artifact-history__actions"><button disabled={busy || selected.version_number === artifact.current_version_number} onClick={() => void compare()}>Compare with current</button><a href={artifactVersionDownloadUrl(artifact.id, selected.version_number)}>Download version</a><button disabled={busy || selected.version_number === artifact.current_version_number} onClick={() => void restore()}>Restore as new version</button></div><pre>{selected.content}</pre></> : <p className="workspace-state">Select a version to inspect it.</p>}{error && <p className="workspace-state workspace-state--error" role="alert">{error}</p>}{comparison && <ArtifactDiffViewer comparison={comparison}/>}</div></div>}
  </section>
}
