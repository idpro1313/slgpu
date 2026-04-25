import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { JobAccepted, Preset, RuntimeSnapshot } from "@/api/types";
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
    },
    onError: (err: Error) => setError(err.message),
  });

  const restartMutation = useMutation({
    mutationFn: () =>
      api.post<JobAccepted>("/runtime/restart", {
        preset: presetName,
        tp: tp ? Number(tp) : null,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (err: Error) => setError(err.message),
  });

  const downMutation = useMutation({
    mutationFn: (includeMonitoring: boolean) =>
      api.post<JobAccepted>("/runtime/down", { include_monitoring: includeMonitoring }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (err: Error) => setError(err.message),
  });

  const snap = snapshot.data;

  return (
    <>
      <PageHeader
        title="Inference Runtime"
        subtitle="Запуск, перезапуск и остановка vLLM/SGLang. Сами действия делает ./slgpu CLI, а статусы читаются из Docker."
      />

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
            disabled={!presetName || upMutation.isPending}
            onClick={() => upMutation.mutate()}
          >
            {upMutation.isPending ? "Запускаем…" : "slgpu up"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={!presetName || restartMutation.isPending}
            onClick={() => restartMutation.mutate()}
          >
            slgpu restart
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => downMutation.mutate(false)}
            disabled={downMutation.isPending}
          >
            slgpu down
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => downMutation.mutate(true)}
            disabled={downMutation.isPending}
          >
            slgpu down --all
          </button>
        </div>
        {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}
      </Section>
    </>
  );
}
