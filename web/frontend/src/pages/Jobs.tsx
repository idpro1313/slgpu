import { useCallback, useState, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { ActivityEntry, Job } from "@/api/types";
import { formatDate } from "@/components/formatters";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";
import { saveTextFile } from "@/lib/saveDownload";

type SelectedJob = { source: "job"; id: number };
type SelectedUi = { source: "ui"; entry: ActivityEntry & { type: "ui" } };
type Selection = SelectedJob | SelectedUi | null;

export function JobsPage() {
  const [selected, setSelected] = useState<Selection>(null);
  const [exportActivityBusy, setExportActivityBusy] = useState(false);

  const activity = useQuery({
    queryKey: ["activity"],
    queryFn: ({ signal }) => api.get<ActivityEntry[]>("/activity", { signal }),
    refetchInterval: 5_000,
  });

  const jobDetail = useQuery({
    queryKey: ["jobs", selected?.source === "job" ? selected.id : null],
    queryFn: ({ signal }) => api.get<Job>(`/jobs/${(selected as SelectedJob).id}`, { signal }),
    enabled: selected?.source === "job",
    refetchInterval: (query) => {
      const st = query.state.data?.status;
      return st === "running" || st === "queued" ? 2_000 : 6_000;
    },
  });

  function activateRow(next: Selection) {
    setSelected(next);
  }

  function rowKeyActivate(e: KeyboardEvent, next: Selection) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activateRow(next);
    }
  }

  const modalOpen = selected !== null;
  const modalTitle =
    selected?.source === "job"
      ? `Задача #${selected.id}`
      : selected?.source === "ui"
        ? `Действие UI #${selected.entry.audit_id}`
        : "";
  const modalSubtitle =
    selected?.source === "job"
      ? (jobDetail.data?.message ?? "Команда и логи.")
      : selected?.source === "ui"
        ? (selected.entry.note ?? selected.entry.action)
        : null;

  const exportActivityToFile = useCallback(async () => {
    setExportActivityBusy(true);
    try {
      const items = await api.get<ActivityEntry[]>("/activity?limit=500");
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      saveTextFile(
        `slgpu-activity-${stamp}.json`,
        JSON.stringify(
          {
            exported_at: new Date().toISOString(),
            limit_requested: 500,
            note:
              "До 500 последних записей объединённой ленты (jobs + UI audit).",
            item_count: items.length,
            items,
          },
          null,
          2,
        ),
      );
    } finally {
      setExportActivityBusy(false);
    }
  }, []);

  const saveSelectedJobToFile = useCallback((job: Job) => {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    saveTextFile(
      `slgpu-job-${job.id}-${stamp}.json`,
      JSON.stringify(
        {
          exported_at: new Date().toISOString(),
          note:
            "stdout_tail / stderr_tail — хвост из БД, как на экране задачи.",
          job,
        },
        null,
        2,
      ),
    );
  }, []);

  return (
    <>
      <PageHeader
        title="Задачи"
        subtitle="Фоновые native-задачи (слоты, pull, мониторинг, бенчи) и действия в UI (модели, пресеты, настройки). Для running/queued лог в модалке подтягивается каждые ~2 с (docker pull / вывод). По строке или Enter/Space — подробности; Esc или фон — закрыть."
      />

      <Section
        title="История"
        subtitle="На экране до 100 последних записей; автообновление каждые 5 с. «Сохранить ленту в файл» — до 500 записей в JSON (то же объединение jobs + UI)."
        actions={
          <button
            type="button"
            className="btn"
            disabled={exportActivityBusy || activity.isLoading}
            onClick={() => void exportActivityToFile()}
          >
            {exportActivityBusy ? "Готовим…" : "Сохранить ленту в файл"}
          </button>
        }
      >
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
                        role="button"
                        tabIndex={0}
                        onClick={() => activateRow({ source: "job", id: j.id })}
                        onKeyDown={(e) =>
                          rowKeyActivate(e, { source: "job", id: j.id })
                        }
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
                      role="button"
                      tabIndex={0}
                      onClick={() => activateRow({ source: "ui", entry: row })}
                      onKeyDown={(e) => rowKeyActivate(e, { source: "ui", entry: row })}
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

      <Modal
        isOpen={modalOpen}
        onClose={() => setSelected(null)}
        title={modalTitle}
        subtitle={modalSubtitle}
        actions={
          selected?.source === "job" && jobDetail.data ? (
            <button
              type="button"
              className="btn"
              onClick={() => {
                const j = jobDetail.data;
                if (j) saveSelectedJobToFile(j);
              }}
            >
              Сохранить задачу в файл
            </button>
          ) : null
        }
      >
        {selected?.source === "job" ? (
          jobDetail.isLoading || !jobDetail.data ? (
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
          )
        ) : selected?.source === "ui" ? (
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
        ) : null}
      </Modal>
    </>
  );
}
