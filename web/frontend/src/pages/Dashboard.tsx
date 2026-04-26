import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { DashboardData, GpuProcessState, GpuStateResponse, RuntimeSlotView } from "@/api/types";
import { formatBytesIEC } from "@/components/formatters";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";
import { VramBar } from "@/components/VramBar";

function presetForGpuIndex(index: number, slots: RuntimeSlotView[] | undefined): string | null {
  if (!slots?.length) return null;
  for (const s of slots) {
    if (!s.gpu_indices?.trim()) continue;
    const ids = s.gpu_indices
      .split(",")
      .map((x) => parseInt(x.trim(), 10))
      .filter((n) => !Number.isNaN(n));
    if (ids.includes(index)) {
      return s.preset_name ?? s.slot_key;
    }
  }
  return null;
}

function numGpu(v: number | string): number {
  return typeof v === "number" ? v : parseInt(String(v), 10) || 0;
}

export function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: ({ signal }) => api.get<DashboardData>("/dashboard", { signal }),
    refetchInterval: 10_000,
  });

  const gpuLive = useQuery({
    queryKey: ["gpu-state"],
    queryFn: ({ signal }) => api.get<GpuStateResponse>("/gpu/state", { signal }),
    refetchInterval: 3_000,
  });

  return (
    <>
      <PageHeader
        title="Обзор стенда"
        subtitle="Сводка по моделям, серверу (CPU/RAM/диск/GPU), активным запускам, мониторингу и LiteLLM. Обновляется каждые 10 секунд."
      />

      {isError ? (
        <div className="empty-state">Не удалось получить данные дашборда.</div>
      ) : null}

      <div className="metric-grid">
        <MetricCard
          label="Всего моделей"
          value={data?.metrics.models_total ?? "—"}
          hint={`Готово к запуску: ${data?.metrics.models_ready ?? 0}`}
          accent
        />
        <MetricCard
          label="Пресеты"
          value={data?.metrics.presets_total ?? "—"}
          hint="из БД и data/presets (PRESETS_DIR)"
        />
        <MetricCard
          label="Активные задачи"
          value={data?.metrics.active_jobs ?? 0}
          hint="job runner, advisory locks"
        />
        <MetricCard
          label="Сервисы мониторинга"
          value={
            data
              ? `${data.metrics.services_healthy} / ${data.metrics.services_total}`
              : "—"
          }
          hint="прометей, графана, локи, лангфуз, литеЛЛМ"
        />
      </div>

      <Section
        title="Сервер"
        subtitle="ОС и железо в том виде, в каком их видит контейнер slgpu-web (/proc, диск по пути репозитория). Память может отражать лимит cgroup. NVIDIA/CUDA — если в контейнере доступен nvidia-smi (опционально подключите GPU к slgpu-web)."
      >
        {isError ? (
          <div className="empty-state">Блок недоступен.</div>
        ) : isLoading || !data?.host ? (
          <div className="empty-state">Загружаем…</div>
        ) : (
          <div className="cards-grid">
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">ОС и ядро</span>
              </div>
              <div className="status-card__detail">
                <div>{data.host.os_pretty}</div>
                <div className="mono" style={{ marginTop: 6, fontSize: 13 }}>
                  kernel {data.host.kernel} · {data.host.arch}
                </div>
                {data.host.hostname ? (
                  <div className="mono" style={{ marginTop: 4, fontSize: 13 }}>
                    host {data.host.hostname}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">CPU</span>
              </div>
              <div className="status-card__detail">
                <div>{data.host.cpu_model ?? "—"}</div>
                <div style={{ marginTop: 6 }}>
                  Логических ядер: <span className="mono">{data.host.cpu_logical_cores}</span>
                </div>
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">RAM</span>
              </div>
              <div className="status-card__detail">
                <div>
                  Всего:{" "}
                  <span className="mono">{formatBytesIEC(data.host.memory_total_bytes)}</span>
                </div>
                <div style={{ marginTop: 6 }}>
                  Доступно:{" "}
                  <span className="mono">{formatBytesIEC(data.host.memory_available_bytes)}</span>
                </div>
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">Диск (корень репо)</span>
              </div>
              <div className="status-card__detail mono" style={{ fontSize: 13, wordBreak: "break-all" }}>
                {data.host.disk_slgpu_path}
              </div>
              <div className="status-card__detail" style={{ marginTop: 8 }}>
                <div>
                  Всего / занято / свободно:{" "}
                  <span className="mono">
                    {formatBytesIEC(data.host.disk_slgpu_total_bytes)} /{" "}
                    {formatBytesIEC(data.host.disk_slgpu_used_bytes)} /{" "}
                    {formatBytesIEC(data.host.disk_slgpu_free_bytes)}
                  </span>
                </div>
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">NVIDIA / CUDA</span>
              </div>
              <div className="status-card__detail">
                {data.host.nvidia.smi_available ? (
                  <>
                    <div>
                      Драйвер:{" "}
                      <span className="mono">{data.host.nvidia.driver_version ?? "—"}</span>
                      {" · CUDA "}
                      <span className="mono">{data.host.nvidia.cuda_version ?? "—"}</span>
                    </div>
                    {data.host.nvidia.gpus && data.host.nvidia.gpus.length > 0 ? (
                      <ul style={{ margin: "10px 0 0 0", paddingLeft: 18 }}>
                        {data.host.nvidia.gpus.map((g) => (
                          <li key={g.index} className="mono" style={{ fontSize: 13 }}>
                            [{g.index}] {g.name} — {g.memory_total_mib} MiB
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ marginTop: 8 }}>GPU не перечислены.</div>
                    )}
                  </>
                ) : (
                  <div>{data.host.nvidia.note ?? "nvidia-smi недоступен."}</div>
                )}
              </div>
            </div>
          </div>
        )}
      </Section>

      <Section
        title="GPU (live)"
        subtitle="VRAM и загрузка с хоста (nvidia-smi), опрос каждые 3 с. Пресет — по слотам runtime из БД (совпадение индексов GPU)."
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => gpuLive.refetch()}
            disabled={gpuLive.isFetching}
          >
            Обновить
          </button>
        }
      >
        {gpuLive.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : gpuLive.isError ? (
          <div className="empty-state">Не удалось получить /gpu/state.</div>
        ) : !gpuLive.data?.smi_available ? (
          <div className="empty-state">
            nvidia-smi недоступен{gpuLive.data?.error ? ` (${gpuLive.data.error})` : ""} — подключите GPU к Docker и образ
            WEB_NVIDIA_SMI_DOCKER_IMAGE.
          </div>
        ) : (
          <div className="cards-grid">
            {gpuLive.data.gpus.map((g) => {
              const u = numGpu(g.memory_used_mib);
              const t = numGpu(g.memory_total_mib);
              const util = numGpu(g.utilization_gpu);
              const vramPct = t > 0 ? Math.min(100, Math.round((u / t) * 100)) : 0;
              const preset = presetForGpuIndex(g.index, data?.runtime.slots);
              const gid = g.uuid != null && g.uuid !== "" ? String(g.uuid) : null;
              const procsOnGpu = (gpuLive.data?.processes ?? []).filter((p: GpuProcessState) => {
                const pu = p.gpu_uuid != null && p.gpu_uuid !== "" ? String(p.gpu_uuid) : null;
                return Boolean(gid && pu && gid === pu);
              });
              return (
                <div className="status-card" key={g.index}>
                  <div className="status-card__head">
                    <span className="status-card__name">GPU {g.index}</span>
                    <StatusBadge
                      status={util >= 90 ? "degraded" : util >= 50 ? "unknown" : "healthy"}
                      label={`${util}%`}
                    />
                  </div>
                  <div className="status-card__detail mono" style={{ fontSize: 13 }}>
                    {g.name || "—"}
                  </div>
                  {preset ? (
                    <div className="status-card__detail" style={{ marginTop: 6, fontSize: 12 }}>
                      Пресет: <span className="mono">{preset}</span>
                    </div>
                  ) : null}
                  <div className="status-card__detail" style={{ marginTop: 8 }}>
                    <div className="mono" style={{ fontSize: 12 }}>
                      VRAM {u} / {t} MiB
                    </div>
                    <VramBar pct={vramPct} height={8} borderRadius={4} marginTop={6} />
                  </div>
                  {procsOnGpu.length ? (
                    <div className="status-card__detail" style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 11, opacity: 0.85 }}>Процессы (nvidia-smi)</div>
                      {procsOnGpu.map((p: GpuProcessState) => (
                        <div key={p.pid} className="mono" style={{ fontSize: 11, marginTop: 4 }}>
                          pid {p.pid} {p.process_name ?? "—"} · {String(p.used_memory_mib ?? "—")} MiB
                          {p.slot_key ? ` · slot:${p.slot_key}` : " · external"}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </Section>

      <Section
        title="Слоты инференса"
        subtitle="Записи engine_slots с пробой /v1/models (primary-строка в API — слот default или первый по имени)."
      >
        {isLoading || !data ? (
          <div className="empty-state">Загружаем…</div>
        ) : data.runtime.slots.length === 0 ? (
          <div className="empty-state">
            Нет активных слотов в БД. Возможен запуск только через compose/bash без web — тогда
            сводка по primary в API и GPU live выше.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--registry">
              <thead>
                <tr>
                  <th>Слот</th>
                  <th>Движок</th>
                  <th>Пресет</th>
                  <th>Порт</th>
                  <th>TP</th>
                  <th>GPU</th>
                  <th>Контейнер</th>
                  <th>Модели</th>
                </tr>
              </thead>
              <tbody>
                {data.runtime.slots.map((s: RuntimeSlotView) => (
                  <tr key={s.slot_key}>
                    <td className="mono">{s.slot_key}</td>
                    <td className="mono">{s.engine}</td>
                    <td>{s.preset_name ?? "—"}</td>
                    <td className="mono">{s.api_port ?? "—"}</td>
                    <td>{s.tp ?? "—"}</td>
                    <td className="mono" style={{ maxWidth: 120 }}>
                      {s.gpu_indices ?? "—"}
                    </td>
                    <td>
                      <StatusBadge status={s.container_status ?? "unknown"} />
                      <div className="mono" style={{ fontSize: 11, marginTop: 4 }}>
                        {s.container_name ?? "—"}
                      </div>
                    </td>
                    <td className="mono" style={{ fontSize: 12, maxWidth: 200 }}>
                      {s.served_models.length ? s.served_models.join(", ") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section
        title="Сервисы"
        subtitle="Состояние мониторинга и LiteLLM по последнему опросу."
      >
        <div className="cards-grid">
          {data?.services.map((service) => (
            <div className="status-card" key={service.key}>
              <div className="status-card__head">
                <span className="status-card__name">{service.display_name}</span>
                <StatusBadge status={service.status} />
              </div>
              <div className="status-card__detail">
                {service.detail ?? service.container_status ?? "—"}
              </div>
              {service.url ? (
                <a
                  className="status-card__link"
                  href={service.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Открыть UI →
                </a>
              ) : null}
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
