import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  AppConfigStack,
  AppConfigStatus,
  Job,
  JobAccepted,
  PublicAccessSettings,
} from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

type RegistryEntry = NonNullable<AppConfigStack["registry"]>[number];

type StackRow = {
  id: string;
  key: string;
  value: string;
  isSecret: boolean;
  /** true: ключ существует в реестре stack_registry — флаг секрета и группа фиксированы. */
  fromRegistry: boolean;
  /**
   * Только для `isSecret=true`. true → значение секрета уже задано в БД
   * (backend вернул `data.secrets[key] === "***"`). UI:
   *  · показывает «••••••••» как placeholder и подпись «значение задано»;
   *  · НЕ подсвечивает красным даже для required-ключей;
   *  · пустой ввод при сохранении трактуется как «не менять» (см. buildStackPatch).
   */
  secretSet: boolean;
};

function newRowId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `r-${Math.random().toString(36).slice(2)}`;
}

/**
 * ID групп = разделы `configs/main.env` 1..8.
 * Порядок повторяет порядок секций в main.env (registry на бэке тоже отсортирован
 * в этом порядке, см. _STACK_KEY_REGISTRY).
 */
type StackGroupId =
  | "network"
  | "web"
  | "paths"
  | "images"
  | "inference"
  | "monitoring"
  | "proxy"
  | "secrets"
  | "other";

const STACK_GROUP_ORDER: StackGroupId[] = [
  "network",
  "web",
  "paths",
  "images",
  "inference",
  "monitoring",
  "proxy",
  "secrets",
  "other",
];

const STACK_GROUP_META: Record<StackGroupId, { title: string; subtitle: string }> = {
  network: {
    title: "1. Сеть Docker и compose-проекты",
    subtitle:
      "Имя общей Docker-сети slgpu и имена docker-compose проектов для слотов инференса, мониторинга и прокси.",
  },
  web: {
    title: "2. Web UI (slgpu-web)",
    subtitle:
      "Образ, контейнер, внутренний и опубликованный порт slgpu-web; уровень логов uvicorn; запасной host для публичных ссылок и host-проб мониторинга/LLM из контейнера web.",
  },
  paths: {
    title: "3. Пути на хосте (bind mount)",
    subtitle:
      "Абсолютные пути для slgpu-web, моделей, пресетов, данных мониторинга и прокси (Prometheus TSDB, Grafana, Loki/Promtail, Postgres/ClickHouse/MinIO/Redis), а также образ для chown в fix-perms.",
  },
  images: {
    title: "4. Образы Docker (LLM + monitoring + proxy)",
    subtitle:
      "Теги контейнеров vLLM, SGLang, Prometheus/Grafana/Loki/Promtail, DCGM/NodeExporter, Langfuse + Worker, Postgres/Redis/ClickHouse, MinIO/mc, LiteLLM.",
  },
  inference: {
    title: "5. Инференс — LLM API, движок, vLLM, SGLang, кеши",
    subtitle:
      "Движок (vllm|sglang), модель/ревизия, LLM_API_BIND и хост-порты (vLLM / SGLang); listen внутри контейнеров подставляется из них автоматически — отдельные поля в UI скрыты. Далее авто-диапазоны слотов, параметры vLLM и SGLang.",
  },
  monitoring: {
    title: "6. Мониторинг — Prometheus, Grafana, Loki, Promtail, DCGM, NodeExporter",
    subtitle:
      "DNS-имена сервисов в сети slgpu, внутренние и опубликованные порты, имена контейнеров; ретенция Prometheus, учётка Grafana, GF_SERVER_ROOT_URL. Конфиги *.tmpl рендерятся backend'ом из этих значений.",
  },
  proxy: {
    title: "7. Прокси — Langfuse + LiteLLM + Postgres + Redis + ClickHouse + MinIO",
    subtitle:
      "DNS-имена/порты/контейнеры сервисов прокси-стека, host bind и порты Langfuse/Worker/LiteLLM/MinIO, креды Postgres/Redis/ClickHouse/MinIO, NEXTAUTH_URL/SECRET, salt/encryption-key, S3-бакеты, ключи Langfuse для интеграции LiteLLM (OTEL).",
  },
  secrets: {
    title: "8. Секреты приложения",
    subtitle:
      "Отдельные секреты, не привязанные к стеку прокси/мониторинга (HF_TOKEN). Значения не отдаются в API; пустое поле — оставить как есть. Сброс — стереть значение и сохранить.",
  },
  other: {
    title: "Прочие параметры",
    subtitle:
      "Ключи вне реестра — добавленные пользователем переменные. Backend их не валидирует.",
  },
};

const SCOPE_LABELS: Record<string, string> = {
  web_up: "запуск web",
  monitoring_up: "монитори&shy;нг",
  proxy_up: "LiteLLM/Langfuse",
  llm_slot: "LLM-слот",
  fix_perms: "fix-perms",
  pull: "загрузка моделей",
  bench: "бенчмарк",
  port_allocation: "распределение портов",
  probes: "пробы",
};

function formatScopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

function isMissingRequired(
  meta: RegistryEntry | undefined,
  value: string,
  secretSet: boolean,
): boolean {
  if (!meta) return false;
  if (meta.allow_empty) return false;
  if (meta.required_for.length === 0) return false;
  // Для секретов backend никогда не возвращает значение, но через `secretSet`
  // (`data.secrets[key] === "***"`) мы знаем, что в БД оно уже есть. Тогда строка
  // не считается «missing» — даже при пустом поле value (которое для секрета
  // означает «не менять»).
  if (meta.is_secret && secretSet) return false;
  return value.trim() === "";
}

function rowsFromServer(data: AppConfigStack): StackRow[] {
  const stack = data.stack ?? {};
  const sec = data.secrets ?? {};
  const registry = data.registry ?? [];

  const rows: StackRow[] = [];
  const seen = new Set<string>();

  // Реестр приходит с backend в порядке секций main.env (registry_to_public()
  // не сортирует — отдаёт порядок _STACK_KEY_REGISTRY). Поэтому идём по нему
  // как есть: секции 1..8 и внутри секции — порядок ключей из main.env.
  for (const meta of registry) {
    if (meta.ui_hidden) continue;
    const k = meta.key;
    const isSecret = meta.is_secret;
    const value = isSecret ? "" : (stack[k] ?? "");
    // Для секретов backend возвращает в `data.secrets` маску ("***" если значение
    // в БД задано, "" если ключ есть, но без значения). Признак «значение в БД
    // задано» нужен фронту, чтобы не подсвечивать строку красным как «не
    // заполнено».
    const secretSet = isSecret && Boolean(sec[k] && sec[k] !== "");
    rows.push({ id: newRowId(), key: k, value, isSecret, fromRegistry: true, secretSet });
    seen.add(k);
  }

  // Пользовательские ключи из БД, которых нет в реестре, — попадут в группу
  // "other"; внутри неё сортируем по имени, для стабильного UI.
  for (const k of Object.keys(stack).sort()) {
    if (seen.has(k)) continue;
    rows.push({
      id: newRowId(),
      key: k,
      value: stack[k] ?? "",
      isSecret: false,
      fromRegistry: false,
      secretSet: false,
    });
    seen.add(k);
  }
  for (const k of Object.keys(sec).sort()) {
    if (seen.has(k)) continue;
    rows.push({
      id: newRowId(),
      key: k,
      value: "",
      isSecret: true,
      fromRegistry: false,
      secretSet: Boolean(sec[k] && sec[k] !== ""),
    });
    seen.add(k);
  }
  return rows;
}

/**
 * Группа строки = `meta.group` из реестра (= раздел main.env).
 * Чекбокс «секрет» НЕ перекидывает строку в группу `secrets` — секреты
 * отображаются в своих смысловых разделах (как в main.env, где
 * GRAFANA_ADMIN_PASSWORD живёт в «Мониторинг», а LANGFUSE_SALT — в «Прокси»).
 */
function stackGroupId(row: StackRow, regByKey: Map<string, RegistryEntry>): StackGroupId {
  const meta = regByKey.get(row.key.trim());
  if (meta) {
    const g = meta.group as StackGroupId;
    if ((STACK_GROUP_ORDER as string[]).includes(g)) return g;
    return "other";
  }
  // Пользовательские ключи всегда в "other".
  return "other";
}

/** Ключи с ui_hidden не участвуют в форме; при сохранении не отправляют null для строк, отсутствующих в UI. */
function buildStackPatch(
  data: AppConfigStack | undefined,
  rows: StackRow[],
  registry: RegistryEntry[] | undefined,
): { stack?: Record<string, string | null>; secrets?: Record<string, string | null> } | null {
  if (!data) return null;
  const hiddenKeys = new Set(
    (registry ?? []).filter((e) => e.ui_hidden === true).map((e) => e.key.trim()),
  );
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

  // stack: апсёртим только реальные значения; пустые в форме считаем «не задано» —
  // если ключ был в БД, удаляем (null), иначе ничего не делаем (не плодим пустые записи).
  const existingStackKeys = new Set(Object.keys(data.stack ?? {}));
  for (const r of stackRows) {
    const v = r.value;
    if (v === "") {
      if (existingStackKeys.has(r.k)) stack[r.k] = null;
    } else {
      stack[r.k] = v;
    }
  }
  // Удалённые в форме ключи (отсутствуют в норме, но были в БД) — null.
  const formStackKeys = new Set(stackRows.map((r) => r.k));
  for (const k of existingStackKeys) {
    if (!formStackKeys.has(k)) {
      if (hiddenKeys.has(k)) continue;
      stack[k] = null;
    }
  }

  // secrets: пустое значение = «не менять»; ввод нового — апсёрт; удаление строки = null.
  const existingSecretKeys = new Set(Object.keys(data.secrets ?? {}));
  for (const r of secretRows) {
    const v = r.value.trim();
    if (v) secrets[r.k] = v;
  }
  const formSecretKeys = new Set(secretRows.map((r) => r.k));
  for (const k of existingSecretKeys) {
    if (!formSecretKeys.has(k)) secrets[k] = null;
  }

  const out: { stack?: Record<string, string | null>; secrets?: Record<string, string | null> } =
    {};
  if (Object.keys(stack).length > 0) out.stack = stack;
  if (Object.keys(secrets).length > 0) out.secrets = secrets;
  if (!out.stack && !out.secrets) return null;
  return out;
}

export function SettingsPage() {
  const [searchParams] = useSearchParams();
  const missingHighlight = useMemo(() => {
    const raw = searchParams.get("missing");
    if (!raw?.trim()) return new Set<string>();
    return new Set(
      raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    );
  }, [searchParams]);

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

  const regByKey = useMemo(() => {
    const m = new Map<string, RegistryEntry>();
    for (const r of appStack.data?.registry ?? []) m.set(r.key, r);
    return m;
  }, [appStack.data?.registry]);

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
    const patch = buildStackPatch(appStack.data, stackRows, appStack.data.registry);
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
          Первичный импорт из <span className="mono">configs/main.env</span> (секреты — вручную в
          таблице ниже); правка переменных — по группам (<span className="mono">stack_params</span>).
          Для смены секрета введите новое значение в строке, не вставляйте{" "}
          <span className="mono">***</span>. Незаполненные обязательные параметры подсвечены{" "}
          <span style={{ color: "var(--color-danger)", fontWeight: 600 }}>красным</span> — без них
          соответствующие задачи (запуск мониторинга, прокси, LLM-слотов) завершатся ошибкой
          «missing keys for &lt;scope&gt;».
        </p>

        <Section
          title="Импорт из файлов"
          subtitle="Читает только `configs/main.env`, затем импортирует пресеты из `data/presets/*.env` в таблицу БД. Повтор без force вернёт 409."
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
              {installCfg.isPending ? "Импорт…" : "Импортировать из configs/main.env"}
            </button>
          </div>
        </Section>

        <Section
          title="Параметры окружения"
          subtitle="Группы по назначению. Колонка «Описание» — назначение и сценарии (где параметр обязателен). Удаление строки — удаление ключа из БД."
        >
          {appStack.isLoading ? (
            <div className="empty-state">Загружаем…</div>
          ) : (
            <form className="flex flex--col flex--gap-md" onSubmit={onSaveStack}>
              {STACK_GROUP_ORDER.map((gid) => {
                const rowsInGroup = stackRows.filter((r) => stackGroupId(r, regByKey) === gid);
                const meta = STACK_GROUP_META[gid];
                const showEmptyOther = gid === "other";
                if (rowsInGroup.length === 0 && !showEmptyOther) return null;

                const missingInGroup = rowsInGroup.filter((r) =>
                  isMissingRequired(regByKey.get(r.key.trim()), r.value, r.secretSet),
                ).length;

                return (
                  <div key={gid} className="settings-stack-subgroup">
                    <h3 className="settings-stack-subgroup__title">
                      {meta.title}
                      {missingInGroup > 0 ? (
                        <span
                          className="settings-stack-subgroup__missing-badge"
                          title="Сколько обязательных параметров в этой группе не заполнено"
                        >
                          незаполнено: {missingInGroup}
                        </span>
                      ) : null}
                    </h3>
                    <p className="settings-stack-subgroup__lead">{meta.subtitle}</p>
                    {gid === "other" ? (
                      <div className="flex flex--gap-sm flex--wrap" style={{ marginBottom: 12 }}>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() =>
                            setStackRows((prev) => [
                              ...prev,
                              {
                                id: newRowId(),
                                key: "",
                                value: "",
                                isSecret: false,
                                fromRegistry: false,
                                secretSet: false,
                              },
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
                        className="table table--compact settings-stack-table"
                        style={{ width: "100%", minWidth: "720px" }}
                      >
                        <colgroup>
                          <col style={{ width: "22%" }} />
                          <col style={{ width: "26%" }} />
                          <col style={{ width: "44%" }} />
                          <col style={{ width: "4%" }} />
                          <col style={{ width: "4%" }} />
                        </colgroup>
                        <thead>
                          <tr>
                            <th>Ключ</th>
                            <th>Значение</th>
                            <th>Описание / для чего</th>
                            <th>Секрет</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {rowsInGroup.map((row) => {
                            const km = regByKey.get(row.key.trim());
                            const missingRequired = isMissingRequired(km, row.value, row.secretSet);
                            const queryHighlight =
                              row.key && missingHighlight.has(row.key);
                            const rowClass = [
                              missingRequired ? "settings-stack-row--missing-required" : "",
                              queryHighlight ? "settings-stack-row--missing" : "",
                            ]
                              .filter(Boolean)
                              .join(" ");
                            const secretValuePlaceholder = row.secretSet
                              ? "•••••••• (значение задано в БД — введите новое, чтобы заменить; пусто = не менять)"
                              : missingRequired
                                ? "обязательный — заполните секрет"
                                : "новое значение (пусто = не менять)";
                            return (
                              <tr key={row.id} className={rowClass || undefined}>
                                <td>
                                  <input
                                    className={`input ${
                                      missingRequired ? "input--missing" : ""
                                    }`}
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
                                    disabled={patchStack.isPending || row.fromRegistry}
                                    title={
                                      row.fromRegistry
                                        ? "Ключ из реестра — переименование запрещено."
                                        : undefined
                                    }
                                  />
                                </td>
                                <td>
                                  <input
                                    className={`input ${
                                      missingRequired ? "input--missing" : ""
                                    }`}
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
                                      row.isSecret
                                        ? secretValuePlaceholder
                                        : missingRequired
                                          ? "обязательный — заполните"
                                          : ""
                                    }
                                    disabled={patchStack.isPending}
                                    type={row.isSecret ? "password" : "text"}
                                    autoComplete="off"
                                    title={
                                      row.isSecret && row.secretSet
                                        ? "Секрет уже сохранён в БД (значение скрыто). Оставьте поле пустым, чтобы не менять."
                                        : undefined
                                    }
                                  />
                                </td>
                                <td className="settings-stack-desc">
                                  {km ? (
                                    <>
                                      <div>{km.description}</div>
                                      {km.required_for.length > 0 ? (
                                        <div className="settings-stack-desc__scopes">
                                          обязателен для:{" "}
                                          {km.required_for
                                            .map(formatScopeLabel)
                                            .map((s, i, arr) => (
                                              <span key={s}>
                                                {s}
                                                {i < arr.length - 1 ? ", " : ""}
                                              </span>
                                            ))}
                                        </div>
                                      ) : km.allow_empty ? (
                                        <div className="settings-stack-desc__scopes">
                                          опциональный (allow_empty)
                                        </div>
                                      ) : null}
                                      {row.isSecret ? (
                                        <div
                                          className={`settings-stack-desc__secret ${
                                            row.secretSet
                                              ? "settings-stack-desc__secret--set"
                                              : "settings-stack-desc__secret--unset"
                                          }`}
                                        >
                                          {row.secretSet
                                            ? "секрет: значение задано в БД (скрыто)"
                                            : "секрет: значение в БД не задано"}
                                        </div>
                                      ) : null}
                                    </>
                                  ) : (
                                    <>
                                      <div className="settings-stack-desc__scopes">
                                        пользовательский ключ — описание не задано
                                      </div>
                                      {row.isSecret ? (
                                        <div
                                          className={`settings-stack-desc__secret ${
                                            row.secretSet
                                              ? "settings-stack-desc__secret--set"
                                              : "settings-stack-desc__secret--unset"
                                          }`}
                                        >
                                          {row.secretSet
                                            ? "секрет: значение задано в БД (скрыто)"
                                            : "секрет: значение в БД не задано"}
                                        </div>
                                      ) : null}
                                    </>
                                  )}
                                </td>
                                <td style={{ width: "1%" }}>
                                  <input
                                    type="checkbox"
                                    checked={row.isSecret}
                                    onChange={(e) =>
                                      setStackRows((prev) =>
                                        prev.map((r) =>
                                          r.id === row.id
                                            ? {
                                                ...r,
                                                isSecret: e.target.checked,
                                                // Ручная смена флага сбрасывает признак «уже задан в БД»:
                                                // пользователь должен сохранить, чтобы серверная маска
                                                // обновилась.
                                                secretSet: false,
                                              }
                                            : r,
                                        ),
                                      )
                                    }
                                    disabled={patchStack.isPending || row.fromRegistry}
                                    title={
                                      row.fromRegistry
                                        ? "Тип ключа определён реестром."
                                        : "Секрет: значение не возвращается из API"
                                    }
                                  />
                                </td>
                                <td style={{ width: "1%" }}>
                                  <button
                                    type="button"
                                    className="btn btn--ghost"
                                    disabled={patchStack.isPending || row.fromRegistry}
                                    onClick={() =>
                                      setStackRows((prev) => prev.filter((r) => r.id !== row.id))
                                    }
                                    title={
                                      row.fromRegistry
                                        ? "Ключ из реестра нельзя удалить — оставьте пустым."
                                        : "Удалить ключ из БД"
                                    }
                                  >
                                    Удалить
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
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
