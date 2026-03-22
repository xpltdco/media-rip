/**
 * TypeScript types matching the backend Pydantic models.
 *
 * These mirror:
 *   backend/app/models/job.py    → Job, JobStatus, ProgressEvent, FormatInfo
 *   backend/app/models/session.py → Session
 *   backend/app/routers/system.py → PublicConfig
 *   backend/app/routers/health.py → HealthStatus
 */

export type JobStatus =
  | 'queued'
  | 'extracting'
  | 'downloading'
  | 'completed'
  | 'failed'
  | 'expired'

export interface Job {
  id: string
  session_id: string
  url: string
  status: JobStatus
  format_id: string | null
  quality: string | null
  output_template: string | null
  filename: string | null
  filesize: number | null
  progress_percent: number
  speed: string | null
  eta: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface JobCreate {
  url: string
  format_id?: string | null
  quality?: string | null
  output_template?: string | null
  media_type?: string | null       // "video" | "audio"
  output_format?: string | null    // e.g. "mp3", "wav", "mp4", "webm"
}

export interface ProgressEvent {
  job_id: string
  status: string
  percent: number
  speed: string | null
  eta: string | null
  downloaded_bytes: number | null
  total_bytes: number | null
  filename: string | null
  filesize?: number | null
  error_message?: string | null
}

export interface FormatInfo {
  format_id: string
  ext: string
  resolution: string | null
  codec: string | null
  filesize: number | null
  format_note: string | null
  vcodec: string | null
  acodec: string | null
}

export interface PublicConfig {
  session_mode: string
  default_theme: string
  welcome_message: string
  purge_enabled: boolean
  max_concurrent_downloads: number
  default_video_format: string
  default_audio_format: string
  privacy_mode: boolean
  privacy_retention_minutes: number
  admin_enabled: boolean
  admin_setup_complete: boolean
}

export interface HealthStatus {
  status: string
  version: string
  yt_dlp_version: string
  uptime: number
  queue_depth: number
}

export interface UrlInfoEntry {
  title: string
  url: string
  duration: number | null
}

export interface UrlInfo {
  type: 'single' | 'playlist' | 'unknown'
  title: string | null
  count?: number
  entries: UrlInfoEntry[]
  duration?: number | null
  is_audio_only: boolean
  unavailable_count?: number
  default_ext?: string
}

/**
 * SSE event types received from GET /api/events.
 */
export interface SSEInitEvent {
  jobs: Job[]
}

export interface SSEJobUpdateEvent extends ProgressEvent {}

export interface SSEJobRemovedEvent {
  job_id: string
}
