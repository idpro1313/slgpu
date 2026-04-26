import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Job, JobAccepted, PublicAccessSettings } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

type AppConfigStatus = { installed: boolean; meta: Record<string, unknown> };
type AppConfigStack = {
  stack: Record<string, string>;
  secrets: Record<string, string>;
  meta: Record<string, unknown>;
};

type StackRow = { id: string; key: string; value: string; isSecret: boolean };

function newRowId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `r-${Math.random().toString(36).slice(2)}`;
}

function rowsFromServer(data: AppConfigStack): StackRow[] {
  const stack = data.stack ?? {};
  const sec = data.secrets ?? {};
  return [
    ...Object.keys(stack)
      .sort()
      .map((k) => ({
        id: newRowId(),
        key: k,
        value: stack[k] ?? "",
        isSecret: false as const,
      })),
    ...Object.keys(sec)
      .sort()
      .map((k) => ({
        id: newRowId(),
        key: k,
        value: "",
        isSecret: true as const,
      })),
  ];
}

function buildStackPatch(
  data: AppConfigStack | undefined,
  rows: StackRow[],
): { stack?: Record<string, string | null>; secrets?: Record<string, string | null> } | null {
  if (!data) return null;
  const norm = rows
    .map((r) => ({ ...r, k: r.key.trim() }))
    .filter((r) => r.k.length > 0);
  const byKey = new Map<string, (typeof norm)[0]>();
  for (const r of norm) {
    byKey.set(r.k, r);
  }
  const uniq = [...byKey.values()];
  const stackRows = uniq.filter((r) => !r.isSecret);
  const secretRows = uniq.filter((r) => r.isSecret);

  const stack: Record<string, string | null> = {};
  const secrets: Record<string, string | null> = {};

  const editedStackKeys = new Set(stackRows.map((r) => r.k));
  for (const k of Object.keys(data.stack ?? {})) {
    if (!editedStackKeys.has(k)) stack[k] = null;
  }
  for (const r of stackRows) {
    stack[r.k] = r.value;
  }

  const editedSecretKeys = new Set(secretRows.map((r) => r.k));
  for (const k of Object.keys(data.secrets ?? {})) {
    if (!editedSecretKeys.has(k)) secrets[k] = null;
  }
  for (const r of secretRows) {
    const v = r.value.trim();
    if (v) secrets[r.k] = v;
  }

  const out: { stack?: Record<string, string | null>; secrets?: Record<string, string | null> } =
    {};
  if (Object.keys(stack).length > 0) out.stack = stack;
  if (Object.keys(secrets).length > 0) out.secrets = secrets;
  if (!out.stack && !out.secrets) return null;
  return out;
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [serverHost, setServerHost] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [stackRows, setStackRows] = useState<StackRow[]>([]);
  const [installForce, setInstallForce] = useState(false);
  const [cfgMessage, setCfgMessage] = useState<string | null>(null);
  const [cfgError, setCfgError] = useState<string | null>(null);

  const publicAccess = useQuery({
    queryKey: ["settings", "public-access"],
    queryFn: () => api.get<PublicAccessSettings>("/settings/public-access"),
  });

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/jobs"),
    refetchInterval: 2_000,
  });

  const appStatus = useQuery({
    queryKey: ["app-config", "status"],
    queryFn: () => api.get<AppConfigStatus>("/app-config/status"),
  });

  const appStack = useQuery({
    queryKey: ["app-config", "stack"],
    queryFn: () => api.get<AppConfigStack>("/app-config/stack"),
  });

  const installCfg = useMutation({
    mutationFn: (force: boolean) =>
      api.post<{ installed: boolean; stack_keys: number; secret_keys: number }>(
        "/app-config/install",
        { force },
      ),
    onSuccess: (res) => {
      setCfgError(null);
      setCfgMessage(
        `Импорт выполнен: ключей стека ${res.stack_keys}, секретов ${res.secret_keys}.`,
      );
      queryClient.invalidateQueries({ queryKey: ["app-config"] });
    },
    onError: (err: Error) => {
      setCfgMessage(null);
      setCfgError(err.message);
    },
  });

  const patchStack = useMutation({
    mutationFn: (body: {
      stack?: Record<string, string | null>;
      secrets?: Record<string, string | null>;
    }) => api.patch("/app-config/stack", body),
    onSuccess: () => {
      setCfgError(null);
      setCfgMessage("Стек и секреты обновлены в БД.");
      queryClient.invalidateQueries({ queryKey: ["app-config"] });
    },
    onError: (err: Error) => {
      setCfgMessage(null);
      setCfgError(err.message);
    },
  });

  const monitoringAction = useMutation({
    mutationFn: (act: string) =>
      api.post<JobAccepted>("/monitoring/action", { action: act }),
    onSuccess: () => {
      setJobError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
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

  useEffect(() => {
    if (appStack.data) {
      setStackRows(rowsFromServer(appStack.data));
    }
  }, [appStack.data]);

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

  function onSaveStack(event: FormEvent) {
    event.preventDefault();
    setCfgMessage(null);
    setCfgError(null);
    const patch = buildStackPatch(appStack.data, stackRows);
    if (!patch) {
      setCfgError("Нет изменений для сохранения (или данные ещё не загружены).");
      return;
    }
    patchStack.mutate(patch);
  }

  return (
    <>
      <PageHeader
        title="Настройки"
        subtitle="Публичный адрес сервера, импорт стека из main.env и правка плоских ключей в SQLite (таблица stack_params: одна строка на параметр). Секреты в API маскируются; для смены введите новое значение в строке (не вставляйте ***)."
      />

      {(cfgMessage || cfgError) && (
        <p style={{ color: cfgError ? "var(--color-danger)" : "var(--color-success)" }}>
          {cfgError ?? cfgMessage}
        </p>
      )}

      <Section
        title="Установка стека из файлов"
        subtitle="Читает `main.env` в корне репозитория и опционально `configs/secrets/hf.env`, `configs/secrets/langfuse-litellm.env`. Повтор без force вернёт 409."
      >
        <div className="flex flex--col flex--gap-sm">
          <p className="section__subtitle" style={{ margin: 0 }}>
            Статус:{" "}
            {appStatus.isLoading
              ? "…"
              : appStatus.data?.installed
                ? "установлено"
                : "не импортировано"}
            {appStatus.data?.meta && typeof appStatus.data.meta.installed_at === "string"
              ? ` · ${appStatus.data.meta.installed_at}`
              : null}
          </p>
          <label className="flex flex--gap-sm" style={{ alignItems: "center" }}>
            <input
              type="checkbox"
              checked={installForce}
              onChange={(e) => setInstallForce(e.target.checked)}
            />
            <span>Принудительно перезаписать (force)</span>
          </label>
          <button
            type="button"
            className="btn btn--primary"
            disabled={installCfg.isPending}
            onClick={() => installCfg.mutate(installForce)}
          >
            {installCfg.isPending ? "Импорт…" : "Импортировать из main.env"}
          </button>
        </div>
      </Section>

      <Section
        title="Стек и секреты (БД)"
        subtitle="Каждый параметр — отдельная строка в таблице `stack_params`. Галочка «секрет» — значение не отдаётся в API; оставьте поле пустым, если не меняете. Удаление строки удаляет ключ из БД."
      >
        {appStack.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : (
          <form className="flex flex--col flex--gap-md" onSubmit={onSaveStack}>
            <div className="flex flex--gap-sm flex--wrap">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() =>
                  setStackRows((prev) => [
                    ...prev,
                    { id: newRowId(), key: "", value: "", isSecret: false },
                  ])
                }
              >
                + параметр
              </button>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="table table--compact" style={{ width: "100%", minWidth: "520px" }}>
                <thead>
                  <tr>
                    <th>Ключ</th>
                    <th>Значение</th>
                    <th>Секрет</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {stackRows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <input
                          className="input"
                          value={row.key}
                          onChange={(e) =>
                            setStackRows((prev) =>
                              prev.map((r) =>
                                r.id === row.id ? { ...r, key: e.target.value } : r,
                              ),
                            )
                          }
                          spellCheck={false}
                          placeholder="VAR_NAME"
                          disabled={patchStack.isPending}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          value={row.value}
                          onChange={(e) =>
                            setStackRows((prev) =>
                              prev.map((r) =>
                                r.id === row.id ? { ...r, value: e.target.value } : r,
                              ),
                            )
                          }
                          spellCheck={false}
                          placeholder={
                            row.isSecret ? "новое значение (пусто = не менять)" : ""
                          }
                          disabled={patchStack.isPending}
                          type={row.isSecret ? "password" : "text"}
                          autoComplete="off"
                        />
                      </td>
                      <td style={{ width: "1%" }}>
                        <input
                          type="checkbox"
                          checked={row.isSecret}
                          onChange={(e) =>
                            setStackRows((prev) =>
                              prev.map((r) =>
                                r.id === row.id ? { ...r, isSecret: e.target.checked } : r,
                              ),
                            )
                          }
                          disabled={patchStack.isPending}
                          title="Секрет: не показывается в API после сохранения"
                        />
                      </td>
                      <td style={{ width: "1%" }}>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          disabled={patchStack.isPending}
                          onClick={() =>
                            setStackRows((prev) => prev.filter((r) => r.id !== row.id))
                          }
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="section__subtitle">
              Ключи с маской в ответе API:{" "}
              <span className="mono">
                {appStack.data ? JSON.stringify(Object.keys(appStack.data.secrets).sort()) : "—"}
              </span>
            </p>
            <button type="submit" className="btn btn--ghost" disabled={patchStack.isPending}>
              {patchStack.isPending ? "Сохранение…" : "Сохранить в БД"}
            </button>
          </form>
        )}
      </Section>

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
