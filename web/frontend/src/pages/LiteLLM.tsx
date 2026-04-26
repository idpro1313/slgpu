import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { LiteLLMHealth } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

interface LiteLLMInfo {
  ui_url: string;
  api_url: string;
  port: number;
  note: string;
}

export function LiteLLMPage() {
  const health = useQuery({
    queryKey: ["litellm", "health"],
    queryFn: () => api.get<LiteLLMHealth>("/litellm/health"),
    refetchInterval: 10_000,
  });
  const info = useQuery({
    queryKey: ["litellm", "info"],
    queryFn: () => api.get<LiteLLMInfo>("/litellm/info"),
  });
  const models = useQuery({
    queryKey: ["litellm", "models"],
    queryFn: () => api.get<Array<{ id: string; object?: string }>>("/litellm/models"),
    refetchInterval: 15_000,
  });

  return (
    <>
      <PageHeader
        title="LiteLLM Proxy"
        subtitle="Single OpenAI-compatible API в проект slgpu. Маршрутами и ключами управляет Admin UI самого LiteLLM. Подъём стека мониторинга — со страницы «Мониторинг» или CLI."
        actions={
          <a className="btn" href={info.data?.ui_url} target="_blank" rel="noreferrer">
            Открыть Admin UI
          </a>
        }
      />

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
