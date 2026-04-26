import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { DashboardData } from "@/api/types";
import { formatBytesIEC } from "@/components/formatters";
import { MetricCard } from "@/components/MetricCard";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

export function DashboardPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/dashboard"),
    refetchInterval: 10_000,
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
        title="Inference Runtime"
        subtitle="Реальный движок vLLM/SGLang в проекте slgpu по данным Docker и /v1/models."
      >
        {isLoading || !data ? (
          <div className="empty-state">Загружаем…</div>
        ) : data.runtime.engine ? (
          <div className="cards-grid">
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">Движок</span>
                <StatusBadge status={data.runtime.container_status ?? "unknown"} />
              </div>
              <div className="status-card__detail mono">
                {data.runtime.engine} • порт {data.runtime.api_port ?? "—"}
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">Метрики</span>
                <StatusBadge
                  status={data.runtime.metrics_available ? "healthy" : "down"}
                  label={data.runtime.metrics_available ? "ok" : "нет"}
                />
              </div>
              <div className="status-card__detail">
                {data.runtime.metrics_available
                  ? "Проверка /metrics из slgpu-web: ответ 200. Prometheus на хосте может собирать тот же endpoint."
                  : "Проверка /metrics из slgpu-web не прошла (см. WEB_LLM_HTTP_HOST и сеть slgpu). На хосте /metrics у движка всё ещё может быть доступен."}
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">Пресет запуска</span>
              </div>
              <div className="status-card__detail mono">
                {data.runtime.preset_name ?? "—"}
                {data.runtime.tp ? ` • TP ${data.runtime.tp}` : ""}
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">Модель пресета</span>
              </div>
              <div className="status-card__detail mono">
                {data.runtime.hf_id ?? "—"}
              </div>
            </div>
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">Обслуживаемые модели</span>
              </div>
              <div className="status-card__detail mono">
                {data.runtime.served_models.length === 0
                  ? "—"
                  : data.runtime.served_models.join(", ")}
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state">Контейнеры vLLM/SGLang не запущены.</div>
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
