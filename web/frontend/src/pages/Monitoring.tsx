import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { JobAccepted, ServiceCard } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

export function MonitoringPage() {
  const queryClient = useQueryClient();
  const services = useQuery({
    queryKey: ["monitoring", "services"],
    queryFn: () => api.get<ServiceCard[]>("/monitoring/services"),
    refetchInterval: 8_000,
  });

  const action = useMutation({
    mutationFn: (act: string) =>
      api.post<JobAccepted>("/monitoring/action", { action: act }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["monitoring", "services"] });
    },
  });

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
              disabled={action.isPending}
            >
              monitoring up
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => action.mutate("restart")}
              disabled={action.isPending}
            >
              restart
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => action.mutate("fix-perms")}
              disabled={action.isPending}
            >
              fix-perms
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => action.mutate("down")}
              disabled={action.isPending}
            >
              down
            </button>
          </>
        }
      />

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
