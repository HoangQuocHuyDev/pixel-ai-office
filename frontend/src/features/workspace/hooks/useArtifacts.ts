import { useEffect, useState } from 'react'
import { fetchArtifacts, fetchArtifactSummary } from '../api/artifactClient'
import type { ArtifactFilters, ArtifactList, ArtifactSummary } from '../types'

const emptyFilters: ArtifactFilters = { search: '', artifactType: '', agentId: '', offset: 0 }

export function useArtifacts() {
  const [filters, setFilters] = useState(emptyFilters)
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [data, setData] = useState<ArtifactList | null>(null)
  const [summary, setSummary] = useState<ArtifactSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedSearch(filters.search), 350); return () => window.clearTimeout(timer) }, [filters.search])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    void Promise.all([
      fetchArtifacts({ ...filters, search: debouncedSearch }, controller.signal),
      fetchArtifactSummary(controller.signal),
    ]).then(([nextData, nextSummary]) => { setData(nextData); setSummary(nextSummary) })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Workspace is unavailable.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [debouncedSearch, filters.artifactType, filters.agentId, filters.offset, refreshKey])

  const updateFilters = (patch: Partial<ArtifactFilters>) => setFilters((current) => ({ ...current, ...patch, offset: patch.offset ?? 0 }))
  return { filters, updateFilters, data, summary, loading, error, refresh: () => setRefreshKey((value) => value + 1) }
}
