import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { api } from "@/api/client";
import type {
  LogExportAccepted,
  LogExportOut,
  LogReportAccepted,
  LogReportLlmCatalogSource,
  LogReportOut,
} from "@/api/types";
import { saveBlobToClient } from "@/lib/saveDownload";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

function toIsoUtc(d: Date): string {
  return d.toISOString();
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toDatetimeLocalValue(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(
    d.getHours(),
  )}:${pad2(d.getMinutes())}`;
}

function presetRange(preset: "15m" | "1h" | "24h"): [Date, Date] {
  const to = new Date();
  const from = new Date(to);
  if (preset === "15m") from.setMinutes(from.getMinutes() - 15);
  else if (preset === "1h") from.setHours(from.getHours() - 1);
  else from.setHours(from.getHours() - 24);
  return [from, to];
}

export function LogReportsPage() {
  const queryClient = useQueryClient();
  const [preset, setPreset] = useState<"15m" | "1h" | "24h" | "custom">("1h");
  const [scope, setScope] = useState<"slgpu" | "all" | "custom">("slgpu");
  const [logqlCustom, setLogqlCustom] = useState(
    '{job="docker-logs", container=~"slgpu-.*"}',
  );
  const [llmModel, setLlmModel] = useState("");
  const [maxLines, setMaxLines] = useState(8000);
  const [reportId, setReportId] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const [exportScope, setExportScope] = useState<"slgpu" | "all" | "custom">(
    "slgpu",
  );
  const [exportLogql, setExportLogql] = useState(
    '{job="docker-logs", container=~"slgpu-.*"}',
  );
  const [exportRedact, setExportRedact] = useState(true);
  const [exportContainer, setExportContainer] = useState("");
  const [exportComposeService, setExportComposeService] = useState("");
  const [exportComposeProject, setExportComposeProject] = useState("");
  const [exportSlot, setExportSlot] = useState("");
  const [exportEngine, setExportEngine] = useState("");
  const [exportPreset, setExportPreset] = useState("");
  const [exportRunId, setExportRunId] = useState("");
  const [exportId, setExportId] = useState<number | null>(null);
  const [exportFormError, setExportFormError] = useState<string | null>(null);

  const [rangeFromCustom, setRangeFromCustom] = useState("");
  const [rangeToCustom, setRangeToCustom] = useState("");

  const catalogSourceQ = useQuery({
    queryKey: ["log-reports", "llm-catalog-source"],
    queryFn: ({ signal }) =>
      api.get<LogReportLlmCatalogSource>("/log-reports/llm-catalog-source", {
        signal,
      }),
    staleTime: 60_000,
  });

  const useLitellmModelCatalog =
    catalogSourceQ.data?.use_litellm_model_catalog ?? true;

  const modelsQ = useQuery({
    queryKey: ["litellm", "models"],
    queryFn: ({ signal }) =>
      api.get<Array<{ id?: string }>>("/litellm/models", { signal }),
    refetchInterval: 60_000,
    enabled: useLitellmModelCatalog,
  });

  const modelOptions = useMemo(() => {
    const ids = modelsQ.data
      ?.map((x) => x?.id?.trim?.())
      .filter((x): x is string => !!x?.length)
      ?? [];
    return Array.from(new Set(ids)).sort((a, b) => a.localeCompare(b));
  }, [modelsQ.data]);

  useEffect(() => {
    if (!useLitellmModelCatalog) return;
    if (!llmModel && modelOptions.length) {
      const first = modelOptions[0];
      if (first) setLlmModel(first);
    }
  }, [useLitellmModelCatalog, llmModel, modelOptions]);

  const fillCustomRangeFromPreset = (rangePreset: "15m" | "1h" | "24h" = "1h") => {
    const [from, to] = presetRange(rangePreset);
    setRangeFromCustom(toDatetimeLocalValue(from));
    setRangeToCustom(toDatetimeLocalValue(to));
  };

  const handlePresetChange = (next: "15m" | "1h" | "24h" | "custom") => {
    setPreset(next);
    if (next === "custom" && (!rangeFromCustom || !rangeToCustom)) {
      fillCustomRangeFromPreset("1h");
    }
  };

  const listQ = useQuery({
    queryKey: ["log-reports", "list"],
    queryFn: ({ signal }) =>
      api.get<{ items: LogReportOut[] }>("/log-reports?limit=15", { signal }),
    refetchInterval: 12_000,
  });

  const activeReportQ = useQuery({
    queryKey: ["log-reports", "one", reportId],
    queryFn: ({ signal }) =>
      api.get<LogReportOut>(`/log-reports/${reportId}`, { signal }),
    enabled: reportId != null,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "pending" || s === "running" ? 2_000 : false;
    },
  });

  const exportsListQ = useQuery({
    queryKey: ["log-exports", "list"],
    queryFn: ({ signal }) =>
      api.get<{ items: LogExportOut[] }>("/log-exports?limit=20", { signal }),
    refetchInterval: 10_000,
  });

  const activeExportQ = useQuery({
    queryKey: ["log-exports", "one", exportId],
    queryFn: ({ signal }) =>
      api.get<LogExportOut>(`/log-exports/${exportId}`, { signal }),
    enabled: exportId != null,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "pending" || s === "running" ? 2_000 : false;
    },
  });

  const createMut = useMutation({
    mutationFn: async () => {
      let from: Date;
      let to: Date;
      if (preset === "custom") {
        if (!rangeFromCustom.trim() || !rangeToCustom.trim()) {
          throw new Error("Укажите начало и конец интервала (ISO или datetime-local).");
        }
        from = new Date(rangeFromCustom);
        to = new Date(rangeToCustom);
        if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
          throw new Error("Некорректные даты.");
        }
      } else {
        [from, to] = presetRange(preset);
      }
      const body: Record<string, unknown> = {
        time_from: toIsoUtc(from),
        time_to: toIsoUtc(to),
        scope,
        llm_model: llmModel.trim(),
        max_lines: maxLines,
      };
      if (scope === "custom") {
        body.logql = logqlCustom.trim();
      }
      return api.post<LogReportAccepted>("/log-reports", body);
    },
    onSuccess: (data) => {
      setFormError(null);
      setReportId(data.report_id);
      void queryClient.invalidateQueries({ queryKey: ["log-reports"] });
    },
    onError: (err: Error) => {
      if (err instanceof ApiError) {
        setFormError(err.message);
        return;
      }
      setFormError(err.message);
    },
  });

  const createExportMut = useMutation({
    mutationFn: async () => {
      let from: Date;
      let to: Date;
      if (preset === "custom") {
        if (!rangeFromCustom.trim() || !rangeToCustom.trim()) {
          throw new Error("Укажите начало и конец интервала.");
        }
        from = new Date(rangeFromCustom);
        to = new Date(rangeToCustom);
        if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
          throw new Error("Некорректные даты.");
        }
      } else {
        [from, to] = presetRange(preset);
      }
      const body: Record<string, unknown> = {
        time_from: toIsoUtc(from),
        time_to: toIsoUtc(to),
        scope: exportScope,
        redact_secrets: exportRedact,
      };
      if (exportScope === "custom") {
        body.logql = exportLogql.trim();
      }
      const trim = (s: string) => s.trim() || undefined;
      const c = trim(exportContainer);
      const cs = trim(exportComposeService);
      const cp = trim(exportComposeProject);
      const sl = trim(exportSlot);
      const en = trim(exportEngine);
      const pr = trim(exportPreset);
      const rn = trim(exportRunId);
      if (c) body.container = c;
      if (cs) body.compose_service = cs;
      if (cp) body.compose_project = cp;
      if (sl) body.slgpu_slot = sl;
      if (en) body.slgpu_engine = en;
      if (pr) body.slgpu_preset = pr;
      if (rn) body.slgpu_run_id = rn;

      return api.post<LogExportAccepted>("/log-exports", body);
    },
    onSuccess: (data) => {
      setExportFormError(null);
      setExportId(data.export_id);
      void queryClient.invalidateQueries({ queryKey: ["log-exports"] });
    },
    onError: (err: Error) => {
      if (err instanceof ApiError) {
        setExportFormError(err.message);
        return;
      }
      setExportFormError(err.message);
    },
  });

  const rep = activeReportQ.data;
  const ex = activeExportQ.data;

  return (
    <div>
      <PageHeader
        title="Отчёты логов"
        subtitle="Loki: LLM-отчёт (факты + сводка) и полная выгрузка строк в ndjson.gz без лимита по числу строк (постраничные запросы к Loki). Хвост контейнеров — страница «Docker». Горизонт выгрузки — до retention Loki (в шаблоне мониторинга обычно 120 суток)."
      />

      <Section
        title="Новый отчёт"
        subtitle="Интервал не более 168 ч. Ограничение max_lines — защита от перегруза Loki."
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }}>
              Период
            </label>
            <select
              className="select"
              value={preset}
              onChange={(e) =>
                handlePresetChange(e.target.value as "15m" | "1h" | "24h" | "custom")
              }
            >
              <option value="15m">15 мин</option>
              <option value="1h">1 ч</option>
              <option value="24h">24 ч</option>
              <option value="custom">Свой интервал</option>
            </select>
            <label className="label" style={{ margin: 0 }}>
              scope
            </label>
            <select
              className="select"
              value={scope}
              onChange={(e) =>
                setScope(e.target.value as "slgpu" | "all" | "custom")
              }
            >
              <option value="slgpu">slgpu (контейнеры slgpu-*)</option>
              <option value="all">all (все docker-logs)</option>
              <option value="custom">custom LogQL</option>
            </select>
            <label className="label" style={{ margin: 0 }}>
              max_lines
            </label>
            <input
              className="input"
              type="number"
              min={500}
              max={20_000}
              step={500}
              value={maxLines}
              onChange={(e) => setMaxLines(parseInt(e.target.value, 10) || 8000)}
              style={{ width: 100 }}
            />
            <button
              type="button"
              className="btn btn--primary"
              disabled={createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              Сформировать
            </button>
          </div>
        }
      >
        {preset === "custom" ? (
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "flex-end", marginBottom: 12 }}
          >
            <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
              Начало
              <input
                className="input"
                type="datetime-local"
                value={rangeFromCustom}
                onChange={(e) => setRangeFromCustom(e.target.value)}
                style={{ minWidth: 230 }}
              />
            </label>
            <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
              Конец
              <input
                className="input"
                type="datetime-local"
                value={rangeToCustom}
                onChange={(e) => setRangeToCustom(e.target.value)}
                style={{ minWidth: 230 }}
              />
            </label>
            <button
              type="button"
              className="btn"
              onClick={() => fillCustomRangeFromPreset("1h")}
              style={{ padding: "4px 10px" }}
            >
              Последний час
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => fillCustomRangeFromPreset("24h")}
              style={{ padding: "4px 10px" }}
            >
              Последние 24 ч
            </button>
          </div>
        ) : null}

        {scope === "custom" ? (
          <div style={{ marginBottom: 12 }}>
            <div className="label">LogQL селектор (начинается с {'{'})</div>
            <textarea
              className="input"
              rows={3}
              value={logqlCustom}
              onChange={(e) => setLogqlCustom(e.target.value)}
              style={{ width: "100%", fontFamily: "monospace", fontSize: "0.9em" }}
            />
          </div>
        ) : null}

        <div className="flex flex--gap-sm flex--wrap" style={{ alignItems: "center" }}>
          <label className="label" style={{ margin: 0 }}>
            Модель для сводки
          </label>
          <input
            className="input"
            list={
              useLitellmModelCatalog ? "logreport-model-suggestions" : undefined
            }
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
            placeholder={
              useLitellmModelCatalog
                ? "как в каталоге LiteLLM (/litellm/models)"
                : "вручную под ваш API (Настройки → Отчёты логов, LLM)"
            }
            style={{ minWidth: 220 }}
          />
          {useLitellmModelCatalog ? (
            <datalist id="logreport-model-suggestions">
              {modelOptions.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          ) : (
            <span className="section__subtitle">
              Указан свой базовый URL для отчётов — подсказки из LiteLLM не
              запрашиваются; модель введите вручную (
              <a href="/settings">Настройки</a>
              ).
            </span>
          )}
          {useLitellmModelCatalog && modelsQ.isError ? (
            <span className="section__subtitle">
              список /litellm/models недоступен — введите модель вручную
            </span>
          ) : null}
        </div>

        {formError ? (
          <p className="section__subtitle" style={{ color: "var(--color-danger)" }}>
            {formError}
          </p>
        ) : null}
      </Section>

      <Section
        title="Выгрузка логов в файл"
        subtitle="Интервал времени — тот же, что у «Нового отчёта» (период и поля «Свой интервал»). API: POST /api/v1/log-exports, до ~2880 ч; job web.log_export.generate; файл .ndjson.gz под WEB_DATA_DIR/.slgpu/log-exports/. Promtail добавляет метки slgpu_slot, slgpu_engine, slgpu_preset, slgpu_run_id для слотов."
        actions={
          <button
            type="button"
            className="btn btn--primary"
            disabled={createExportMut.isPending}
            onClick={() => createExportMut.mutate()}
          >
            Запустить выгрузку
          </button>
        }
      >
        <p className="section__subtitle" style={{ marginBottom: 12 }}>
          Период берётся из блока «Новый отчёт» выше (15 мин / 1 ч / 24 ч / свой интервал).
        </p>
        <div
          className="flex flex--gap-sm flex--wrap"
          style={{ alignItems: "center", marginBottom: 12 }}
        >
          <label className="label" style={{ margin: 0 }}>
            scope (экспорт)
          </label>
          <select
            className="select"
            value={exportScope}
            onChange={(e) =>
              setExportScope(e.target.value as "slgpu" | "all" | "custom")
            }
          >
            <option value="slgpu">slgpu</option>
            <option value="all">all</option>
            <option value="custom">custom LogQL</option>
          </select>
          <label className="label" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={exportRedact}
              onChange={(e) => setExportRedact(e.target.checked)}
            />
            Маскировать секреты в строках
          </label>
        </div>
        {exportScope === "custom" ? (
          <div style={{ marginBottom: 12 }}>
            <div className="label">LogQL селектор {'{'}…{'}'}</div>
            <textarea
              className="input"
              rows={3}
              value={exportLogql}
              onChange={(e) => setExportLogql(e.target.value)}
              style={{ width: "100%", fontFamily: "monospace", fontSize: "0.9em" }}
            />
          </div>
        ) : null}
        <div
          className="flex flex--gap-sm flex--wrap"
          style={{ alignItems: "flex-end", marginBottom: 12, gap: 10 }}
        >
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            container
            <input
              className="input"
              value={exportContainer}
              onChange={(e) => setExportContainer(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 140 }}
            />
          </label>
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            compose_service
            <input
              className="input"
              value={exportComposeService}
              onChange={(e) => setExportComposeService(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 120 }}
            />
          </label>
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            compose_project
            <input
              className="input"
              value={exportComposeProject}
              onChange={(e) => setExportComposeProject(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 120 }}
            />
          </label>
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            slgpu_slot
            <input
              className="input"
              value={exportSlot}
              onChange={(e) => setExportSlot(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 100 }}
            />
          </label>
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            slgpu_engine
            <input
              className="input"
              value={exportEngine}
              onChange={(e) => setExportEngine(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 90 }}
            />
          </label>
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            slgpu_preset
            <input
              className="input"
              value={exportPreset}
              onChange={(e) => setExportPreset(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 100 }}
            />
          </label>
          <label className="label" style={{ display: "grid", gap: 4, margin: 0 }}>
            slgpu_run_id
            <input
              className="input"
              value={exportRunId}
              onChange={(e) => setExportRunId(e.target.value)}
              placeholder="опционально"
              style={{ minWidth: 120 }}
            />
          </label>
        </div>
        {exportFormError ? (
          <p className="section__subtitle" style={{ color: "var(--color-danger)" }}>
            {exportFormError}
          </p>
        ) : null}
      </Section>

      {exportId != null ? (
        <Section
          title={`Текущая выгрузка #${exportId}`}
          subtitle={
            ex?.status
              ? `Статус: ${ex.status}${ex.line_count != null ? `, строк: ${ex.line_count}` : ""}`
              : "Загрузка…"
          }
          actions={
            <div className="flex flex--gap-sm flex--wrap">
              <button
                type="button"
                className="btn btn--primary"
                disabled={ex?.status !== "succeeded"}
                onClick={async () => {
                  if (exportId == null) return;
                  try {
                    const dl = await api.download(`/log-exports/${exportId}/download`);
                    saveBlobToClient(
                      dl.blob,
                      dl.filename ?? `log-export-${exportId}.ndjson.gz`,
                    );
                  } catch (e) {
                    if (e instanceof ApiError) {
                      setExportFormError(e.message);
                    }
                  }
                }}
              >
                Скачать .ndjson.gz
              </button>
              <button type="button" className="btn" onClick={() => setExportId(null)}>
                Скрыть
              </button>
            </div>
          }
        >
          {activeExportQ.isLoading ? (
            <div className="empty-state">Загружаем…</div>
          ) : activeExportQ.isError ? (
            <div className="empty-state">
              Ошибка:{" "}
              {activeExportQ.error instanceof Error
                ? activeExportQ.error.message
                : "unknown"}
            </div>
          ) : (
            <>
              {ex?.retention_note ? (
                <p className="section__subtitle">{ex.retention_note}</p>
              ) : null}
              {ex?.logql ? (
                <pre
                  className="code-block"
                  style={{ maxHeight: 120, overflow: "auto", fontSize: "0.85em" }}
                >
                  {ex.logql}
                </pre>
              ) : null}
              {ex?.error_message ? (
                <pre className="code-block" style={{ maxHeight: 160, overflow: "auto" }}>
                  {ex.error_message}
                </pre>
              ) : null}
            </>
          )}
        </Section>
      ) : null}

      {reportId != null ? (
        <Section
          title={`Текущий отчёт #${reportId}`}
          subtitle={rep?.status ? `Статус: ${rep.status}` : "Загрузка…"}
          actions={
            <button type="button" className="btn" onClick={() => setReportId(null)}>
              Скрыть карточку
            </button>
          }
        >
          {activeReportQ.isLoading ? (
            <div className="empty-state">Загружаем…</div>
          ) : activeReportQ.isError ? (
            <div className="empty-state">
              Ошибка:{" "}
              {activeReportQ.error instanceof Error
                ? activeReportQ.error.message
                : "unknown"}
            </div>
          ) : (
            <>
              {rep?.error_message ? (
                <pre className="code-block" style={{ maxHeight: 200, overflow: "auto" }}>
                  {rep.error_message}
                </pre>
              ) : null}
              {rep?.llm_markdown ? (
                <>
                  <div className="label">Сводка (Markdown)</div>
                  <pre
                    className="code-block"
                    style={{ maxHeight: 420, overflow: "auto", whiteSpace: "pre-wrap" }}
                  >
                    {rep.llm_markdown}
                  </pre>
                </>
              ) : null}
              {!rep?.llm_markdown &&
              rep?.status !== "failed" &&
              (rep?.status === "pending" || rep?.status === "running") ? (
                <p className="section__subtitle">Ждём Loki и LLM-сводку (или локальный fallback)…</p>
              ) : null}
              {rep?.facts ? (
                <>
                  <div className="label">Факты (JSON для модели)</div>
                  <pre
                    className="code-block"
                    style={{ maxHeight: 320, overflow: "auto", fontSize: "0.85em" }}
                  >
                    {JSON.stringify(rep.facts, null, 2)}
                  </pre>
                </>
              ) : null}
            </>
          )}
        </Section>
      ) : null}

      <Section title="Последние отчёты" subtitle="GET /api/v1/log-reports?limit=15">
        {listQ.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>id</th>
                  <th>status</th>
                  <th>job</th>
                  <th>интервал (UTC)</th>
                  <th>scope</th>
                  <th>модель</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(listQ.data?.items ?? []).map((row) => (
                  <tr key={row.id}>
                    <td className="mono">{row.id}</td>
                    <td>{row.status}</td>
                    <td className="mono">{row.job_id ?? "—"}</td>
                    <td className="mono" style={{ fontSize: "0.85em" }}>
                      {row.time_from.replace("T", " ").replace("+00:00", "Z")} →{" "}
                      {row.time_to.replace("T", " ").replace("+00:00", "Z")}
                    </td>
                    <td>{row.scope}</td>
                    <td className="mono" style={{ maxWidth: 160 }} title={row.llm_model}>
                      {row.llm_model.length > 24
                        ? `${row.llm_model.slice(0, 21)}…`
                        : row.llm_model}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        style={{ padding: "2px 8px" }}
                        onClick={() => setReportId(row.id)}
                      >
                        открыть
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Последние выгрузки" subtitle="GET /api/v1/log-exports?limit=20">
        {exportsListQ.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>id</th>
                  <th>status</th>
                  <th>job</th>
                  <th>строки</th>
                  <th>интервал (UTC)</th>
                  <th>scope</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(exportsListQ.data?.items ?? []).map((row) => (
                  <tr key={row.id}>
                    <td className="mono">{row.id}</td>
                    <td>{row.status}</td>
                    <td className="mono">{row.job_id ?? "—"}</td>
                    <td>{row.line_count ?? "—"}</td>
                    <td className="mono" style={{ fontSize: "0.85em" }}>
                      {row.time_from.replace("T", " ").replace("+00:00", "Z")} →{" "}
                      {row.time_to.replace("T", " ").replace("+00:00", "Z")}
                    </td>
                    <td>{row.scope}</td>
                    <td>
                      <div className="flex flex--gap-sm" style={{ flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn"
                          style={{ padding: "2px 8px" }}
                          onClick={() => setExportId(row.id)}
                        >
                          статус
                        </button>
                        <button
                          type="button"
                          className="btn"
                          style={{ padding: "2px 8px" }}
                          disabled={row.status !== "succeeded"}
                          onClick={async () => {
                            try {
                              const dl = await api.download(`/log-exports/${row.id}/download`);
                              saveBlobToClient(
                                dl.blob,
                                dl.filename ?? `log-export-${row.id}.ndjson.gz`,
                              );
                            } catch (e) {
                              if (e instanceof ApiError) {
                                setExportFormError(e.message);
                              }
                            }
                          }}
                        >
                          скачать
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
