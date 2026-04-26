import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Job, JobAccepted, Preset, RuntimeLogs, RuntimeSnapshot } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

export function RuntimePage() {
  const queryClient = useQueryClient();
  const [engine, setEngine] = useState<"vllm" | "sglang">("vllm");
  const [presetName, setPresetName] = useState<string>("");
  const [port, setPort] = useState<string>("");
  const [tp, setTp] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const presets = useQuery({
    queryKey: ["presets"],
    queryFn: () => api.get<Preset[]>("/presets"),
  });
  const snapshot = useQuery({
    queryKey: ["runtime-snapshot"],
    queryFn: () => api.get<RuntimeSnapshot>("/runtime/snapshot"),
    refetchInterval: 8_000,
  });
  const logs = useQuery({
    queryKey: ["runtime-logs"],
    queryFn: () => api.get<RuntimeLogs>("/runtime/logs?tail=400"),
    refetchInterval: 5_000,
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.get<Job[]>("/jobs"),
    refetchInterval: 2_000,
  });

  const upMutation = useMutation({
    mutationFn: () =>
      api.post<JobAccepted>("/runtime/up", {
        engine,
        preset: presetName,
        port: port ? Number(port) : null,
        tp: tp ? Number(tp) : null,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-logs"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const restartMutation = useMutation({
    mutationFn: () =>
      api.post<JobAccepted>("/runtime/restart", {
        preset: presetName,
        tp: tp ? Number(tp) : null,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-logs"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const downMutation = useMutation({
    mutationFn: (includeMonitoring: boolean) =>
      api.post<JobAccepted>("/runtime/down", { include_monitoring: includeMonitoring }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-logs"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const snap = snapshot.data;
  const activeEngineJob = jobs.data?.find(
    (job) => job.scope === "engine" && (job.status === "queued" || job.status === "running"),
  );
  const submittingCommand = upMutation.isPending || restartMutation.isPending || downMutation.isPending;
  const runtimeBusy = Boolean(activeEngineJob) || submittingCommand;

  return (
    <>
      <PageHeader
        title="Inference Runtime"
        subtitle="Запуск, перезапуск и остановка vLLM/SGLang. Сами действия делает ./slgpu CLI, а статусы читаются из Docker."
      />

      {runtimeBusy ? (
        <Section
          title="Команда выполняется"
          subtitle="До завершения текущей операции запуск, рестарт и остановка заблокированы."
        >
          {activeEngineJob ? (
            <div className="status-card">
              <div className="status-card__head">
                <span className="status-card__name">
                  #{activeEngineJob.id} {activeEngineJob.kind}
                </span>
                <StatusBadge status={activeEngineJob.status} />
              </div>
              <div className="status-card__detail mono">
                {activeEngineJob.message ?? activeEngineJob.command.join(" ")}
              </div>
              <div className="status-card__detail">
                Подробный stdout/stderr tail доступен на вкладке «Задачи».
              </div>
            </div>
          ) : (
            <div className="empty-state">Отправляем команду в job runner…</div>
          )}
        </Section>
      ) : null}

      <Section
        title="Текущий снимок"
        subtitle="Контейнер выбирается автоматически: первым берётся работающий vllm, затем sglang."
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => snapshot.refetch()}
            disabled={snapshot.isFetching}
          >
            Обновить
          </button>
        }
      >
        <div className="cards-grid">
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">Engine</span>
              <StatusBadge
                status={snap?.container_status ?? "unknown"}
                label={snap?.engine ?? "—"}
              />
            </div>
            <div className="status-card__detail mono">
              port: {snap?.api_port ?? "—"}
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">Запрошенный пресет</span>
            </div>
            <div className="status-card__detail mono">
              {snap?.preset_name ?? "—"}
              {snap?.tp ? ` • TP ${snap.tp}` : ""}
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">Модель пресета</span>
            </div>
            <div className="status-card__detail mono">{snap?.hf_id ?? "—"}</div>
          </div>
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">/metrics</span>
              <StatusBadge
                status={snap?.metrics_available ? "healthy" : "down"}
                label={snap?.metrics_available ? "ok" : "нет"}
              />
            </div>
            <div className="status-card__detail">
              Доступность Prometheus-ручки vLLM/SGLang
            </div>
          </div>
          <div className="status-card">
            <div className="status-card__head">
              <span className="status-card__name">Served models</span>
            </div>
            <div className="status-card__detail mono">
              {snap?.served_models?.length
                ? snap.served_models.join(", ")
                : "—"}
            </div>
          </div>
        </div>
      </Section>

      <Section
        title="Запуск"
        subtitle="Команды проходят валидацию до shell. Конфликтующий запуск возвращает 409."
      >
        <div className="form-grid">
          <div>
            <label className="label">Движок</label>
            <select
              className="select"
              value={engine}
              onChange={(event) => setEngine(event.target.value as "vllm" | "sglang")}
            >
              <option value="vllm">vLLM</option>
              <option value="sglang">SGLang</option>
            </select>
          </div>
          <div>
            <label className="label">Пресет</label>
            <select
              className="select"
              value={presetName}
              onChange={(event) => setPresetName(event.target.value)}
            >
              <option value="">— выберите —</option>
              {presets.data?.map((preset) => (
                <option value={preset.name} key={preset.id}>
                  {preset.name} ({preset.hf_id})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Порт API (опц.)</label>
            <input
              className="input"
              type="number"
              value={port}
              onChange={(event) => setPort(event.target.value)}
            />
          </div>
          <div>
            <label className="label">TP override (опц.)</label>
            <input
              className="input"
              type="number"
              value={tp}
              onChange={(event) => setTp(event.target.value)}
            />
          </div>
        </div>
        <div className="flex flex--gap-sm flex--wrap" style={{ marginTop: 16 }}>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!presetName || runtimeBusy}
            onClick={() => upMutation.mutate()}
          >
            {upMutation.isPending ? "Запускаем…" : "slgpu up"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={!presetName || runtimeBusy}
            onClick={() => restartMutation.mutate()}
          >
            slgpu restart
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => downMutation.mutate(false)}
            disabled={runtimeBusy}
          >
            slgpu down
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => downMutation.mutate(true)}
            disabled={runtimeBusy}
          >
            slgpu down --all
          </button>
        </div>
        {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}
      </Section>

      <Section
        title="Лог контейнера модели"
        subtitle="Хвост stdout/stderr текущего контейнера vLLM/SGLang. Обновляется каждые 5 секунд."
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => logs.refetch()}
            disabled={logs.isFetching}
          >
            Обновить лог
          </button>
        }
      >
        <p className="section__subtitle">
          Контейнер:{" "}
          <span className="mono">{logs.data?.container_name ?? "не найден"}</span>
          {logs.data?.engine ? ` • ${logs.data.engine}` : ""}
          {logs.data?.container_status ? ` • ${logs.data.container_status}` : ""}
          {logs.data?.tail ? ` • tail ${logs.data.tail}` : ""}
        </p>
        <pre className="code-block" style={{ maxHeight: 520, overflow: "auto" }}>
          {logs.isLoading
            ? "Загружаем лог…"
            : logs.data?.logs?.trim()
              ? logs.data.logs
              : "Лог пуст или контейнер vLLM/SGLang не найден."}
        </pre>
      </Section>
    </>
  );
}
