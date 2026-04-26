import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { DashboardData } from "@/api/types";
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
        subtitle="Сводка по моделям, активным запускам, мониторингу и LiteLLM. Обновляется каждые 10 секунд."
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
                /metrics доступен и собирается Prometheus
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
