import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  DockerContainerLogs,
  DockerContainersList,
  DockerContainerRow,
  DockerEngineEvents,
} from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

const TAIL_CHOICES = [200, 400, 800, 1500, 3000, 5000] as const;
const EVENTS_SINCE_CHOICES = [600, 1800, 3600, 7200, 86400] as const;
const EVENTS_LIMIT_CHOICES = [500, 1000, 2000, 5000, 10000] as const;
const DAEMON_LINES_CHOICES = [200, 400, 800, 1500] as const;

function containerLabel(c: DockerContainerRow): string {
  const p = c.compose_service
    ? `${c.compose_service}`
    : c.compose_project
      ? `${c.compose_project}`
      : "—";
  return `${c.name} · ${p}`;
}

export function DockerLogsPage() {
  const [scope, setScope] = useState<"slgpu" | "all">("slgpu");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [tail, setTail] = useState<number>(400);
  const [sinceSec, setSinceSec] = useState<number>(3600);
  const [evLimit, setEvLimit] = useState<number>(2000);
  const [daemonLines, setDaemonLines] = useState<number>(400);
  const [search, setSearch] = useState("");

  const list = useQuery({
    queryKey: ["docker-containers", scope],
    queryFn: ({ signal }) =>
      api.get<DockerContainersList>(`/docker/containers?scope=${scope}`, { signal }),
    refetchInterval: 12_000,
  });

  const selectedRow = useMemo(() => {
    if (!list.data?.containers || !selectedKey) return null;
    return list.data.containers.find((c) => c.id === selectedKey) ?? null;
  }, [list.data, selectedKey]);

  const refForRequest = useMemo(() => {
    if (!selectedRow) return null;
    return selectedRow.name || selectedRow.id;
  }, [selectedRow]);

  const logsQ = useQuery({
    queryKey: ["docker-container-logs", refForRequest, tail],
    queryFn: ({ signal }) =>
      api.get<DockerContainerLogs>(
        `/docker/containers/${encodeURIComponent(refForRequest!)}/logs?tail=${tail}`,
        { signal },
      ),
    enabled: refForRequest != null && (list.data?.docker_available ?? false),
    refetchInterval: refForRequest && list.data?.docker_available ? 4_000 : false,
  });

  const engineQ = useQuery({
    queryKey: ["docker-engine-events", sinceSec, evLimit],
    queryFn: ({ signal }) =>
      api.get<DockerEngineEvents>(
        `/docker/engine-events?since_sec=${sinceSec}&limit=${evLimit}`,
        { signal },
      ),
    refetchInterval: 12_000,
  });

  const daemonQ = useQuery({
    queryKey: ["docker-daemon-log", daemonLines],
    queryFn: ({ signal }) =>
      api.get<DockerDaemonLog>(`/docker/daemon-log?lines=${daemonLines}`, { signal }),
    refetchInterval: 25_000,
  });

  const onPickRow = useCallback(
    (c: DockerContainerRow) => {
      setSelectedKey(c.id);
    },
    [setSelectedKey],
  );

  const filtered = useMemo(() => {
    const rows = list.data?.containers ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.image.toLowerCase().includes(q) ||
        (c.compose_service ?? "").toLowerCase().includes(q) ||
        (c.compose_project ?? "").toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q),
    );
  }, [list.data, search]);

  useEffect(() => {
    if (selectedKey && list.data?.containers?.every((c) => c.id !== selectedKey)) {
      setSelectedKey(null);
    }
  }, [list.data, selectedKey]);

  return (
    <>
      <PageHeader
        title="Docker: логи"
        subtitle="Помимо stdout/stderr контейнеров: события Docker Engine (pull, start, die…) и, при доступности, лог демона dockerd из journald. Read-only, тот же socket, что и для списка. Не путать с «Лог слота» на Inference."
      />

      <Section
        title="События Docker Engine"
        subtitle="API `/events` за окно [now−N … now], последние строки при перегрузе. Тот же `docker.sock`, что и у списка контейнеров."
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }}>
              окно, с
            </label>
            <select
              className="select"
              value={sinceSec}
              onChange={(e) => setSinceSec(parseInt(e.target.value, 10))}
            >
              {EVENTS_SINCE_CHOICES.map((s) => (
                <option value={s} key={s}>
                  {s >= 3600 ? `${s / 3600} ч` : `${s / 60} мин`}
                </option>
              ))}
            </select>
            <label className="label" style={{ margin: 0 }}>
              макс. событий
            </label>
            <select
              className="select"
              value={evLimit}
              onChange={(e) => setEvLimit(parseInt(e.target.value, 10))}
            >
              {EVENTS_LIMIT_CHOICES.map((n) => (
                <option value={n} key={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn"
              onClick={() => engineQ.refetch()}
              disabled={engineQ.isFetching}
            >
              Обновить
            </button>
          </div>
        }
      >
        <pre
          className="code-block"
          style={{ maxHeight: 320, overflow: "auto" }}
        >
          {engineQ.isLoading
            ? "Загружаем…"
            : engineQ.isError
              ? `Ошибка: ${engineQ.error instanceof Error ? engineQ.error.message : "unknown"}`
              : (engineQ.data?.events_text ?? "—").trim() || "—"}
        </pre>
      </Section>

      <Section
        title="Лог демона Docker (dockerd)"
        subtitle="`journalctl -u docker.service` на машине, где крутится web-процесс. В контейнере без journal хоста строк может не быть — смотрите `journalctl` на сервере."
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }}>
              строк
            </label>
            <select
              className="select"
              value={daemonLines}
              onChange={(e) => setDaemonLines(parseInt(e.target.value, 10))}
            >
              {DAEMON_LINES_CHOICES.map((n) => (
                <option value={n} key={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn"
              onClick={() => daemonQ.refetch()}
              disabled={daemonQ.isFetching}
            >
              Обновить
            </button>
          </div>
        }
      >
        {daemonQ.data?.journal_note ? (
          <p className="section__subtitle" style={{ marginTop: 0 }}>
            {daemonQ.data.journal_note}
          </p>
        ) : null}
        <pre
          className="code-block"
          style={{ maxHeight: 320, overflow: "auto" }}
        >
          {daemonQ.isLoading
            ? "Загружаем…"
            : daemonQ.isError
              ? `Ошибка: ${daemonQ.error instanceof Error ? daemonQ.error.message : "unknown"}`
              : (() => {
                const t = (daemonQ.data?.text ?? "").trim();
                if (t) return t;
                if (daemonQ.data && !daemonQ.data.journal_note) return "(пусто)";
                return "—";
              })()}
        </pre>
      </Section>

      <Section
        title="Контейнеры"
        subtitle={
          !list.data?.docker_available
            ? "Docker socket недоступен из web (см. права на /var/run/docker.sock)."
            : scope === "slgpu"
              ? "Только slgpu-стек (имя/compose/лейблы)."
              : "Все контейнеры на хосте — осторожно, список может быть длинным."
        }
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }}>
              Область
            </label>
            <select
              className="select"
              value={scope}
              onChange={(e) => {
                setScope(e.target.value as "slgpu" | "all");
                setSelectedKey(null);
              }}
            >
              <option value="slgpu">slgpu</option>
              <option value="all">все</option>
            </select>
            <input
              className="input"
              placeholder="Поиск…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ minWidth: 180 }}
            />
            <button
              type="button"
              className="btn"
              onClick={() => list.refetch()}
              disabled={list.isFetching}
            >
              Обновить список
            </button>
          </div>
        }
      >
        {list.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !list.data?.docker_available ? (
          <div className="empty-state">Список недоступен (Docker).</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">Нет контейнеров (или ничего не подошло под поиск).</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Образ</th>
                  <th>Статус</th>
                  <th>Compose</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => {
                  const active = c.id === selectedKey;
                  return (
                    <tr
                      key={c.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => onPickRow(c)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onPickRow(c);
                        }
                      }}
                      style={{
                        cursor: "pointer",
                        background: active ? "var(--color-surface-alt)" : undefined,
                      }}
                    >
                      <td className="mono">{c.name}</td>
                      <td className="mono" style={{ maxWidth: 240, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={c.image}>
                        {c.image}
                      </td>
                      <td>{c.status}</td>
                      <td className="mono" style={{ fontSize: "0.9em" }}>
                        {c.compose_project ?? "—"}/{c.compose_service ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section
        title="Лог выбранного контейнера"
        subtitle="Обновляется автоматически каждые 4 с, пока открыта страница; только tail последних строк."
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }}>
              tail
            </label>
            <select
              className="select"
              value={tail}
              onChange={(e) => setTail(parseInt(e.target.value, 10))}
            >
              {TAIL_CHOICES.map((n) => (
                <option value={n} key={n}>
                  {n}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn"
              onClick={() => logsQ.refetch()}
              disabled={!refForRequest || logsQ.isFetching}
            >
              Обновить
            </button>
          </div>
        }
      >
        <p className="section__subtitle">
          {selectedRow && refForRequest ? (
            <>
              <span className="mono">{containerLabel(selectedRow)}</span>
              {logsQ.data?.container_name ? (
                <>
                  {" "}
                  · <span className="mono">{logsQ.data.container_name}</span>
                </>
              ) : null}
            </>
          ) : (
            "Выберите строку в таблице выше."
          )}
        </p>
        <pre
          className="code-block"
          style={{ maxHeight: 480, overflow: "auto" }}
        >
          {!refForRequest
            ? "—"
            : logsQ.isLoading
              ? "Загружаем…"
              : logsQ.isError
                ? `Ошибка: ${logsQ.error instanceof Error ? logsQ.error.message : "unknown"}`
                : logsQ.data?.logs?.trim()
                  ? logsQ.data.logs
                  : "(пусто)"}
        </pre>
      </Section>
    </>
  );
}
