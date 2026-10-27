import { API_BASE_URL } from '../../../config/api'
import type { ArtifactCompare, ArtifactDetail, ArtifactFilters, ArtifactList, ArtifactSummary, ArtifactVersionDetail, ArtifactVersionList, SaveVersionInput } from '../types'

export class ArtifactApiError extends Error {
  readonly status: number
  readonly code?: string
  constructor(message: string, status: number, code?: string) { super(message); this.status = status; this.code = code }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal })
  if (!response.ok) {
    let body: { error?: { code?: string; message?: string } } = {}
    try { body = await response.json() as typeof body } catch { /* use fallback */ }
    throw new ArtifactApiError(body.error?.message ?? `Unable to load workspace (${response.status}).`, response.status, body.error?.code)
  }
  return (await response.json()) as T
}

export function fetchArtifacts(filters: ArtifactFilters, signal?: AbortSignal): Promise<ArtifactList> {
  const params = new URLSearchParams({ limit: '12', offset: String(filters.offset) })
  if (filters.search.trim()) params.set('search', filters.search.trim())
  if (filters.artifactType) params.set('artifact_type', filters.artifactType)
  if (filters.agentId) params.set('agent_id', filters.agentId)
  return getJson(`/api/v1/artifacts?${params}`, signal)
}
export const fetchArtifactSummary = (signal?: AbortSignal) => getJson<ArtifactSummary>('/api/v1/artifacts/summary', signal)
export const fetchArtifact = (artifactId: number, signal?: AbortSignal) => getJson<ArtifactDetail>(`/api/v1/artifacts/${artifactId}`, signal)
export const artifactDownloadUrl = (artifactId: number) => `${API_BASE_URL}/api/v1/artifacts/${artifactId}/download`
export const fetchArtifactVersions = (artifactId: number, signal?: AbortSignal) => getJson<ArtifactVersionList>(`/api/v1/artifacts/${artifactId}/versions?limit=100&offset=0`, signal)
export const fetchArtifactVersion = (artifactId: number, version: number, signal?: AbortSignal) => getJson<ArtifactVersionDetail>(`/api/v1/artifacts/${artifactId}/versions/${version}`, signal)
export const compareArtifactVersions = (artifactId: number, fromVersion: number, toVersion: number, signal?: AbortSignal) => getJson<ArtifactCompare>(`/api/v1/artifacts/${artifactId}/compare?from_version=${fromVersion}&to_version=${toVersion}`, signal)
export const artifactVersionDownloadUrl = (artifactId: number, version: number) => `${API_BASE_URL}/api/v1/artifacts/${artifactId}/versions/${version}/download`

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) {
    let payload: { error?: { code?: string; message?: string } } = {}
    try { payload = await response.json() as typeof payload } catch { /* use fallback */ }
    throw new ArtifactApiError(payload.error?.message ?? `Unable to save artifact (${response.status}).`, response.status, payload.error?.code)
  }
  return (await response.json()) as T
}
export const saveArtifactVersion = (artifactId: number, input: SaveVersionInput) => postJson<ArtifactVersionDetail>(`/api/v1/artifacts/${artifactId}/versions`, input)
export const restoreArtifactVersion = (artifactId: number, versionNumber: number, expectedVersionNumber: number) => postJson<ArtifactVersionDetail>(`/api/v1/artifacts/${artifactId}/restore`, { version_number: versionNumber, expected_version_number: expectedVersionNumber })
