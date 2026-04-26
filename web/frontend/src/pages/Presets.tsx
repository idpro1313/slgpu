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

interface PresetEditorForm {
  hf_id: string;
  engine: "vllm" | "sglang";
  tp: string;
  served_model_name: string;
  gpu_mask: string;
  description: string;
  parameters_json: string;
  is_active: boolean;
}

const EMPTY: NewPresetForm = {
  name: "",
  hf_id: "",
  engine: "vllm",
  tp: "",
  served_model_name: "",
  description: "",
};

function editorFromPreset(preset: Preset): PresetEditorForm {
  return {
    hf_id: preset.hf_id,
    engine: preset.engine === "sglang" ? "sglang" : "vllm",
    tp: preset.tp == null ? "" : String(preset.tp),
    served_model_name: preset.served_model_name ?? "",
    gpu_mask: preset.gpu_mask ?? "",
    description: preset.description ?? "",
    parameters_json: JSON.stringify(preset.parameters ?? {}, null, 2),
    is_active: preset.is_active,
  };
}

export function PresetsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<NewPresetForm>(EMPTY);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editor, setEditor] = useState<PresetEditorForm | null>(null);
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

  const selectedPreset = presets.data?.find((preset) => preset.id === selectedId) ?? null;

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
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const updatePreset = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: PresetEditorForm }) => {
      let parameters: unknown;
      try {
        parameters = JSON.parse(payload.parameters_json || "{}");
      } catch (exc) {
        throw new Error(`Некорректный JSON параметров: ${String(exc)}`);
      }
      if (!parameters || Array.isArray(parameters) || typeof parameters !== "object") {
        throw new Error("Параметры должны быть JSON-объектом");
      }
      return api.patch<Preset>(`/presets/${id}`, {
        hf_id: payload.hf_id,
        engine: payload.engine,
        tp: payload.tp ? Number(payload.tp) : null,
        served_model_name: payload.served_model_name || null,
        gpu_mask: payload.gpu_mask || null,
        description: payload.description || null,
        parameters,
        is_active: payload.is_active,
      });
    },
    onSuccess: (preset) => {
      setError(null);
      setSelectedId(preset.id);
      setEditor(editorFromPreset(preset));
      queryClient.invalidateQueries({ queryKey: ["presets"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    <>
      <PageHeader
        title="Пресеты запуска"
        subtitle="CRUD пресетов и двусторонняя синхронизация с data/presets/<slug>.env (PRESETS_DIR)."
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
        title="Просмотр и редактирование"
        subtitle="Изменения сохраняются в БД; чтобы записать их в data/presets/*.env, нажмите экспорт."
      >
        {!selectedPreset || !editor ? (
          <div className="empty-state">Выберите пресет в таблице ниже.</div>
        ) : (
          <>
            <div className="form-grid">
              <div>
                <label className="label">Имя пресета</label>
                <input className="input mono" value={selectedPreset.name} disabled />
              </div>
              <div>
                <label className="label">HF ID</label>
                <input
                  className="input"
                  value={editor.hf_id}
                  onChange={(event) => setEditor({ ...editor, hf_id: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Движок</label>
                <select
                  className="select"
                  value={editor.engine}
                  onChange={(event) =>
                    setEditor({
                      ...editor,
                      engine: event.target.value as PresetEditorForm["engine"],
                    })
                  }
                >
                  <option value="vllm">vLLM</option>
                  <option value="sglang">SGLang</option>
                </select>
              </div>
              <div>
                <label className="label">TP</label>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={128}
                  value={editor.tp}
                  onChange={(event) => setEditor({ ...editor, tp: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Served model name</label>
                <input
                  className="input"
                  value={editor.served_model_name}
                  onChange={(event) =>
                    setEditor({ ...editor, served_model_name: event.target.value })
                  }
                />
              </div>
              <div>
                <label className="label">GPU mask</label>
                <input
                  className="input"
                  placeholder="0,1,2,3"
                  value={editor.gpu_mask}
                  onChange={(event) => setEditor({ ...editor, gpu_mask: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Описание</label>
                <input
                  className="input"
                  value={editor.description}
                  onChange={(event) =>
                    setEditor({ ...editor, description: event.target.value })
                  }
                />
              </div>
              <div>
                <label className="label">Активен</label>
                <label style={{ display: "flex", gap: 8, alignItems: "center", minHeight: 42 }}>
                  <input
                    type="checkbox"
                    checked={editor.is_active}
                    onChange={(event) =>
                      setEditor({ ...editor, is_active: event.target.checked })
                    }
                  />
                  <span>{editor.is_active ? "да" : "нет"}</span>
                </label>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <label className="label" htmlFor="preset-parameters">
                Parameters JSON
              </label>
              <textarea
                id="preset-parameters"
                className="input mono"
                rows={14}
                spellCheck={false}
                value={editor.parameters_json}
                onChange={(event) =>
                  setEditor({ ...editor, parameters_json: event.target.value })
                }
              />
            </div>

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 16 }}>
              <button
                type="button"
                className="btn btn--primary"
                disabled={updatePreset.isPending || !editor.hf_id}
                onClick={() => updatePreset.mutate({ id: selectedPreset.id, payload: editor })}
              >
                {updatePreset.isPending ? "Сохраняем…" : "Сохранить"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => exportPreset.mutate(selectedPreset.id)}
                disabled={exportPreset.isPending}
              >
                Экспорт в .env
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setEditor(editorFromPreset(selectedPreset))}
              >
                Сбросить форму
              </button>
            </div>

            <p className="section__subtitle" style={{ marginTop: 12 }}>
              Файл: <span className="mono">{selectedPreset.file_path ?? "ещё не экспортирован"}</span>.
              Sync: {selectedPreset.is_synced ? "synced" : "drift"}.
            </p>
          </>
        )}
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
                        className="btn btn--ghost"
                        onClick={() => {
                          setSelectedId(preset.id);
                          setEditor(editorFromPreset(preset));
                        }}
                      >
                        Открыть
                      </button>{" "}
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
