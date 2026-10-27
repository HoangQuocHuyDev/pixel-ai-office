import type { ArtifactCompare } from '../types'

export default function ArtifactDiffViewer({ comparison }: { comparison: ArtifactCompare }) {
  return <section className="artifact-diff" aria-label="Version comparison"><header><strong>Version {comparison.from_version} → {comparison.to_version}</strong><span>+{comparison.added_lines} / −{comparison.removed_lines}</span></header><pre>{comparison.unified_diff || 'No textual differences.'}</pre></section>
}
