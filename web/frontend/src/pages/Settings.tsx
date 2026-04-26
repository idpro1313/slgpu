import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Job, JobAccepted, PublicAccessSettings } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [serverHost, setServerHost] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);

  const publicAccess = useQuery({
    queryKey: ["settings", "public-access"],
    queryFn: () => api.get<PublicAccessSettings>("/settings/public-access"),
  });

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/jobs"),
    refetchInterval: 2_000,
  });

  const monitoringAction = useMutation({
    mutationFn: (act: string) =>
      api.post<JobAccepted>("/monitoring/action", { action: act }),
    onSuccess: () => {
      setJobError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["monitoring", "services"] });
    },
    onError: (err: Error) => setJobError(err.message),
  });

  const activeMonitoringJob = jobs.data?.find(
    (job) => job.scope === "monitoring" && (job.status === "queued" || job.status === "running"),
  );
  const monitoringBusy =
    Boolean(activeMonitoringJob) || monitoringAction.isPending;

  useEffect(() => {
    if (publicAccess.data) {
      setServerHost(publicAccess.data.server_host ?? "");
    }
  }, [publicAccess.data]);

  const save = useMutation({
    mutationFn: () =>
      api.patch<PublicAccessSettings>("/settings/public-access", {
        server_host: serverHost.trim() || null,
      }),
    onSuccess: () => {
      setError(null);
      setMessage("Настройки сохранены. Ссылки мониторинга обновятся после перезагрузки данных.");
      queryClient.invalidateQueries({ queryKey: ["settings", "public-access"] });
      queryClient.invalidateQueries({ queryKey: ["monitoring", "services"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["litellm", "info"] });
    },
    onError: (err: Error) => {
      setMessage(null);
      setError(err.message);
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  const data = publicAccess.data;

  return (
    <>
      <PageHeader
        title="Настройки"
        subtitle="Публичный адрес сервера используется только для ссылок, которые открывает браузер: Grafana, Prometheus, Langfuse и LiteLLM Admin UI."
      />

      <Section
        title="Адрес сервера"
        subtitle="Внутренние health-пробы из контейнера по-прежнему используют WEB_MONITORING_HTTP_HOST; здесь задаётся внешний host для пользователей."
      >
        <form className="flex flex--col flex--gap-md" onSubmit={onSubmit}>
          <label>
            <span className="label">IP адрес или DNS имя</span>
            <input
              className="input"
              placeholder="например: 10.10.10.25 или llm.example.local"
              value={serverHost}
              onChange={(event) => setServerHost(event.target.value)}
            />
          </label>
          <p className="section__subtitle">
            Не указывайте путь. Если поле пустое, Develonica.LLM использует hostname текущего
            запроса к приложению:{" "}
            <span className="mono">{data?.effective_server_host ?? "загрузка..."}</span>.
          </p>
          <div className="flex flex--gap-sm flex--wrap">
            <button type="submit" className="btn btn--primary" disabled={save.isPending}>
              {save.isPending ? "Сохраняем..." : "Сохранить"}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={save.isPending}
              onClick={() => setServerHost("")}
            >
              Использовать host приложения
            </button>
          </div>
          {message ? <p style={{ color: "var(--color-success)" }}>{message}</p> : null}
          {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}
        </form>
      </Section>

      <Section
        title="Права на каталоги мониторинга"
        subtitle="Команда `./slgpu monitoring fix-perms`: создаёт/чинит владельца bind-mount каталогов стека (Loki, Langfuse, LiteLLM и др.). Обычно нужна один раз на новом сервере; выполняется как фоновая задача. Пока идёт любая job мониторинга, кнопка заблокирована."
      >
        <div className="flex flex--col flex--gap-sm">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={monitoringBusy}
            onClick={() => monitoringAction.mutate("fix-perms")}
          >
            {monitoringAction.isPending ? "Запуск fix-perms…" : "fix-perms (chmod/chown mount’ов)"}
          </button>
          {activeMonitoringJob ? (
            <p className="section__subtitle" style={{ margin: 0 }}>
              Выполняется job мониторинга #{activeMonitoringJob.id} — дождитесь окончания или смотрите
              «Задачи».
            </p>
          ) : null}
          {jobError ? <p style={{ color: "var(--color-danger)" }}>{jobError}</p> : null}
        </div>
      </Section>

      <Section title="Итоговые ссылки" subtitle="Именно эти URL будут показаны на Dashboard, Monitoring и LiteLLM.">
        {publicAccess.isLoading || !data ? (
          <div className="empty-state">Загружаем...</div>
        ) : (
          <div className="cards-grid">
            <LinkCard title="Grafana" url={data.grafana_url} />
            <LinkCard title="Prometheus" url={data.prometheus_url} />
            <LinkCard title="Langfuse" url={data.langfuse_url} />
            <LinkCard title="LiteLLM Admin UI" url={data.litellm_ui_url} />
            <LinkCard title="LiteLLM API" url={data.litellm_api_url} />
          </div>
        )}
      </Section>
    </>
  );
}

function LinkCard({ title, url }: { title: string; url: string }) {
  return (
    <div className="status-card">
      <div className="status-card__head">
        <span className="status-card__name">{title}</span>
      </div>
      <div className="status-card__detail mono">{url}</div>
      <a className="status-card__link" href={url} target="_blank" rel="noreferrer">
        Открыть →
      </a>
    </div>
  );
}
