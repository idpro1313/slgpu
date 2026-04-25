import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Preset, PresetSyncResult } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

interface NewPresetForm {
  name: string;
  hf_id: string;
  engine: "vllm" | "sglang";
  tp: string;
  served_model_name: string;
  description: string;
}

const EMPTY: NewPresetForm = {
  name: "",
  hf_id: "",
  engine: "vllm",
  tp: "",
  served_model_name: "",
  description: "",
};

export function PresetsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<NewPresetForm>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<PresetSyncResult | null>(null);

  const presets = useQuery({
    queryKey: ["presets"],
    queryFn: () => api.get<Preset[]>("/presets"),
    refetchInterval: 15_000,
  });

  const sync = useMutation({
    mutationFn: () => api.post<PresetSyncResult>("/presets/sync"),
    onSuccess: (data) => {
      setSyncResult(data);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const create = useMutation({
    mutationFn: (payload: NewPresetForm) =>
      api.post<Preset>("/presets", {
        name: payload.name,
        hf_id: payload.hf_id,
        engine: payload.engine,
        tp: payload.tp ? Number(payload.tp) : null,
        served_model_name: payload.served_model_name || null,
        description: payload.description || null,
        parameters: {},
      }),
    onSuccess: () => {
      setForm(EMPTY);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const exportPreset = useMutation({
    mutationFn: (id: number) => api.post<Preset>(`/presets/${id}/export`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["presets"] }),
    onError: (err: Error) => setError(err.message),
  });

  return (
    <>
      <PageHeader
        title="Пресеты запуска"
        subtitle="CRUD пресетов и двусторонняя синхронизация с configs/models/<slug>.env."
        actions={
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
          >
            {sync.isPending ? "Синхронизация…" : "Синхронизировать с диском"}
          </button>
        }
      />

      {syncResult ? (
        <div className="section" style={{ marginTop: 0 }}>
          <p className="section__subtitle">
            Импортировано <strong>{syncResult.imported}</strong>, обновлено{" "}
            <strong>{syncResult.updated}</strong>, пропущено{" "}
            <strong>{syncResult.skipped}</strong>.
          </p>
          {syncResult.errors.length > 0 ? (
            <pre className="code-block">{syncResult.errors.join("\n")}</pre>
          ) : null}
        </div>
      ) : null}

      <Section
        title="Создать пресет"
        subtitle="Минимальный пресет: имя, HF id, движок и опционально TP. Параметры можно расширить позже."
      >
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            if (!form.name || !form.hf_id) return;
            create.mutate(form);
          }}
        >
          <div>
            <label className="label">Имя пресета</label>
            <input
              className="input"
              placeholder="qwen3.6-35b-a3b"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </div>
          <div>
            <label className="label">HF ID</label>
            <input
              className="input"
              placeholder="Qwen/Qwen3.6-35B-A3B"
              value={form.hf_id}
              onChange={(event) => setForm({ ...form, hf_id: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Движок</label>
            <select
              className="select"
              value={form.engine}
              onChange={(event) =>
                setForm({ ...form, engine: event.target.value as NewPresetForm["engine"] })
              }
            >
              <option value="vllm">vLLM</option>
              <option value="sglang">SGLang</option>
            </select>
          </div>
          <div>
            <label className="label">TP (tensor parallel)</label>
            <input
              className="input"
              type="number"
              min={1}
              max={16}
              value={form.tp}
              onChange={(event) => setForm({ ...form, tp: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Served model name</label>
            <input
              className="input"
              placeholder="qwen3.6-35b"
              value={form.served_model_name}
              onChange={(event) =>
                setForm({ ...form, served_model_name: event.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Описание</label>
            <input
              className="input"
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
            />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={create.isPending || !form.name || !form.hf_id}
            >
              {create.isPending ? "Создаём…" : "Создать пресет"}
            </button>
          </div>
        </form>
        {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}
      </Section>

      <Section
        title="Все пресеты"
        subtitle="Колонка Sync показывает, совпадает ли запись в БД с .env-файлом."
      >
        {presets.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !presets.data || presets.data.length === 0 ? (
          <div className="empty-state">Пресетов нет. Создайте новый или синхронизируйте с диска.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>HF ID</th>
                  <th>Движок</th>
                  <th>TP</th>
                  <th>Served name</th>
                  <th>Sync</th>
                  <th>Active</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {presets.data.map((preset) => (
                  <tr key={preset.id}>
                    <td className="mono">{preset.name}</td>
                    <td className="mono">{preset.hf_id}</td>
                    <td>{preset.engine}</td>
                    <td>{preset.tp ?? "—"}</td>
                    <td className="mono">{preset.served_model_name ?? "—"}</td>
                    <td>
                      <StatusBadge
                        status={preset.is_synced ? "healthy" : "degraded"}
                        label={preset.is_synced ? "synced" : "drift"}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        status={preset.is_active ? "healthy" : "unknown"}
                        label={preset.is_active ? "yes" : "no"}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => exportPreset.mutate(preset.id)}
                        disabled={exportPreset.isPending}
                      >
                        Экспорт в .env
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}
