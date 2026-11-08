/** Read-side contract for /api/v2. Optional fields represent genuinely unknown observations. */
export type Timestamp = string | number;
export interface Versioned { id: string; revision: number; observed_at?: Timestamp | null }
export interface Page<T> { items: T[]; next_cursor?: string | null; observed_at?: Timestamp | null; available?: boolean }
export type ActualState = 'idle' | 'watching' | 'starting' | 'recording' | 'reconnecting' | 'stopping' | 'blocked' | 'error';
export interface Channel extends Versioned {
  name: string; platform: string; desired_mode: 'auto' | 'paused'; actual_state: ActualState;
  reason_code?: string | null; broadcast_id?: string | null; title?: string | null;
  started_at?: Timestamp | null; write_rate_bps?: number | null; last_write_at?: Timestamp | null;
  controls_available?: boolean;
}
export interface Broadcast extends Versioned {
  title: string; channel_id: string; channel_name?: string; platform: string;
  started_at?: Timestamp | null; ended_at?: Timestamp | null; status: string;
  segment_count?: number; total_size?: number; duration_seconds?: number | null;
  validation_status?: string | null; identity_basis?: string | null;
}
export interface Segment extends Versioned {
  session_id?: string; sequence: number; captured_from?: Timestamp | null; captured_to?: Timestamp | null;
  started_at?: Timestamp | null; ended_at?: Timestamp | null; gap_before?: boolean | number | null;
  duration_seconds?: number | null; estimated?: boolean;
}
export interface Session extends Versioned {
  started_at?: Timestamp | null; ended_at?: Timestamp | null; engine?: string; outcome?: string | null; stop_reason?: string | null;
}
export interface Artifact extends Versioned {
  kind: string; relative_path: string; size?: number | null; validation?: string | Record<string, unknown> | null;
  exists?: boolean | null; exists_status?: string; segment_id?: string | null; storage_id?: string;
  controls_available?: boolean;
}
export type JobState = 'queued' | 'running' | 'retry_wait' | 'blocked' | 'failed' | 'cancel_requested' | 'cancelled' | 'succeeded' | 'interrupted';
export interface Job extends Versioned {
  kind: string; target_id: string; state: JobState; attempts?: number; max_attempts?: number;
  error_code?: string | null; error_message?: string | null; progress?: number | string | Record<string, unknown> | null;
  created_at?: Timestamp | null; next_run_at?: Timestamp | null; cancel_requested?: boolean;
}
export interface JobAttempt extends Versioned {
  attempt_no: number; started_at?: Timestamp | null; ended_at?: Timestamp | null; outcome?: string | null;
  error_code?: string | null; error_message?: string | null; error_detail?: string | null; stage?: string | null; exit_code?: number | null;
}
export interface JobDetail extends Job { attempt_history?: JobAttempt[]; log?: string | null }
export interface BroadcastDetail extends Broadcast { sessions?: Session[]; segments: Segment[]; artifacts: Artifact[]; jobs: Job[]; jobs_available?: boolean }
export interface Command {
  id?: string; command_id?: string; state?: string; status?: string; status_url?: string;
  error_code?: string | null; error_message?: string | null; message?: string; observed_at?: string;
}
export interface SystemStatus {
  observed_at?: Timestamp | null; enabled: boolean; version?: string;
  features?: { durable_jobs?: boolean; channel_controls?: boolean };
  channels: { recording: number; watching: number; attention: number; total: number };
  jobs: { queued: number; running: number; failed: number; blocked: number };
  worker?: { ready?: boolean; running?: boolean | number; [key: string]: unknown };
  storage?: { status: string; message?: string; free_bytes?: number; total_bytes?: number; checked_at?: Timestamp | null; last_ok_at?: Timestamp | null; [key: string]: unknown };
}
export interface Settings {
  enabled: boolean; version?: string;
  storage?: { database?: string; recordings?: string; originals_preserved?: boolean };
  features?: Record<string, boolean>; links?: Record<string, string>;
}
export interface ApiErrorBody { code: string; message: string; retryable?: boolean; request_id?: string; details?: unknown }
