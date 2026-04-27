import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Job, JobAccepted, ServiceCard } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

export function MonitoringPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: ({ signal }) => api.get<Job[]>("/jobs", { signal }),
    refetchInterval: 2_000,
  });
  const services = useQuery({
    queryKey: ["monitoring", "services"],
    queryFn: ({ signal }) => api.get<ServiceCard[]>("/monitoring/services", { signal }),
    refetchInterval: 8_000,
  });

  const action = useMutation({
    mutationFn: (act: string) =>
      api.post<JobAccepted>("/monitoring/action", { action: act }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
      queryClient.invalidateQueries({ queryKey: ["monitoring", "services"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const activeMonitoringJob = jobs.data?.find(
    (job) => job.scope === "monitoring" && (job.status === "queued" || job.status === "running"),
  );
  const monitoringBusy = Boolean(activeMonitoringJob) || action.isPending;

  return (
    <>
      <PageHeader
        title="Стек мониторинга"
        subtitle="Prometheus, Grafana, Loki, Promtail, DCGM, Node Exporter, Langfuse и LiteLLM-проба."
        actions={
          <>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => action.mutate("up")}
              disabled={monitoringBusy}
            >
              monitoring up
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => action.mutate("restart")}
              disabled={monitoringBusy}
            >
              restart
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => action.mutate("down")}
              disabled={monitoringBusy}
            >
              down
            </button>
          </>
        }
      />

      {monitoringBusy ? (
        <Section
          title="Команда мониторинга выполняется"
          subtitle="Пока job не завершилась, повторные up/restart/down заблокированы."
        >
          {activeMonitoringJob ? (
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">
                  #{activeMonitoringJob.id} {activeMonitoringJob.kind}
                </span>
                <StatusBadge status={activeMonitoringJob.status} />
              </div>
              <div className="status-card__detail mono">
                {activeMonitoringJob.message ?? activeMonitoringJob.command.join(" ")}
              </div>
              <div className="status-card__detail">
                Подробный stdout/stderr tail доступен на вкладке «Задачи».
              </div>
            </div>
          ) : (
            <div className="empty-state">Отправляем команду в job runner…</div>
          )}
        </Section>
      ) : null}
      {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}

      <Section title="Сервисы" subtitle="Опрос Docker + HTTP-проба, обновление каждые 8 секунд.">
        {services.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !services.data || services.data.length === 0 ? (
          <div className="empty-state">Нет данных от Docker daemon.</div>
        ) : (
          <div className="cards-grid">
            {services.data.map((service) => (
              <div className="status-card" key={service.key}>
                <div className="status-card__head">
                  <span className="status-card__name">{service.display_name}</span>
                  <StatusBadge status={service.status} />
                </div>
                <div className="status-card__detail">
                  {service.detail ?? "ok"}
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
        )}
      </Section>
    </>
  );
}
