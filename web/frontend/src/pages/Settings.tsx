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

/** Явные пути и * _DATA_DIR (кроме ключей инференса — их нет с таким суффиксом в типичном стеке). */
const PATH_KEYS = new Set<string>([
  "MODELS_DIR",
  "PRESETS_DIR",
  "WEB_DATA_DIR",
  "SLGPU_MODEL_ROOT",
  "PROMETHEUS_DATA_DIR",
  "GRAFANA_DATA_DIR",
  "LOKI_DATA_DIR",
  "PROMTAIL_DATA_DIR",
]);

function isPathKey(key: string): boolean {
  return PATH_KEYS.has(key) || key.endsWith("_DATA_DIR");
}

const MONITORING_COMPOSE_KEYS = new Set<string>([
  "PROMETHEUS_PORT",
  "GRAFANA_PORT",
  "LANGFUSE_PORT",
  "LITELLM_PORT",
  "LOKI_PORT",
  "WEB_COMPOSE_PROJECT_INFER",
  "WEB_COMPOSE_PROJECT_MONITORING",
]);

const WEB_UI_KEYS = new Set<string>(["WEB_PORT", "WEB_BIND", "WEB_LOG_LEVEL"]);

const LLM_API_KEYS = new Set<string>(["LLM_API_BIND", "LLM_API_PORT", "LLM_API_PORT_SGLANG"]);

const INFERENCE_EXACT = new Set<string>([
  "TP",
  "GPU_MEM_UTIL",
  "MAX_MODEL_LEN",
  "KV_CACHE_DTYPE",
  "NVIDIA_VISIBLE_DEVICES",
  "TOOL_CALL_PARSER",
  "REASONING_PARSER",
  "SLGPU_SERVED_MODEL_NAME",
  "MODEL_ID",
  "MODEL_REVISION",
]);

function isInferenceKey(key: string): boolean {
  if (INFERENCE_EXACT.has(key)) return true;
  if (key.startsWith("SLGPU_") && key !== "SLGPU_MODEL_ROOT") return true;
  if (key.startsWith("VLLM_")) return true;
  if (key.startsWith("SGLANG_")) return true;
  if (key.startsWith("MM_ENCODER_")) return true;
  if (key.startsWith("CHAT_TEMPLATE_")) return true;
  return false;
}

type StackParamGroupId =
  | "paths"
  | "web"
  | "llm_api"
  | "monitoring"
  | "inference"
  | "other"
  | "secrets";

const STACK_GROUP_ORDER: StackParamGroupId[] = [
  "paths",
  "web",
  "llm_api",
  "monitoring",
  "inference",
  "other",
  "secrets",
];

const STACK_GROUP_META: Record<
  StackParamGroupId,
  { title: string; subtitle: string }
> = {
  paths: {
    title: "Пути и каталоги",
    subtitle: "Модели, пресеты, данные web и каталоги мониторинга на хосте.",
  },
  web: {
    title: "Web UI приложения",
    subtitle: "Порт и bind Develonica.LLM, уровень лога.",
  },
  llm_api: {
    title: "Сеть API движка",
    subtitle: "Адрес и порты OpenAI-совместимого API vLLM / SGLang.",
  },
  monitoring: {
    title: "Мониторинг и compose",
    subtitle: "Порты Prometheus, Grafana, Langfuse, LiteLLM, Loki и имена compose-проектов.",
  },
  inference: {
    title: "GPU и инференс",
    subtitle: "TP, память, KV, видимые GPU, парсеры, переменные SLGPU_ / VLLM_ / SGLANG_ и др.",
  },
  other: {
    title: "Прочие параметры",
    subtitle: "Ключи вне типовых групп и новые переменные.",
  },
  secrets: {
    title: "Секреты и ключи",
    subtitle:
      "Значения не отдаются в API; пустое поле — не менять. Список имён с маской см. ниже формы.",
  },
};

function stackParamGroupId(row: StackRow): StackParamGroupId {
  if (row.isSecret) return "secrets";
  const k = row.key.trim();
  if (!k) return "other";
  if (isPathKey(k)) return "paths";
  if (MONITORING_COMPOSE_KEYS.has(k)) return "monitoring";
  if (WEB_UI_KEYS.has(k)) return "web";
  if (LLM_API_KEYS.has(k)) return "llm_api";
  if (isInferenceKey(k)) return "inference";
  return "other";
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
  /** Пусто = не менять; ввод = новый ключ; сброс — отдельная кнопка. */
  const [litellmKey, setLiteLLMKey] = useState("");
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

  const clearLiteLLMKey = useMutation({
    mutationFn: () =>
      api.patch<PublicAccessSettings>("/settings/public-access", { litellm_api_key: null }),
    onSuccess: () => {
      setError(null);
      setMessage("API-ключ LiteLLM сброшен в БД.");
      setLiteLLMKey("");
      queryClient.invalidateQueries({ queryKey: ["settings", "public-access"] });
      queryClient.invalidateQueries({ queryKey: ["monitoring", "services"] });
      queryClient.invalidateQueries({ queryKey: ["litellm", "info"] });
    },
    onError: (err: Error) => {
      setMessage(null);
      setError(err.message);
    },
  });

  const save = useMutation({
    mutationFn: () => {
      const body: { server_host: string | null; litellm_api_key?: string } = {
        server_host: serverHost.trim() || null,
      };
      const k = litellmKey.trim();
      if (k) body.litellm_api_key = k;
      return api.patch<PublicAccessSettings>("/settings/public-access", body);
    },
    onSuccess: () => {
      setError(null);
      setMessage("Настройки сохранены. Ссылки на других страницах обновятся после перезагрузки данных.");
      setLiteLLMKey("");
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
        subtitle="Публичный адрес для ссылок в UI, стек в БД (файлы и таблица параметров по смыслу), обслуживание каталогов мониторинга."
      />

      {(cfgMessage || cfgError) && (
        <p style={{ color: cfgError ? "var(--color-danger)" : "var(--color-success)" }}>
          {cfgError ?? cfgMessage}
        </p>
      )}

      <div className="settings-group">
        <h2 className="settings-group__heading">Внешний доступ</h2>
        <p className="settings-group__lead">
          Host для подстановки в URL Grafana, Prometheus, Langfuse и LiteLLM на Dashboard и смежных
          страницах. Внутренние проверки из контейнера используют{" "}
          <span className="mono">WEB_MONITORING_HTTP_HOST</span> и порты из стека.
        </p>

        <Section
          title="Публичный адрес сервера"
          subtitle="Если пусто — в ссылках используется hostname текущего запроса к приложению."
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
              Не указывайте путь. Сейчас эффективный host:{" "}
              <span className="mono">{data?.effective_server_host ?? "загрузка..."}</span>.
            </p>
            <label>
              <span className="label">API-ключ LiteLLM (LITELLM_MASTER_KEY / proxy key)</span>
              <input
                className="input"
                type="password"
                autoComplete="off"
                placeholder="оставьте пустым, чтобы не менять; новый ключ — для запросов /v1 из backend"
                value={litellmKey}
                onChange={(e) => setLiteLLMKey(e.target.value)}
              />
            </label>
            <p className="section__subtitle" style={{ margin: 0 }}>
              Ключ в базе:{" "}
              {publicAccess.isLoading
                ? "…"
                : data?.litellm_api_key_set
                  ? "задан (значение не показывается)"
                  : "не задан — при необходимости заполните, если у LiteLLM включена авторизация."}
            </p>
            <div className="flex flex--gap-sm flex--wrap">
              <button type="submit" className="btn btn--primary" disabled={save.isPending}>
                {save.isPending ? "Сохраняем..." : "Сохранить"}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={clearLiteLLMKey.isPending || publicAccess.isLoading}
                onClick={() => {
                  if (!data?.litellm_api_key_set) return;
                  if (!globalThis.confirm("Удалить сохранённый API-ключ LiteLLM?")) return;
                  clearLiteLLMKey.mutate();
                }}
                title="Очистить ключ в настройках"
              >
                {clearLiteLLMKey.isPending ? "…" : "Сбросить API-ключ"}
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
      </div>

      <div className="settings-group">
        <h2 className="settings-group__heading">Стек в базе данных</h2>
        <p className="settings-group__lead">
          Первичный импорт из <span className="mono">main.env</span> и связанных secret-файлов; правка
          переменных — по группам ниже (<span className="mono">stack_params</span>). Для смены секрета
          введите новое значение в строке, не вставляйте <span className="mono">***</span>.
        </p>

        <Section
          title="Импорт из файлов"
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
          title="Параметры окружения"
          subtitle="Группы по назначению. Галочка «секрет» переносит ключ в последнюю группу; удаление строки удаляет ключ из БД."
        >
          {appStack.isLoading ? (
            <div className="empty-state">Загружаем…</div>
          ) : (
            <form className="flex flex--col flex--gap-md" onSubmit={onSaveStack}>
              {STACK_GROUP_ORDER.map((gid) => {
                const rowsInGroup = stackRows.filter((r) => stackParamGroupId(r) === gid);
                const meta = STACK_GROUP_META[gid];
                const showEmptyOther = gid === "other";
                if (rowsInGroup.length === 0 && !showEmptyOther) return null;

                return (
                  <div key={gid} className="settings-stack-subgroup">
                    <h3 className="settings-stack-subgroup__title">{meta.title}</h3>
                    <p className="settings-stack-subgroup__lead">{meta.subtitle}</p>
                    {gid === "other" ? (
                      <div className="flex flex--gap-sm flex--wrap" style={{ marginBottom: 12 }}>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() =>
                            setStackRows((prev) => [
                              ...prev,
                              { id: newRowId(), key: "", value: "", isSecret: false },
                            ])
                          }
                          disabled={patchStack.isPending}
                        >
                          + параметр
                        </button>
                      </div>
                    ) : null}
                    <div style={{ overflowX: "auto" }}>
                      <table
                        className="table table--compact"
                        style={{ width: "100%", minWidth: "520px" }}
                      >
                        <thead>
                          <tr>
                            <th>Ключ</th>
                            <th>Значение</th>
                            <th>Секрет</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {rowsInGroup.map((row) => (
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
                    {rowsInGroup.length === 0 && gid === "other" ? (
                      <p className="section__subtitle" style={{ marginTop: 8 }}>
                        Нет пользовательских ключей. Добавьте строку кнопкой «+ параметр».
                      </p>
                    ) : null}
                  </div>
                );
              })}

              <p className="section__subtitle">
                Имена секретов в API (маскированы):{" "}
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
      </div>

      <div className="settings-group">
        <h2 className="settings-group__heading">Обслуживание хоста</h2>
        <p className="settings-group__lead">
          Разовые операции на стороне сервера: права на каталоги данных мониторинга (bind mount).
        </p>

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
      </div>
    </>
  );
}
