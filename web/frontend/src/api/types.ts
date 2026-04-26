export type ServiceStatus = "unknown" | "healthy" | "degraded" | "down";
export type DownloadStatus = "unknown" | "pending" | "downloading" | "ready" | "error" | "partial";
export type RunStatus =
  | "requested"
  | "starting"
  | "running"
  | "degraded"
  | "stopped"
  | "failed";
export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface DashboardMetrics {
  models_total: number;
  models_ready: number;
  presets_total: number;
  active_jobs: number;
  services_healthy: number;
  services_total: number;
}

export interface DashboardRuntime {
  engine: string | null;
  api_port: number | null;
  container_status: string | null;
  preset_name: string | null;
  hf_id: string | null;
  tp: number | null;
  served_models: string[];
  metrics_available: boolean;
  last_checked_at: string | null;
}

export interface DashboardServiceCard {
  key: string;
  display_name: string;
  category: string;
  status: ServiceStatus;
  detail: string | null;
  url: string | null;
  container_status: string | null;
}

export interface DashboardData {
  metrics: DashboardMetrics;
  runtime: DashboardRuntime;
  services: DashboardServiceCard[];
}

export interface HFModel {
  id: number;
  hf_id: string;
  revision: string | null;
  slug: string;
  local_path: string | null;
  size_bytes: number | null;
  download_status: DownloadStatus;
  last_error: string | null;
  last_pulled_at: string | null;
  attempts: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ModelSyncResult {
  touched: number;
  total: number;
}

export interface Preset {
  id: number;
  name: string;
  description: string | null;
  model_id: number | null;
  hf_id: string;
  tp: number | null;
  gpu_mask: string | null;
  served_model_name: string | null;
  parameters: Record<string, unknown>;
  file_path: string | null;
  is_synced: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RuntimeSnapshot {
  engine: string | null;
  api_port: number | null;
  container_status: string | null;
  preset_name: string | null;
  hf_id: string | null;
  tp: number | null;
  served_models: string[];
  metrics_available: boolean;
  last_checked_at: string | null;
}

export interface RuntimeLogs {
  engine: string | null;
  container_name: string | null;
  container_status: string | null;
  tail: number;
  logs: string;
  last_checked_at: string | null;
}

export interface ServiceCard {
  key: string;
  display_name: string;
  category: string;
  status: ServiceStatus;
  container_id: string | null;
  url: string | null;
  detail: string | null;
  extra: Record<string, unknown>;
  last_seen_at: string | null;
}

export interface Job {
  id: number;
  correlation_id: string;
  kind: string;
  scope: string;
  resource: string | null;
  status: JobStatus;
  command: string[];
  actor: string | null;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  stdout_tail: string | null;
  stderr_tail: string | null;
  progress: number | null;
  message: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobAccepted {
  job_id: number;
  correlation_id: string;
  kind: string;
  status: JobStatus;
  message: string | null;
}

/** GET /activity: CLI-задача или запись о действии в UI (без дубля с job). */
export type ActivityEntry =
  | { type: "job"; created_at: string; job: Job }
  | {
      type: "ui";
      created_at: string;
      audit_id: number;
      action: string;
      target: string | null;
      actor: string | null;
      note: string | null;
      payload: Record<string, unknown>;
    };

export interface PresetSyncResult {
  imported: number;
  updated: number;
  skipped: number;
  errors: string[];
}

export interface LiteLLMHealth {
  liveliness: boolean;
  readiness: boolean;
  ui: boolean;
}

export interface PublicAccessSettings {
  server_host: string | null;
  effective_server_host: string;
  grafana_url: string;
  prometheus_url: string;
  langfuse_url: string;
  litellm_ui_url: string;
  litellm_api_url: string;
}

export interface Healthz {
  status: string;
  version: string;
  slgpu_root: string;
  database_url_masked: string;
}
