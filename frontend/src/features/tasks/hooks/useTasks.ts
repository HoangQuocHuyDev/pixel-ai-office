import { useCallback, useEffect, useState } from 'react'
import { fetchAgents } from '../../agents/api/agentClient'
import type { AgentId, AgentMetadata } from '../../agents/types'
import { createTask, deleteTask, fetchTasks, updateTask, updateTaskStatus } from '../api/taskClient'
import type { OfficeTask, TaskInput, TaskStatus } from '../types'

export function useTasks() {
  const [tasks, setTasks] = useState<OfficeTask[]>([])
  const [agents, setAgents] = useState<AgentMetadata[]>([])
  const [statusFilter, setStatusFilter] = useState<TaskStatus | ''>('')
  const [agentFilter, setAgentFilter] = useState<AgentId | ''>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError(null)
    try { setTasks(await fetchTasks({ status: statusFilter || undefined, agentId: agentFilter || undefined }, signal)) }
    catch (reason) { if (!signal?.aborted) setError(reason instanceof Error ? reason.message : 'Unable to load tasks.') }
    finally { if (!signal?.aborted) setLoading(false) }
  }, [agentFilter, statusFilter])

  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort() }, [load])
  useEffect(() => { void fetchAgents().then(setAgents).catch(() => setError('Unable to load agents.')) }, [])

  const save = async (payload: TaskInput, id?: number) => { await (id ? updateTask(id, payload) : createTask(payload)); await load() }
  const remove = async (id: number) => { await deleteTask(id); await load() }
  const changeStatus = async (id: number, status: TaskStatus) => { await updateTaskStatus(id, status); await load() }
  return { tasks, agents, loading, error, statusFilter, agentFilter, setStatusFilter, setAgentFilter, load, save, remove, changeStatus }
}
