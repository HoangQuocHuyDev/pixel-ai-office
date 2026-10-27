import { useCallback, useEffect, useState } from 'react'
import { fetchArtifactVersions } from '../api/artifactClient'
import type { ArtifactVersionList } from '../types'

export function useArtifactVersions(artifactId: number) {
  const [data, setData] = useState<ArtifactVersionList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    void fetchArtifactVersions(artifactId, controller.signal).then(setData)
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load versions.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [artifactId, refreshKey])
  return { data, loading, error, refresh }
}
