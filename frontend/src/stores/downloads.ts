/**
 * Downloads Pinia store — manages job state and CRUD actions.
 *
 * Jobs are stored in a reactive Map keyed by job ID.
 * SSE events update the map directly via internal mutation methods.
 * Components read from the `jobs` ref and computed getters.
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { Job, JobCreate, JobStatus, ProgressEvent } from '@/api/types'

export const useDownloadsStore = defineStore('downloads', () => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const jobs = ref<Map<string, Job>>(new Map())
  const isSubmitting = ref(false)
  const submitError = ref<string | null>(null)

  // ---------------------------------------------------------------------------
  // Getters
  // ---------------------------------------------------------------------------

  const jobList = computed<Job[]>(() =>
    Array.from(jobs.value.values()).sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    ),
  )

  const activeJobs = computed<Job[]>(() =>
    jobList.value.filter((j) => !isTerminal(j.status)),
  )

  const completedJobs = computed<Job[]>(() =>
    jobList.value.filter((j) => j.status === 'completed'),
  )

  const failedJobs = computed<Job[]>(() =>
    jobList.value.filter((j) => j.status === 'failed'),
  )

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  async function fetchJobs(): Promise<void> {
    const list = await api.getDownloads()
    jobs.value = new Map(list.map((j) => [j.id, j]))
  }

  async function submitDownload(payload: JobCreate): Promise<Job> {
    isSubmitting.value = true
    submitError.value = null
    try {
      const job = await api.createDownload(payload)
      jobs.value.set(job.id, job)
      return job
    } catch (err: any) {
      submitError.value = err.message || 'Failed to submit download'
      throw err
    } finally {
      isSubmitting.value = false
    }
  }

  async function cancelDownload(id: string): Promise<void> {
    await api.deleteDownload(id)
    // job_removed SSE event will remove it from the map
  }

  // ---------------------------------------------------------------------------
  // SSE event handlers (called by useSSE composable)
  // ---------------------------------------------------------------------------

  function handleInit(initialJobs: Job[]): void {
    // Merge with existing jobs rather than replacing — avoids race condition
    // where a locally-submitted job is cleared by an SSE init replay
    const merged = new Map(jobs.value)
    for (const job of initialJobs) {
      merged.set(job.id, job)
    }
    jobs.value = merged
  }

  function handleJobUpdate(event: ProgressEvent): void {
    const existing = jobs.value.get(event.job_id)
    // Normalize yt-dlp status to our JobStatus enum
    const normalizedStatus = event.status === 'finished' ? 'completed' : event.status

    if (existing) {
      existing.status = normalizedStatus as JobStatus
      existing.progress_percent = event.percent
      if (event.speed !== null) existing.speed = event.speed
      if (event.eta !== null) existing.eta = event.eta
      if (event.filename !== null) existing.filename = event.filename
      if (event.error_message) existing.error_message = event.error_message
      // Trigger reactivity by re-setting the map entry
      jobs.value.set(event.job_id, { ...existing })
    } else {
      // Job wasn't in our map yet (submitted from another tab, or arrived
      // before the POST response) — create a minimal entry
      jobs.value.set(event.job_id, {
        id: event.job_id,
        session_id: '',
        url: '',
        status: normalizedStatus as JobStatus,
        format_id: null,
        quality: null,
        output_template: null,
        filename: event.filename ?? null,
        filesize: null,
        progress_percent: event.percent,
        speed: event.speed ?? null,
        eta: event.eta ?? null,
        error_message: null,
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
      })
    }
  }

  function handleJobRemoved(jobId: string): void {
    jobs.value.delete(jobId)
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function isTerminal(status: JobStatus | string): boolean {
    return status === 'completed' || status === 'failed' || status === 'expired'
  }

  return {
    // State
    jobs,
    isSubmitting,
    submitError,
    // Getters
    jobList,
    activeJobs,
    completedJobs,
    failedJobs,
    // Actions
    fetchJobs,
    submitDownload,
    cancelDownload,
    // SSE handlers
    handleInit,
    handleJobUpdate,
    handleJobRemoved,
    // Helpers
    isTerminal,
  }
})
