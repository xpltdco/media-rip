import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDownloadsStore } from '@/stores/downloads'
import type { Job, ProgressEvent } from '@/api/types'

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: overrides.id ?? 'job-1',
    session_id: 'sess-1',
    url: 'https://example.com/video',
    status: 'queued',
    format_id: null,
    quality: null,
    output_template: null,
    filename: null,
    filesize: null,
    progress_percent: 0,
    speed: null,
    eta: null,
    error_message: null,
    created_at: '2026-03-18T00:00:00Z',
    started_at: null,
    completed_at: null,
    ...overrides,
  }
}

describe('downloads store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('handleInit', () => {
    it('populates jobs from init event', () => {
      const store = useDownloadsStore()
      const jobs = [makeJob({ id: 'a' }), makeJob({ id: 'b' })]
      store.handleInit(jobs)

      expect(store.jobs.size).toBe(2)
      expect(store.jobs.get('a')).toBeDefined()
      expect(store.jobs.get('b')).toBeDefined()
    })

    it('merges with existing jobs on re-init (avoids race with local submits)', () => {
      const store = useDownloadsStore()
      store.handleInit([makeJob({ id: 'old' })])
      expect(store.jobs.has('old')).toBe(true)

      store.handleInit([makeJob({ id: 'new' })])
      // Merge keeps both old (locally submitted) and new (SSE replay)
      expect(store.jobs.has('old')).toBe(true)
      expect(store.jobs.has('new')).toBe(true)
    })
  })

  describe('handleJobUpdate', () => {
    it('updates progress on existing job', () => {
      const store = useDownloadsStore()
      store.handleInit([makeJob({ id: 'j1' })])

      const event: ProgressEvent = {
        job_id: 'j1',
        status: 'downloading',
        percent: 45.5,
        speed: '2.5 MiB/s',
        eta: '1m30s',
        downloaded_bytes: null,
        total_bytes: null,
        filename: 'video.mp4',
      }
      store.handleJobUpdate(event)

      const job = store.jobs.get('j1')!
      expect(job.status).toBe('downloading')
      expect(job.progress_percent).toBe(45.5)
      expect(job.speed).toBe('2.5 MiB/s')
      expect(job.eta).toBe('1m30s')
      expect(job.filename).toBe('video.mp4')
    })

    it('normalizes yt-dlp "finished" status to "completed"', () => {
      const store = useDownloadsStore()
      store.handleInit([makeJob({ id: 'j1' })])

      store.handleJobUpdate({
        job_id: 'j1',
        status: 'finished',
        percent: 100,
        speed: null,
        eta: null,
        downloaded_bytes: null,
        total_bytes: null,
        filename: 'video.mp4',
      })

      expect(store.jobs.get('j1')!.status).toBe('completed')
    })

    it('creates minimal entry for unknown job (cross-tab scenario)', () => {
      const store = useDownloadsStore()
      const event: ProgressEvent = {
        job_id: 'nonexistent',
        status: 'downloading',
        percent: 50,
        speed: null,
        eta: null,
        downloaded_bytes: null,
        total_bytes: null,
        filename: null,
      }
      // Should not throw — creates a minimal placeholder entry
      store.handleJobUpdate(event)
      expect(store.jobs.size).toBe(1)
      expect(store.jobs.get('nonexistent')!.status).toBe('downloading')
    })
  })

  describe('handleJobRemoved', () => {
    it('removes job from map', () => {
      const store = useDownloadsStore()
      store.handleInit([makeJob({ id: 'j1' }), makeJob({ id: 'j2' })])

      store.handleJobRemoved('j1')
      expect(store.jobs.has('j1')).toBe(false)
      expect(store.jobs.has('j2')).toBe(true)
    })

    it('no-ops for unknown job', () => {
      const store = useDownloadsStore()
      store.handleInit([makeJob({ id: 'j1' })])
      store.handleJobRemoved('nonexistent')
      expect(store.jobs.size).toBe(1)
    })
  })

  describe('computed getters', () => {
    it('jobList is sorted newest-first', () => {
      const store = useDownloadsStore()
      store.handleInit([
        makeJob({ id: 'old', created_at: '2026-03-17T00:00:00Z' }),
        makeJob({ id: 'new', created_at: '2026-03-18T00:00:00Z' }),
      ])

      expect(store.jobList[0].id).toBe('new')
      expect(store.jobList[1].id).toBe('old')
    })

    it('activeJobs filters non-terminal', () => {
      const store = useDownloadsStore()
      store.handleInit([
        makeJob({ id: 'q', status: 'queued' }),
        makeJob({ id: 'd', status: 'downloading' }),
        makeJob({ id: 'c', status: 'completed' }),
        makeJob({ id: 'f', status: 'failed' }),
      ])

      expect(store.activeJobs.map((j) => j.id).sort()).toEqual(['d', 'q'])
    })

    it('completedJobs filters completed only', () => {
      const store = useDownloadsStore()
      store.handleInit([
        makeJob({ id: 'c', status: 'completed' }),
        makeJob({ id: 'q', status: 'queued' }),
      ])

      expect(store.completedJobs).toHaveLength(1)
      expect(store.completedJobs[0].id).toBe('c')
    })

    it('failedJobs filters failed only', () => {
      const store = useDownloadsStore()
      store.handleInit([
        makeJob({ id: 'f', status: 'failed' }),
        makeJob({ id: 'q', status: 'queued' }),
      ])

      expect(store.failedJobs).toHaveLength(1)
      expect(store.failedJobs[0].id).toBe('f')
    })
  })

  describe('isTerminal', () => {
    it('returns true for terminal statuses', () => {
      const store = useDownloadsStore()
      expect(store.isTerminal('completed')).toBe(true)
      expect(store.isTerminal('failed')).toBe(true)
      expect(store.isTerminal('expired')).toBe(true)
    })

    it('returns false for active statuses', () => {
      const store = useDownloadsStore()
      expect(store.isTerminal('queued')).toBe(false)
      expect(store.isTerminal('downloading')).toBe(false)
      expect(store.isTerminal('extracting')).toBe(false)
    })
  })
})
