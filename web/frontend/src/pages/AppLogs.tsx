import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { AppLogEvent, AppLogEventsList } from "@/api/types";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

const LIMIT = 200;
const KIND_OPTIONS = [
  "http_request",
  "http_error",
  "app_lifecycle",
  "app_warning",
  "app_error",
  "dependency",
] as const;

function sinceParam(preset: "5m" | "1h" | "24h" | "all"): string | undefined {
  if (preset === "all") return undefined;
  const t = new Date();
  if (preset === "5m") t.setMinutes(t.getMinutes() - 5);
  else if (preset === "1h") t.setHours(t.getHours() - 1);
  else t.setHours(t.getHours() - 24);
  return t.toISOString();
}

function buildAppLogsUrl(params: {
  level?: string;
  eventKind?: string;
  pathPrefix?: string;
  q?: string;
  since?: string;
  beforeId?: number;
}): string {
  const u = new URLSearchParams();
  u.set("limit", String(LIMIT));
  if (params.level?.trim()) u.set("level", params.level.trim());
  if (params.eventKind?.trim()) u.set("event_kind", params.eventKind.trim());
  if (params.pathPrefix?.trim()) u.set("path_prefix", params.pathPrefix.trim());
  if (params.q?.trim()) u.set("q", params.q.trim());
  if (params.since) u.set("since", params.since);
  if (params.beforeId != null) u.set("before_id", String(params.beforeId));
  return `/app-logs/events?${u.toString()}`;
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n - 1)}…`;
}

export function AppLogsPage() {
  const [level, setLevel] = useState("");
  const [eventKind, setEventKind] = useState("");
  const [pathPrefix, setPathPrefix] = useState("");
  const [q, setQ] = useState("");
  const [timePreset, setTimePreset] = useState<"5m" | "1h" | "24h" | "all">("1h");
  const [older, setOlder] = useState<AppLogEvent[]>([]);
  const [paged, setPaged] = useState(false);
  /** Курсор следующей страницы (после первой — из ответа «ещё»). */
  const [loadCursor, setLoadCursor] = useState<number | null>(null);
  const [detail, setDetail] = useState<AppLogEvent | null>(null);

  const since = useMemo(() => sinceParam(timePreset), [timePreset]);

  const filterKey = [level, eventKind, pathPrefix, q, timePreset].join("|");

  useEffect(() => {
    setOlder([]);
    setPaged(false);
    setLoadCursor(null);
  }, [filterKey]);

  const listQ = useQuery({
    queryKey: ["app-logs-events", level, eventKind, pathPrefix, q, since],
    queryFn: ({ signal }) =>
      api.get<AppLogEventsList>(
        buildAppLogsUrl({
          level: level || undefined,
          eventKind: eventKind || undefined,
          pathPrefix: pathPrefix || undefined,
          q: q || undefined,
          since,
        }),
        { signal },
      ),
    refetchInterval: paged ? false : 4_000,
  });

  const onLoadMore = useCallback(async () => {
    const beforeId = loadCursor ?? listQ.data?.next_before_id;
    if (beforeId == null) return;
    const r = await api.get<AppLogEventsList>(
      buildAppLogsUrl({
        level: level || undefined,
        eventKind: eventKind || undefined,
        pathPrefix: pathPrefix || undefined,
        q: q || undefined,
        since,
        beforeId,
      }),
    );
    setOlder((prev) => [...prev, ...r.items]);
    setLoadCursor(r.next_before_id);
    setPaged(true);
  }, [loadCursor, listQ.data?.next_before_id, level, eventKind, pathPrefix, q, since]);

  const visible = useMemo(() => {
    const first = listQ.data?.items ?? [];
    return [...first, ...older];
  }, [listQ.data?.items, older]);

  const canLoadMore = useMemo(() => {
    if (listQ.isLoading) return false;
    if (older.length === 0) {
      return (listQ.data?.next_before_id ?? null) != null;
    }
    return (loadCursor ?? null) != null;
  }, [listQ.isLoading, listQ.data?.next_before_id, older.length, loadCursor]);

  return (
    <div>
      <PageHeader
        title="Логи"
        subtitle="События slgpu-web в SQLite (app_log_event): HTTP, уровни логгеров, усечённые traceback. Секреты в тело не пишутся. Stdout/опциональный app.log (WEB_LOG_FILE_ENABLED) — для Loki/дебага."
      />
      <Section
        title="События приложения"
        subtitle={
          paged
            ? "Загружены дополнительные страницы — автообновление отключено. Сбросьте пагинацию, изменив фильтр."
            : "Автообновление каждые 4 с. /healthz, /assets, /favicon, /app-logs/events не пишутся в access middleware."
        }
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }} htmlFor="applog-since">
              За период
            </label>
            <select
              id="applog-since"
              className="select"
              value={timePreset}
              onChange={(e) =>
                setTimePreset(e.target.value as "5m" | "1h" | "24h" | "all")
              }
            >
              <option value="5m">5 мин</option>
              <option value="1h">1 ч</option>
              <option value="24h">24 ч</option>
              <option value="all">Всё</option>
            </select>
            <input
              className="input"
              placeholder="Уровни: INFO,WARNING,ERROR"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              style={{ minWidth: 200 }}
              aria-label="Уровни CSV"
            />
            <select
              className="select"
              value={eventKind}
              onChange={(e) => setEventKind(e.target.value)}
              aria-label="Вид события"
            >
              <option value="">Все виды</option>
              {KIND_OPTIONS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
            <input
              className="input"
              placeholder="Префикс пути API"
              value={pathPrefix}
              onChange={(e) => setPathPrefix(e.target.value)}
              style={{ minWidth: 160 }}
            />
            <input
              className="input"
              placeholder="Поиск в message"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ minWidth: 160 }}
            />
            <button
              type="button"
              className="btn"
              onClick={() => void listQ.refetch()}
              disabled={listQ.isFetching}
            >
              Обновить
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => onLoadMore()}
              disabled={!canLoadMore || listQ.isFetching}
            >
              Загрузить ещё
            </button>
          </div>
        }
      >
        {listQ.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : listQ.isError ? (
          <div className="empty-state">
            Ошибка:{" "}
            {listQ.error instanceof Error
              ? listQ.error.message
              : "неизвестно"}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>Время (UTC)</th>
                  <th>level</th>
                  <th>kind</th>
                  <th>logger</th>
                  <th>req</th>
                  <th>path</th>
                  <th>st</th>
                  <th>ms</th>
                  <th>message</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={`${row.id}-${row.created_at}`}>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>
                      {row.created_at.replace("T", " ").replace("+00:00", "Z")}
                    </td>
                    <td>{row.level}</td>
                    <td className="mono" style={{ fontSize: "0.85em" }}>
                      {row.event_kind}
                    </td>
                    <td
                      className="mono"
                      style={{ maxWidth: 140, fontSize: "0.85em" }}
                      title={row.logger_name}
                    >
                      {truncate(row.logger_name, 24)}
                    </td>
                    <td className="mono" style={{ fontSize: "0.8em" }}>
                      {row.request_id
                        ? truncate(row.request_id, 10)
                        : "—"}
                    </td>
                    <td
                      className="mono"
                      style={{ maxWidth: 220, fontSize: "0.85em" }}
                      title={row.http_path ?? ""}
                    >
                      {truncate(
                        (row.http_method ? `${row.http_method} ` : "") +
                          (row.http_path ?? "—"),
                        48,
                      )}
                    </td>
                    <td>{row.status_code ?? "—"}</td>
                    <td>
                      {row.duration_ms != null
                        ? row.duration_ms.toFixed(0)
                        : "—"}
                    </td>
                    <td
                      className="mono"
                      style={{ maxWidth: 320, fontSize: "0.85em" }}
                    >
                      {truncate(row.message, 120)}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        style={{ padding: "2px 8px", fontSize: "0.85em" }}
                        onClick={() => setDetail(row)}
                      >
                        детали
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visible.length === 0 ? (
              <p className="section__subtitle" style={{ marginTop: 8 }}>
                Нет событий по фильтру.
              </p>
            ) : null}
          </div>
        )}
      </Section>

      <Modal
        title="Детали события"
        subtitle={detail ? `id=${detail.id}` : null}
        isOpen={detail != null}
        onClose={() => setDetail(null)}
        size="wide"
      >
        {detail ? (
          <div className="flex flex--gap-md" style={{ flexDirection: "column" }}>
            <pre className="code-block" style={{ maxHeight: 200, overflow: "auto" }}>
              {JSON.stringify(
                {
                  id: detail.id,
                  created_at: detail.created_at,
                  level: detail.level,
                  event_kind: detail.event_kind,
                  logger_name: detail.logger_name,
                  module_anchor: detail.module_anchor,
                  http_method: detail.http_method,
                  http_path: detail.http_path,
                  status_code: detail.status_code,
                  duration_ms: detail.duration_ms,
                  request_id: detail.request_id,
                  correlation_id: detail.correlation_id,
                  message: detail.message,
                  log_extra: detail.log_extra,
                },
                null,
                2,
              )}
            </pre>
            {detail.exc_summary ? (
              <>
                <div className="label">Traceback (усечённо)</div>
                <pre
                  className="code-block"
                  style={{ maxHeight: 360, overflow: "auto" }}
                >
                  {detail.exc_summary}
                </pre>
              </>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
