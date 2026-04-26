import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  GpuStateResponse,
  GpuAvailability,
  Job,
  JobAccepted,
  Preset,
  RuntimeLogs,
  RuntimeSlotView,
  RuntimeSnapshot,
} from "@/api/types";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";
import { VramBar } from "@/components/VramBar";

function isEngineJobActive(j: Job): boolean {
  return j.scope === "engine" && (j.status === "queued" || j.status === "running");
}

function jobBusyOnResource(jobs: Job[] | undefined, resource: string | null | undefined): boolean {
  if (!jobs?.length) return false;
  return jobs.some((j) => isEngineJobActive(j) && j.resource === resource);
}

function num(v: number | string): number {
  return typeof v === "number" ? v : parseInt(String(v), 10) || 0;
}

function parseGpuCsv(csv: string | null | undefined): number[] {
  if (!csv?.trim()) return [];
  return csv
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !Number.isNaN(n));
}

function vramForIndices(gpu: GpuStateResponse | undefined, indices: number[]): { u: number; t: number } | null {
  if (!gpu?.gpus?.length || !indices.length) return null;
  const byIdx = new Map(gpu.gpus.map((g) => [g.index, g]));
  let u = 0;
  let t = 0;
  for (const i of indices) {
    const g = byIdx.get(i);
    if (g) {
      u += num(g.memory_used_mib);
      t += num(g.memory_total_mib);
    }
  }
  return t > 0 ? { u, t } : null;
}

function GpuMatrixTable({ data }: { data: GpuStateResponse | undefined }) {
  if (!data) {
    return <div className="empty-state">Нет данных GPU.</div>;
  }
  if (!data.smi_available) {
    return (
      <div className="empty-state">
        nvidia-smi недоступен{data.error ? ` (${data.error})` : ""}.
      </div>
    );
  }
  if (!data.gpus.length) {
    return <div className="empty-state">Список GPU пуст.</div>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table">
        <thead>
          <tr>
            <th>GPU</th>
            <th>Имя</th>
            <th>VRAM</th>
            <th>Util</th>
          </tr>
        </thead>
        <tbody>
          {data.gpus.map((g) => {
            const u = num(g.memory_used_mib);
            const to = num(g.memory_total_mib);
            const pct = to > 0 ? Math.min(100, Math.round((u / to) * 100)) : 0;
            return (
              <tr key={g.index}>
                <td className="mono">{g.index}</td>
                <td className="mono" style={{ maxWidth: 220 }}>
                  {g.name || "—"}
                </td>
                <td>
                  <div className="mono" style={{ fontSize: 13 }}>
                    {u} / {to} MiB
                  </div>
                  <VramBar pct={pct} height={6} borderRadius={3} marginTop={4} />
                </td>
                <td className="mono">
                  {g.utilization_gpu}%
                  {g.utilization_memory != null ? ` / m${g.utilization_memory}%` : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SlotCard(props: {
  slot: RuntimeSlotView;
  gpu: GpuStateResponse | undefined;
  jobs: Job[] | undefined;
  onDown: (key: string) => void;
  onRestart: (key: string) => void;
  onLogs: (key: string) => void;
  downPending: boolean;
  restartPending: boolean;
}) {
  const { slot } = props;
  const busy = jobBusyOnResource(props.jobs, `slot:${slot.slot_key}`);
  const vi = vramForIndices(props.gpu, parseGpuCsv(slot.gpu_indices));
  return (
    <div className="status-card">
      <div className="status-card__head">
        <span className="status-card__name mono">{slot.slot_key}</span>
        <StatusBadge status={slot.container_status ?? "unknown"} label={slot.engine} />
      </div>
      <div className="status-card__detail mono" style={{ fontSize: 13 }}>
        {slot.preset_name ?? "—"} • порт {slot.api_port ?? "—"}
        {slot.tp != null ? ` • TP ${slot.tp}` : ""}
      </div>
      <div className="status-card__detail mono" style={{ fontSize: 12 }}>
        GPU: {slot.gpu_indices ?? "—"}
        {vi ? ` • VRAM ${vi.u} / ${vi.t} MiB` : ""}
      </div>
      <div className="status-card__detail mono" style={{ fontSize: 12 }}>
        {slot.hf_id ?? "—"}
      </div>
      <div className="status-card__detail mono" style={{ fontSize: 12 }}>
        models: {slot.served_models?.length ? slot.served_models.join(", ") : "—"}
      </div>
      <div className="flex flex--gap-sm flex--wrap" style={{ marginTop: 10 }}>
        <button
          type="button"
          className="btn btn--danger"
          disabled={busy || props.downPending}
          onClick={() => props.onDown(slot.slot_key)}
        >
          Stop
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy || !slot.preset_name || props.restartPending}
          onClick={() => slot.preset_name && props.onRestart(slot.slot_key)}
        >
          Restart
        </button>
        <button type="button" className="btn" onClick={() => props.onLogs(slot.slot_key)}>
          Logs
        </button>
      </div>
    </div>
  );
}

export function RuntimePage() {
  const queryClient = useQueryClient();
  const [logSlotKey, setLogSlotKey] = useState<string | null>(null);
  const [launchOpen, setLaunchOpen] = useState(false);
  const [launchEngine, setLaunchEngine] = useState<"vllm" | "sglang">("vllm");
  const [launchPreset, setLaunchPreset] = useState<string>("");
  const [launchSlotKey, setLaunchSlotKey] = useState<string>("");
  const [launchTp, setLaunchTp] = useState<string>("");
  const [launchPort, setLaunchPort] = useState<string>("");
  const [launchGpuText, setLaunchGpuText] = useState<string>("");
  const [launchError, setLaunchError] = useState<string | null>(null);

  const presets = useQuery({
    queryKey: ["presets"],
    queryFn: ({ signal }) => api.get<Preset[]>("/presets", { signal }),
  });
  const snapshot = useQuery({
    queryKey: ["runtime-snapshot"],
    queryFn: ({ signal }) => api.get<RuntimeSnapshot>("/runtime/snapshot", { signal }),
    refetchInterval: 8_000,
  });
  const slotLogs = useQuery({
    queryKey: ["runtime-logs", logSlotKey],
    queryFn: ({ signal }) =>
      api.get<RuntimeLogs>(
        `/runtime/slots/${encodeURIComponent(logSlotKey!)}/logs?tail=400`,
        { signal },
      ),
    enabled: logSlotKey != null,
    refetchInterval: logSlotKey ? 5_000 : false,
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: ({ signal }) => api.get<Job[]>("/jobs", { signal }),
    refetchInterval: 2_000,
  });
  const gpuState = useQuery({
    queryKey: ["gpu-state"],
    queryFn: ({ signal }) => api.get<GpuStateResponse>("/gpu/state", { signal }),
    refetchInterval: 3_000,
  });

  const launchPresetRow = useMemo(
    () => presets.data?.find((p) => p.name === launchPreset),
    [presets.data, launchPreset],
  );
  const effectiveLaunchTp = useMemo(() => {
    if (launchTp.trim()) {
      const n = parseInt(launchTp, 10);
      return Number.isNaN(n) ? 1 : n;
    }
    return launchPresetRow?.tp != null ? launchPresetRow.tp : 1;
  }, [launchTp, launchPresetRow?.tp]);

  const availability = useQuery({
    queryKey: ["gpu-availability", effectiveLaunchTp, launchPreset],
    queryFn: ({ signal }) =>
      api.get<GpuAvailability>(`/gpu/availability?tp=${effectiveLaunchTp}`, { signal }),
    enabled: launchOpen && Boolean(launchPreset),
    refetchInterval: launchOpen ? 4_000 : false,
  });

  const slotDownMutation = useMutation({
    mutationFn: (slotKey: string) => api.post<JobAccepted>(`/runtime/slots/${encodeURIComponent(slotKey)}/down`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["gpu-state"] });
    },
  });

  const slotRestartMutation = useMutation({
    mutationFn: (args: { slotKey: string; preset: string }) =>
      api.post<JobAccepted>(`/runtime/slots/${encodeURIComponent(args.slotKey)}/restart`, {
        preset: args.preset,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["gpu-state"] });
    },
  });

  const slotUpMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<JobAccepted>("/runtime/slots", body),
    onSuccess: () => {
      setLaunchError(null);
      setLaunchOpen(false);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
      queryClient.invalidateQueries({ queryKey: ["runtime-snapshot"] });
      queryClient.invalidateQueries({ queryKey: ["gpu-availability"] });
      queryClient.invalidateQueries({ queryKey: ["gpu-state"] });
    },
    onError: (err: Error) => setLaunchError(err.message),
  });

  const snap = snapshot.data;

  const openLaunch = () => {
    setLaunchError(null);
    setLaunchOpen(true);
    if (presets.data?.[0]) {
      setLaunchPreset(presets.data[0].name);
      if (presets.data[0].tp != null) setLaunchTp(String(presets.data[0].tp));
      else setLaunchTp("");
    }
    setLaunchGpuText("");
  };

  const submitLaunch = () => {
    setLaunchError(null);
    if (!launchPreset) {
      setLaunchError("Выберите пресет");
      return;
    }
    const body: Record<string, unknown> = {
      engine: launchEngine,
      preset: launchPreset,
      tp: effectiveLaunchTp,
    };
    if (launchSlotKey.trim()) body.slot_key = launchSlotKey.trim();
    if (launchPort.trim()) {
      const p = parseInt(launchPort, 10);
      if (!Number.isNaN(p)) body.host_api_port = p;
    }
    if (launchGpuText.trim()) {
      const gpus = launchGpuText
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !Number.isNaN(n));
      if (gpus.length) body.gpu_indices = gpus;
    }
    slotUpMutation.mutate(body);
  };

  const slots = snap?.slots ?? [];
  const legacyNoSlots = slots.length === 0 && Boolean(snap?.engine);

  return (
    <>
      <PageHeader
        title="Inference"
        subtitle="Мультислотный vLLM/SGLang (docker), GPU в реальном времени, запуск и остановка по слотам. CLI: ./slgpu up / down."
      />

      <Section
        title="GPU (live)"
        subtitle="Снимок nvidia-smi через web (кэш ~3 с), обновление каждые 3 с."
        actions={
          <button
            type="button"
            className="btn"
            onClick={() => gpuState.refetch()}
            disabled={gpuState.isFetching}
          >
            Обновить
          </button>
        }
      >
        <GpuMatrixTable data={gpuState.data} />
      </Section>

      <Section
        title="Слоты"
        subtitle="Активные слоты из снимка runtime. Для `slot_key=default` (как в CLI) укажите имя слота `default` в диалоге запуска."
        actions={
          <div className="flex flex--gap-sm flex--wrap" style={{ alignItems: "center" }}>
            <button
              type="button"
              className="btn"
              onClick={() => snapshot.refetch()}
              disabled={snapshot.isFetching}
            >
              Обновить снимок
            </button>
            <button type="button" className="btn btn--primary" onClick={openLaunch}>
              Запустить слот
            </button>
          </div>
        }
      >
        {snapshot.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : slots.length > 0 ? (
          <div className="cards-grid">
            {slots.map((s) => (
              <SlotCard
                key={s.slot_key}
                slot={s}
                gpu={gpuState.data}
                jobs={jobs.data}
                onDown={(key) => slotDownMutation.mutate(key)}
                onRestart={(key) => {
                  const p = s.preset_name;
                  if (p) slotRestartMutation.mutate({ slotKey: key, preset: p });
                }}
                onLogs={(key) => setLogSlotKey(key)}
                downPending={slotDownMutation.isPending}
                restartPending={slotRestartMutation.isPending}
              />
            ))}
          </div>
        ) : legacyNoSlots ? (
          <p className="section__subtitle">
            Compose/legacy-контейнер без записей в <span className="mono">engine_slots</span> — кратко:{" "}
            <span className="mono">
              {snap?.engine} :{snap?.api_port}
            </span>
            {snap?.served_models?.length ? ` • models: ${snap.served_models.join(", ")}` : ""}
          </p>
        ) : (
          <div className="empty-state">Нет активных слотов. Нажмите «Запустить слот».</div>
        )}
      </Section>

      <Section
        title="Лог слота"
        subtitle="Кнопка Logs у слота или выбор `default` для логов слота по умолчанию."
        actions={
          <div className="flex flex--gap-sm flex--wrap">
            <button
              type="button"
              className="btn"
              onClick={() => setLogSlotKey("default")}
            >
              default
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => slotLogs.refetch()}
              disabled={!logSlotKey || slotLogs.isFetching}
            >
              Обновить
            </button>
          </div>
        }
      >
        <p className="section__subtitle">
          Слот: <span className="mono">{logSlotKey ?? "не выбран"}</span>
          {logSlotKey && slotLogs.data?.engine ? (
            <>
              {" "}
              · движок <span className="mono">{slotLogs.data.engine}</span>
              {slotLogs.data.container_name ? (
                <>
                  {" "}
                  · <span className="mono">{slotLogs.data.container_name}</span>
                </>
              ) : null}
            </>
          ) : null}
        </p>
        <pre className="code-block" style={{ maxHeight: 420, overflow: "auto" }}>
          {logSlotKey
            ? slotLogs.isLoading
              ? "Загружаем…"
              : slotLogs.data?.logs?.trim()
                ? slotLogs.data.logs
                : "Лог пуст или контейнер не найден."
            : "Нажмите Logs у слота или «default»."}
        </pre>
      </Section>

      <Modal
        title="Запуск слота"
        subtitle="Имя слота `default` соответствует CLI. GPU и порт при необходимости подставляются на сервере; индексы вручную — через запятую (длина = TP)."
        isOpen={launchOpen}
        onClose={() => setLaunchOpen(false)}
        actions={
          <button
            type="button"
            className="btn btn--primary"
            disabled={slotUpMutation.isPending || !launchPreset}
            onClick={submitLaunch}
          >
            {slotUpMutation.isPending ? "Отправка…" : "Запустить"}
          </button>
        }
      >
        <div className="form-grid" style={{ marginTop: 12 }}>
          <div>
            <label className="label">Движок</label>
            <select
              className="select"
              value={launchEngine}
              onChange={(e) => setLaunchEngine(e.target.value as "vllm" | "sglang")}
            >
              <option value="vllm">vLLM (порты 8111+)</option>
              <option value="sglang">SGLang (порты 8222+)</option>
            </select>
          </div>
          <div>
            <label className="label">Пресет</label>
            <select
              className="select"
              value={launchPreset}
              onChange={(e) => {
                setLaunchPreset(e.target.value);
                const p = presets.data?.find((x) => x.name === e.target.value);
                if (p?.tp != null) setLaunchTp(String(p.tp));
                else setLaunchTp("");
              }}
            >
              <option value="">— выберите —</option>
              {presets.data?.map((p) => (
                <option value={p.name} key={p.id}>
                  {p.name} (TP {p.tp ?? "?"})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">TP (пусто = из пресета)</label>
            <input
              className="input"
              type="number"
              value={launchTp}
              onChange={(e) => setLaunchTp(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Имя слота (опц.)</label>
            <input
              className="input"
              value={launchSlotKey}
              onChange={(e) => setLaunchSlotKey(e.target.value)}
              placeholder="auto"
              autoComplete="off"
            />
          </div>
          <div>
            <label className="label">host_api_port (опц.)</label>
            <input
              className="input"
              type="number"
              value={launchPort}
              onChange={(e) => setLaunchPort(e.target.value)}
              placeholder="авто"
            />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="label">GPU индексы вручную, через запятую (опц.)</label>
            <input
              className="input mono"
              value={launchGpuText}
              onChange={(e) => setLaunchGpuText(e.target.value)}
              placeholder="например: 0,1,2,3"
              autoComplete="off"
            />
          </div>
        </div>
        {launchPreset && availability.data ? (
          <div style={{ marginTop: 16, fontSize: 13 }} className="mono">
            <div>
              Свободные GPU: {availability.data.available.join(", ") || "—"}
            </div>
            <div>
              Подсказка (suggested):{" "}
              {availability.data.suggested?.length
                ? availability.data.suggested.join(", ")
                : "недостаточно свободных для TP"}
            </div>
            {availability.data.note ? <div>note: {availability.data.note}</div> : null}
          </div>
        ) : null}
        {launchError ? <p style={{ color: "var(--color-danger)", marginTop: 12 }}>{launchError}</p> : null}
      </Modal>
    </>
  );
}
