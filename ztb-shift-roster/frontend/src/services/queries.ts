import { useQuery } from '@tanstack/react-query'

import { api } from '@/services/api'
import type {
  Analyst,
  Availability,
  CodeMapping,
  Dashboard,
  Holiday,
  Job,
  Leave,
  Policy,
  Project,
  RosterDetail,
  RosterSummary,
  Skill,
  ValidationReport,
} from '@/types/api'

export const keys = {
  projects: ['projects'] as const,
  analysts: ['analysts'] as const,
  skills: ['skills'] as const,
  policies: ['policies'] as const,
  holidays: ['holidays'] as const,
  availability: ['availability'] as const,
  mappings: ['mappings'] as const,
  leaves: (q: string) => ['leaves', q] as const,
  rosters: (q: string) => ['rosters', q] as const,
  roster: (id: number) => ['roster', id] as const,
  validation: (id: number) => ['validation', id] as const,
  dashboard: (y: number, m: number) => ['dashboard', y, m] as const,
  job: (id: string) => ['job', id] as const,
  jobs: ['jobs'] as const,
}

export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: () => api.get<Project[]>('/projects') })
export const useAnalysts = () => useQuery({ queryKey: keys.analysts, queryFn: () => api.get<Analyst[]>('/analysts') })
export const useSkills = () => useQuery({ queryKey: keys.skills, queryFn: () => api.get<Skill[]>('/skills') })
export const usePolicies = () => useQuery({ queryKey: keys.policies, queryFn: () => api.get<Policy[]>('/policies') })
export const useHolidays = () => useQuery({ queryKey: keys.holidays, queryFn: () => api.get<Holiday[]>('/holidays') })
export const useAvailability = () =>
  useQuery({ queryKey: keys.availability, queryFn: () => api.get<Availability[]>('/availability') })
export const useMappings = () =>
  useQuery({ queryKey: keys.mappings, queryFn: () => api.get<CodeMapping[]>('/shift-code-mappings') })

export function useLeaves(params: Record<string, string | number | undefined> = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== '') as [string, string][],
  ).toString()
  return useQuery({ queryKey: keys.leaves(q), queryFn: () => api.get<Leave[]>(`/leaves${q ? `?${q}` : ''}`) })
}

export function useRosters(params: Record<string, string | number | undefined> = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== '') as [string, string][],
  ).toString()
  return useQuery({ queryKey: keys.rosters(q), queryFn: () => api.get<RosterSummary[]>(`/rosters${q ? `?${q}` : ''}`) })
}

export const useRoster = (id: number) =>
  useQuery({ queryKey: keys.roster(id), queryFn: () => api.get<RosterDetail>(`/rosters/${id}`), enabled: id > 0 })

export const useValidation = (id: number) =>
  useQuery({
    queryKey: keys.validation(id),
    queryFn: () => api.get<ValidationReport>(`/rosters/${id}/validation`),
    enabled: id > 0,
  })

export const useDashboard = (y: number, m: number) =>
  useQuery({ queryKey: keys.dashboard(y, m), queryFn: () => api.get<Dashboard>(`/dashboard?year=${y}&month=${m}`) })

export function useJob(id: string | null) {
  return useQuery({
    queryKey: keys.job(id ?? ''),
    queryFn: () => api.get<Job>(`/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const state = query.state.data?.state
      return state === 'queued' || state === 'running' || !state ? 1000 : false
    },
  })
}

export const useJobs = () =>
  useQuery({ queryKey: keys.jobs, queryFn: () => api.get<Job[]>('/jobs?limit=20'), refetchInterval: 5000 })
