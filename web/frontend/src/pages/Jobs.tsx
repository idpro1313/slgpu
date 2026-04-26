import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { ActivityEntry, Job } from "@/api/types";
import { formatDate } from "@/components/formatters";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

type SelectedJob = { source: "job"; id: number };
type SelectedUi = { source: "ui"; entry: ActivityEntry & { type: "ui" } };
type Selection = SelectedJob | SelectedUi | null;

export function JobsPage() {
  const [selected, setSelected] = useState<Selection>(null);

  const activity = useQuery({
    queryKey: ["activity"],
    queryFn: () => api.get<ActivityEntry[]>("/activity"),
    refetchInterval: 5_000,
  });

  const jobDetail = useQuery({
    queryKey: ["jobs", selected?.source === "job" ? selected.id : null],
    queryFn: () => api.get<Job>(`/jobs/${(selected as SelectedJob).id}`),
    enabled: selected?.source === "job",
    refetchInterval: 4_000,
  });

  return (
    <>
      <PageHeader
        title="Задачи"
        subtitle="Фоновые команды (pull, up, down, monitoring) и отдельные действия в UI: модели, пресеты, настройки, синхронизация пресетов. По клику на строку job — лог; для действия UI — краткие детали."
      />

      <Section title="История" subtitle="Объединённая лента по времени, лимит 100.">
        {activity.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !activity.data || activity.data.length === 0 ? (
          <div className="empty-state">Записей пока нет.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>Тип</th>
                  <th>Команда / действие</th>
                  <th>Цель</th>
                  <th>Актор</th>
                  <th>Статус</th>
                  <th>Exit</th>
                  <th>Время</th>
                </tr>
              </thead>
              <tbody>
                {activity.data.map((row) => {
                  if (row.type === "job") {
                    const j = row.job;
                    return (
                      <tr
                        key={`job-${j.id}`}
                        onClick={() => setSelected({ source: "job", id: j.id })}
                        style={{ cursor: "pointer" }}
                      >
                        <td>CLI</td>
                        <td className="mono">{j.kind}</td>
                        <td className="mono">{j.resource ?? "—"}</td>
                        <td>{j.actor ?? "—"}</td>
                        <td>
                          <StatusBadge status={j.status} />
                        </td>
                        <td>{j.exit_code ?? "—"}</td>
                        <td>{formatDate(j.created_at)}</td>
                      </tr>
                    );
                  }
                  return (
                    <tr
                      key={`ui-${row.audit_id}`}
                      onClick={() => setSelected({ source: "ui", entry: row })}
                      style={{ cursor: "pointer" }}
                    >
                      <td>UI</td>
                      <td className="mono">{row.action}</td>
                      <td className="mono">{row.target ?? "—"}</td>
                      <td>{row.actor ?? "—"}</td>
                      <td>—</td>
                      <td>—</td>
                      <td>{formatDate(row.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {selected?.source === "job" && selected.id != null ? (
        <Section
          title={`Задача #${selected.id}`}
          subtitle={jobDetail.data?.message ?? "Команда и логи."}
          actions={
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setSelected(null)}
            >
              Закрыть
            </button>
          }
        >
          {jobDetail.isLoading || !jobDetail.data ? (
            <div className="empty-state">Загружаем…</div>
          ) : (
            <div className="flex flex--col flex--gap-md">
              <div>
                <div className="label">argv</div>
                <pre className="code-block">{jobDetail.data.command.join(" ")}</pre>
              </div>
              <div>
                <div className="label">stdout (tail)</div>
                <pre className="code-block">{jobDetail.data.stdout_tail ?? "—"}</pre>
              </div>
              <div>
                <div className="label">stderr (tail)</div>
                <pre className="code-block">{jobDetail.data.stderr_tail ?? "—"}</pre>
              </div>
            </div>
          )}
        </Section>
      ) : null}

      {selected?.source === "ui" ? (
        <Section
          title={`Действие UI #${selected.entry.audit_id}`}
          subtitle={selected.entry.note ?? selected.entry.action}
          actions={
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setSelected(null)}
            >
              Закрыть
            </button>
          }
        >
          <div className="flex flex--col flex--gap-md">
            <div>
              <div className="label">action</div>
              <pre className="code-block">{selected.entry.action}</pre>
            </div>
            <div>
              <div className="label">target</div>
              <pre className="code-block">{selected.entry.target ?? "—"}</pre>
            </div>
            {selected.entry.actor ? (
              <div>
                <div className="label">actor</div>
                <pre className="code-block">{selected.entry.actor}</pre>
              </div>
            ) : null}
            <div>
              <div className="label">payload</div>
              <pre className="code-block">
                {JSON.stringify(selected.entry.payload, null, 2) || "—"}
              </pre>
            </div>
          </div>
        </Section>
      ) : null}
    </>
  );
}
