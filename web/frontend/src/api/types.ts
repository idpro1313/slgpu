export type ServiceStatus = "unknown" | "healthy" | "degraded" | "down";
export type DownloadStatus = "unknown" | "pending" | "downloading" | "ready" | "error" | "partial";
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
  /** Мультислотный рантайм: карточки на Dashboard / привязка GPU live. */
  slots: RuntimeSlotView[];
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

export interface DashboardHostNvidiaGpu {
  index: number;
  name: string;
  memory_total_mib: number | string;
}

export interface DashboardHostNvidia {
  smi_available: boolean;
  note?: string;
  driver_version?: string | null;
  cuda_version?: string | null;
  gpus?: DashboardHostNvidiaGpu[];
}

export interface DashboardHostInfo {
  hostname: string | null;
  os_pretty: string;
  kernel: string;
  arch: string;
  cpu_model: string | null;
  cpu_logical_cores: number;
  memory_total_bytes: number | null;
  memory_available_bytes: number | null;
  disk_slgpu_path: string;
  disk_slgpu_total_bytes: number;
  disk_slgpu_used_bytes: number;
  disk_slgpu_free_bytes: number;
  nvidia: DashboardHostNvidia;
}

export interface DashboardData {
  metrics: DashboardMetrics;
  runtime: DashboardRuntime;
  services: DashboardServiceCard[];
  host: DashboardHostInfo;
}

export interface ModelPullProgress {
  job_id: number;
  status: JobStatus;
  progress: number | null;
  message: string | null;
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
  pull_progress?: ModelPullProgress | null;
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

export interface RuntimeSlotView {
  slot_key: string;
  engine: string;
  preset_name: string | null;
  hf_id: string | null;
  api_port: number | null;
  tp: number | null;
  gpu_indices: string | null;
  container_status: string | null;
  container_name: string | null;
  served_models: string[];
  metrics_available: boolean;
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
  slots: RuntimeSlotView[];
}

export interface GpuCardState {
  index: number;
  uuid?: string | null;
  name?: string;
  memory_used_mib: number | string;
  memory_total_mib: number | string;
  utilization_gpu: number | string;
  utilization_memory: number | string;
}

export interface GpuStateResponse {
  smi_available: boolean;
  error: string | null;
  driver_version: string | null;
  cuda_version: string | null;
  gpus: GpuCardState[];
  /** Процессы compute на GPU; поле ``slot_key`` сопоставляется с контейнерами слотов (docker top). */
  processes: GpuProcessState[];
}

export interface GpuProcessState {
  pid: number;
  process_name?: string;
  used_memory_mib?: number | string;
  gpu_uuid?: string | null;
  slot_key?: string | null;
}

export interface GpuBusy {
  index: number;
  slot_key: string;
  preset_name: string | null;
  engine: string;
}

export interface GpuAvailability {
  all_indices: number[];
  available: number[];
  busy: GpuBusy[];
  suggested: number[] | null;
  note: string | null;
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
  /** Аргументы native/CLI job (слот, пресет, порты и т.д.). */
  args: Record<string, unknown>;
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

export type JobAcceptedStatus = JobStatus | "forced";

export interface JobAccepted {
  job_id: number;
  correlation_id: string;
  kind: string;
  status: JobAcceptedStatus;
  message: string | null;
  /** true: POST /runtime/slots/.../down?force=1 — без новой job в очереди */
  forced?: boolean;
  cancelled_job_ids?: number[];
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

/** POST /api/v1/presets/{id}/clone */
export interface PresetCloneRequest {
  name: string;
  description?: string | null;
  hf_id?: string | null;
  tp?: number | null;
  gpu_mask?: string | null;
  served_model_name?: string | null;
  parameters?: Record<string, unknown> | null;
}

export interface LiteLLMHealth {
  liveliness: boolean;
  readiness: boolean;
  ui: boolean;
}

/** GET /litellm/info */
export interface LiteLLMInfo {
  ui_url: string;
  api_url: string;
  port: number;
  note: string;
}

/** GET /bench/runs */
export interface BenchRun {
  engine: string;
  timestamp: string;
  kind: string;
  path: string;
}

/** Состояние install из /app-config/install flow */
export interface AppConfigStatus {
  installed: boolean;
  meta: Record<string, unknown>;
}

/** Ответ GET /app-config/stack */
export interface AppConfigStack {
  stack: Record<string, string>;
  secrets: Record<string, string>;
  meta: Record<string, unknown>;
  /** Метаданные ключей из реестра (группа, обязательность по сценариям). */
  registry?: Array<{
    key: string;
    group: string;
    description: string;
    is_secret: boolean;
    allow_empty: boolean;
    required_for: string[];
  }>;
}

export interface PublicAccessSettings {
  server_host: string | null;
  effective_server_host: string;
  grafana_url: string;
  prometheus_url: string;
  langfuse_url: string;
  litellm_ui_url: string;
  litellm_api_url: string;
  /** Ключ в БД есть (значение никогда не отдаётся). */
  litellm_api_key_set: boolean;
}

export interface Healthz {
  status: string;
  version: string;
  slgpu_root: string;
  database_url_masked: string;
}

/** GET /docker/containers */
export interface DockerContainerRow {
  id: string;
  short_id: string;
  name: string;
  image: string;
  status: string;
  health: string | null;
  compose_project: string | null;
  compose_service: string | null;
}

export interface DockerContainersList {
  docker_available: boolean;
  scope: string;
  containers: DockerContainerRow[];
  last_checked_at: string;
}

/** GET /docker/containers/.../logs */
export interface DockerContainerLogs {
  container_id: string;
  container_name: string | null;
  tail: number;
  logs: string;
  docker_available: boolean;
  last_checked_at: string;
}

/** GET /docker/engine-events */
export interface DockerEngineEvents {
  docker_available: boolean;
  since_sec: number;
  limit: number;
  events_text: string;
  last_checked_at: string;
}

/** GET /docker/daemon-log — journald dockerd (best-effort) */
export interface DockerDaemonLog {
  lines: number;
  text: string;
  journal_note: string | null;
  last_checked_at: string;
}
