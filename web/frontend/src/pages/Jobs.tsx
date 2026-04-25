import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Job } from "@/api/types";
import { formatDate } from "@/components/formatters";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

export function JobsPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/jobs"),
    refetchInterval: 5_000,
  });

  const detail = useQuery({
    queryKey: ["jobs", selectedId],
    queryFn: () => api.get<Job>(`/jobs/${selectedId}`),
    enabled: selectedId != null,
    refetchInterval: 4_000,
  });

  return (
    <>
      <PageHeader
        title="Задачи"
        subtitle="Журнал всех CLI-операций: pull, up, down, restart, monitoring. По клику виден stdout/stderr tail."
      />

      <Section title="История" subtitle="Сортировка по убыванию id, лимит 50.">
        {jobs.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !jobs.data || jobs.data.length === 0 ? (
          <div className="empty-state">Задач пока нет.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Команда</th>
                  <th>Цель</th>
                  <th>Актор</th>
                  <th>Статус</th>
                  <th>Exit</th>
                  <th>Создано</th>
                  <th>Завершено</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => setSelectedId(job.id)}
                    style={{ cursor: "pointer" }}
                  >
                    <td className="mono">#{job.id}</td>
                    <td className="mono">{job.kind}</td>
                    <td className="mono">{job.resource ?? "—"}</td>
                    <td>{job.actor ?? "—"}</td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td>{job.exit_code ?? "—"}</td>
                    <td>{formatDate(job.created_at)}</td>
                    <td>{formatDate(job.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {selectedId != null ? (
        <Section
          title={`Задача #${selectedId}`}
          subtitle={detail.data?.message ?? "Команда и логи."}
          actions={
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setSelectedId(null)}
            >
              Закрыть
            </button>
          }
        >
          {detail.isLoading || !detail.data ? (
            <div className="empty-state">Загружаем…</div>
          ) : (
            <div className="flex flex--col flex--gap-md">
              <div>
                <div className="label">argv</div>
                <pre className="code-block">{detail.data.command.join(" ")}</pre>
              </div>
              <div>
                <div className="label">stdout (tail)</div>
                <pre className="code-block">{detail.data.stdout_tail ?? "—"}</pre>
              </div>
              <div>
                <div className="label">stderr (tail)</div>
                <pre className="code-block">{detail.data.stderr_tail ?? "—"}</pre>
              </div>
            </div>
          )}
        </Section>
      ) : null}
    </>
  );
}
