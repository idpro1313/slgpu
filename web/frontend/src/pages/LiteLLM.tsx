import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import type { Job, JobAccepted, LiteLLMHealth, LiteLLMInfo } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

export function LiteLLMPage() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const health = useQuery({
    queryKey: ["litellm", "health"],
    queryFn: ({ signal }) => api.get<LiteLLMHealth>("/litellm/health", { signal }),
    refetchInterval: 10_000,
  });
  const info = useQuery({
    queryKey: ["litellm", "info"],
    queryFn: ({ signal }) => api.get<LiteLLMInfo>("/litellm/info", { signal }),
  });
  const models = useQuery({
    queryKey: ["litellm", "models"],
    queryFn: ({ signal }) =>
      api.get<Array<{ id: string; object?: string }>>("/litellm/models", { signal }),
    refetchInterval: 15_000,
  });

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/jobs"),
    refetchInterval: 2_000,
  });

  const proxyAction = useMutation({
    mutationFn: (act: string) =>
      api.post<JobAccepted>("/litellm/proxy/action", { action: act }),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
      queryClient.invalidateQueries({ queryKey: ["litellm"] });
      queryClient.invalidateQueries({ queryKey: ["monitoring", "services"] });
    },
    onError: (err: Error) => setActionError(err.message),
  });

  const activeStackJob = jobs.data?.find(
    (job) => job.scope === "monitoring" && (job.status === "queued" || job.status === "running"),
  );
  const stackBusy = Boolean(activeStackJob) || proxyAction.isPending;

  return (
    <>
      <PageHeader
        title="LiteLLM Proxy"
        subtitle="OpenAI-совместимый шлюз (compose `slgpu-proxy`). Старт/стоп только прокси — кнопки справа; полный стек мониторинга — страница «Мониторинг». Пока выполняется любая job мониторинга или прокси, кнопки заблокированы."
        actions={
          <div className="flex flex--gap-sm flex--wrap" style={{ alignItems: "center" }}>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => proxyAction.mutate("up")}
              disabled={stackBusy}
              title="docker compose -f docker-compose.proxy.yml up -d"
            >
              Прокси up
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => proxyAction.mutate("restart")}
              disabled={stackBusy}
            >
              Перезапуск
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={() => proxyAction.mutate("down")}
              disabled={stackBusy}
            >
              Прокси down
            </button>
            {info.data?.ui_url ? (
              <a className="btn" href={info.data.ui_url} target="_blank" rel="noreferrer">
                Admin UI
              </a>
            ) : (
              <span className="btn btn--ghost" aria-disabled="true" title="Дождитесь загрузки URL">
                Admin UI…
              </span>
            )}
          </div>
        }
      />

      {stackBusy ? (
        <Section
          title="Команда стека выполняется"
          subtitle="Полный monitoring или прокси LiteLLM — один lock; повтор до завершения job вернёт 409."
        >
          {activeStackJob ? (
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">
                  #{activeStackJob.id} {activeStackJob.kind}
                </span>
                <StatusBadge status={activeStackJob.status} />
              </div>
              <div className="status-card__detail mono">
                {activeStackJob.message ?? activeStackJob.command.join(" ")}
              </div>
              <div className="status-card__detail">Подробности — в «Задачи».</div>
            </div>
          ) : (
            <div className="empty-state">Отправляем команду…</div>
          )}
        </Section>
      ) : null}
      {actionError ? <p style={{ color: "var(--color-danger)" }}>{actionError}</p> : null}

      <Section title="Health" subtitle="Liveliness / Readiness / UI">
        <div className="cards-grid">
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">/health/liveliness</span>
              <StatusBadge
                status={health.data?.liveliness ? "healthy" : "down"}
                label={health.data?.liveliness ? "ok" : "fail"}
              />
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">/health/readiness</span>
              <StatusBadge
                status={health.data?.readiness ? "healthy" : "down"}
                label={health.data?.readiness ? "ok" : "fail"}
              />
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">/ui</span>
              <StatusBadge
                status={health.data?.ui ? "healthy" : "down"}
                label={health.data?.ui ? "ok" : "fail"}
              />
            </div>
            {info.data ? (
              <div className="status-card__detail mono">{info.data.ui_url}</div>
            ) : null}
          </div>
        </div>
      </Section>

      <Section title="Маршруты" subtitle="Список моделей из LiteLLM /v1/models.">
        {models.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !models.data || models.data.length === 0 ? (
          <div className="empty-state">
            Маршрутов нет. Добавьте их в LiteLLM Admin UI — наше приложение их не дублирует.
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Model id</th>
                <th>Object</th>
              </tr>
            </thead>
            <tbody>
              {models.data.map((model) => (
                <tr key={model.id}>
                  <td className="mono">{model.id}</td>
                  <td>{model.object ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </>
  );
}
