import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { AppLogsTail } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

const TAIL_CHOICES = [200, 400, 800, 1500, 3000, 5000, 10_000, 20_000] as const;

function formatLine(ln: string): string {
  try {
    const o = JSON.parse(ln) as unknown;
    return JSON.stringify(o, null, 2);
  } catch {
    return ln;
  }
}

export function AppLogsPage() {
  const [tail, setTail] = useState<number>(1500);
  const [raw, setRaw] = useState(false);

  const q = useQuery({
    queryKey: ["app-logs-tail", tail],
    queryFn: ({ signal }) =>
      api.get<AppLogsTail>(`/app-logs/tail?tail=${tail}`, { signal }),
    refetchInterval: 4_000,
  });

  const text = useMemo(() => {
    const lines = q.data?.lines ?? [];
    if (raw) return lines.join("\n");
    return lines.map(formatLine).join("\n\n");
  }, [q.data?.lines, raw]);

  return (
    <div>
      <PageHeader
        title="Логи"
        subtitle="JSON-журнал backend (как в stdout контейнера slgpu-web): HTTP-запросы, уровни логгеров, traceback при ошибках. Файл: WEB_DATA_DIR/.slgpu/app.log"
      />
      <Section
        title="События приложения"
        subtitle={
          q.data?.read_error
            ? `Предупреждение: ${q.data.read_error}`
            : "Автообновление каждые 4 с. Статические /assets/ и /healthz не пишутся в access middleware (шум снижен)."
        }
        actions={
          <div
            className="flex flex--gap-sm flex--wrap"
            style={{ alignItems: "center" }}
          >
            <label className="label" style={{ margin: 0 }} htmlFor="applog-tail">
              Строк, с конца
            </label>
            <select
              id="applog-tail"
              className="select"
              value={tail}
              onChange={(e) => setTail(Number(e.target.value))}
            >
              {TAIL_CHOICES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <label
              className="label"
              style={{ margin: 0, display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <input
                type="checkbox"
                checked={raw}
                onChange={(e) => setRaw(e.target.checked)}
                aria-label="Сырой JSON одной строкой"
              />
              сырой JSON
            </label>
            <button
              type="button"
              className="btn"
              onClick={() => void q.refetch()}
              disabled={q.isFetching}
            >
              Обновить
            </button>
          </div>
        }
      >
        {q.data?.path_hint ? (
          <p className="section__subtitle mono" style={{ marginTop: 0 }}>
            {q.data.path_hint}
            {q.data.file_size_bytes != null
              ? ` — ${q.data.file_size_bytes} B`
              : null}
            {q.data.truncated_scan ? " (прочитан хвост файла)" : null}
          </p>
        ) : null}
        <pre
          className="code-block"
          style={{ maxHeight: "min(70vh, 900px)", overflow: "auto" }}
          tabIndex={0}
          role="log"
          aria-label="Лог событий приложения"
        >
          {q.isLoading
            ? "Загружаем…"
            : q.isError
              ? `Ошибка: ${q.error instanceof Error ? q.error.message : "unknown"}`
              : text.trim() || (q.isSuccess ? "(пусто — лог-файл ещё не создан или 0 байт)" : "—")}
        </pre>
      </Section>
    </div>
  );
}
