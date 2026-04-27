import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  DockerContainerLogs,
  DockerContainersList,
  DockerContainerRow,
} from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

const TAIL_CHOICES = [200, 400, 800, 1500, 3000, 5000] as const;

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
        subtitle="Список контейнеров на хосте (read-only) и tail stdout+stderr. Имя или id; для slgpu-стека — фильтр по префиксу/лейблам. Не путать с «Лог слота» на Inference (там только зарегистрированные слоты)."
      />

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
