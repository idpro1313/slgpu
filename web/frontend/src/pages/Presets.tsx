import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Preset, PresetSyncResult } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";
import {
  IconActionButton,
  IconArrowUpTray,
  IconEdit,
  IconFileX,
  IconTrash,
} from "@/components/TableActionIcons";

interface NewPresetForm {
  name: string;
  hf_id: string;
  tp: string;
  served_model_name: string;
  gpu_mask: string;
  description: string;
  parameters: ParameterRow[];
}

interface ParameterRow {
  id: string;
  key: string;
  value: string;
}

interface PresetEditorForm {
  hf_id: string;
  tp: string;
  served_model_name: string;
  gpu_mask: string;
  description: string;
  parameters: ParameterRow[];
  is_active: boolean;
}

const EMPTY: NewPresetForm = {
  name: "",
  hf_id: "",
  tp: "",
  served_model_name: "",
  gpu_mask: "",
  description: "",
  parameters: [],
};

function editorFromPreset(preset: Preset): PresetEditorForm {
  return {
    hf_id: preset.hf_id,
    tp: preset.tp == null ? "" : String(preset.tp),
    served_model_name: preset.served_model_name ?? "",
    gpu_mask: preset.gpu_mask ?? "",
    description: preset.description ?? "",
    parameters: parameterRowsFromRecord(preset.parameters ?? {}),
    is_active: preset.is_active,
  };
}

function parameterRowsFromRecord(parameters: Record<string, unknown>): ParameterRow[] {
  return Object.entries(parameters).map(([key, value], index) => ({
    id: `${key}-${index}`,
    key,
    value: value == null ? "" : String(value),
  }));
}

function parametersFromRows(rows: ParameterRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue;
    out[key] = row.value;
  }
  return out;
}

function isPresetEditorDirty(editor: PresetEditorForm, preset: Preset): boolean {
  const base = editorFromPreset(preset);
  if (editor.hf_id !== base.hf_id) return true;
  if (editor.tp !== base.tp) return true;
  if (editor.served_model_name !== base.served_model_name) return true;
  if (editor.gpu_mask !== base.gpu_mask) return true;
  if (editor.description !== base.description) return true;
  if (editor.is_active !== base.is_active) return true;
  const cur = parametersFromRows(editor.parameters);
  const orig = preset.parameters ?? {};
  const keys = new Set([...Object.keys(cur), ...Object.keys(orig)]);
  for (const key of keys) {
    const a = cur[key] ?? "";
    const b = orig[key] == null ? "" : String(orig[key]);
    if (a !== b) return true;
  }
  return false;
}

function newParameterRow(): ParameterRow {
  return { id: `${Date.now()}-${Math.random()}`, key: "", value: "" };
}

const COMMON_PARAMETERS = [
  "MAX_MODEL_LEN",
  "MODEL_REVISION",
  "KV_CACHE_DTYPE",
  "GPU_MEM_UTIL",
  "VLLM_DOCKER_IMAGE",
  "SLGPU_MAX_NUM_BATCHED_TOKENS",
  "SLGPU_VLLM_MAX_NUM_SEQS",
  "SLGPU_VLLM_BLOCK_SIZE",
  "SLGPU_ENABLE_PREFIX_CACHING",
  "SLGPU_ENABLE_EXPERT_PARALLEL",
  "SGLANG_MEM_FRACTION_STATIC",
  "SGLANG_CUDA_GRAPH_MAX_BS",
  "TOOL_CALL_PARSER",
  "REASONING_PARSER",
  "CHAT_TEMPLATE_CONTENT_FORMAT",
  "BENCH_MODEL_NAME",
];

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

  const cancelPresetEdit = () => {
    if (!selectedPreset || !editor) return;
    if (isPresetEditorDirty(editor, selectedPreset)) {
      if (
        !window.confirm(
          "Закрыть редактирование без сохранения? Несохранённые изменения будут потеряны.",
        )
      ) {
        return;
      }
    }
    setSelectedId(null);
    setEditor(null);
  };

  const create = useMutation({
    mutationFn: (payload: NewPresetForm) =>
      api.post<Preset>("/presets", {
        name: payload.name,
        hf_id: payload.hf_id,
        tp: payload.tp ? Number(payload.tp) : null,
        served_model_name: payload.served_model_name || null,
        gpu_mask: payload.gpu_mask || null,
        description: payload.description || null,
        parameters: parametersFromRows(payload.parameters),
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
      const parameters = parametersFromRows(payload.parameters);
      return api.patch<Preset>(`/presets/${id}`, {
        hf_id: payload.hf_id,
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

  const deletePreset = useMutation({
    mutationFn: ({ id, deleteFile }: { id: number; deleteFile: boolean }) =>
      api.delete<{ deleted: boolean }>(`/presets/${id}?delete_file=${deleteFile ? "true" : "false"}`),
    onSuccess: () => {
      setError(null);
      setSelectedId(null);
      setEditor(null);
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
        subtitle="Минимальный пресет: имя, HF id и опционально TP. Движок (vLLM/SGLang) выбирается при запуске на странице Inference. Параметры можно расширить позже."
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
            <label className="label">TP (tensor parallel)</label>
            <input
              className="input"
              type="number"
              min={1}
              max={128}
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
            <label className="label">GPU mask</label>
            <input
              className="input"
              placeholder="0,1,2,3"
              value={form.gpu_mask}
              onChange={(event) => setForm({ ...form, gpu_mask: event.target.value })}
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
          <div style={{ gridColumn: "1 / -1" }}>
            <label className="label">Параметры запуска</label>
            <ParameterRows
              rows={form.parameters}
              onChange={(parameters) => setForm({ ...form, parameters })}
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
              <label className="label">Параметры запуска</label>
              <ParameterRows
                rows={editor.parameters}
                onChange={(parameters) => setEditor({ ...editor, parameters })}
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
              <button type="button" className="btn btn--ghost" onClick={cancelPresetEdit}>
                Отмена
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
              <button
                type="button"
                className="btn btn--danger"
                disabled={deletePreset.isPending}
                onClick={() => {
                  if (window.confirm(`Удалить пресет ${selectedPreset.name} из БД?`)) {
                    deletePreset.mutate({ id: selectedPreset.id, deleteFile: false });
                  }
                }}
              >
                Удалить из БД
              </button>
              <button
                type="button"
                className="btn btn--danger"
                disabled={deletePreset.isPending}
                onClick={() => {
                  if (window.confirm(`Удалить пресет ${selectedPreset.name} и его .env файл?`)) {
                    deletePreset.mutate({ id: selectedPreset.id, deleteFile: true });
                  }
                }}
              >
                Удалить с .env
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
          <div style={{ overflowX: "auto", width: "100%" }}>
            <table className="table table--registry">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>HF ID</th>
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
                      <div
                        className="table-actions"
                        role="group"
                        aria-label={`Действия: ${preset.name}`}
                      >
                        <IconActionButton
                          label="Редактировать пресет"
                          variant="ghost"
                          onClick={() => {
                            setSelectedId(preset.id);
                            setEditor(editorFromPreset(preset));
                          }}
                        >
                          <IconEdit />
                        </IconActionButton>
                        <IconActionButton
                          label="Экспортировать в .env на диске"
                          variant="default"
                          onClick={() => exportPreset.mutate(preset.id)}
                          disabled={exportPreset.isPending}
                        >
                          <IconArrowUpTray />
                        </IconActionButton>
                        <IconActionButton
                          label="Удалить пресет из БД (запись в web-реестре)"
                          variant="danger"
                          disabled={deletePreset.isPending}
                          onClick={() => {
                            if (window.confirm(`Удалить пресет ${preset.name} из БД?`)) {
                              deletePreset.mutate({ id: preset.id, deleteFile: false });
                            }
                          }}
                        >
                          <IconTrash />
                        </IconActionButton>
                        <IconActionButton
                          label="Удалить пресет и файл .env с диска"
                          variant="danger"
                          className="icon-btn--file-wipe"
                          disabled={deletePreset.isPending}
                          onClick={() => {
                            if (
                              window.confirm(
                                `Удалить пресет ${preset.name} и стереть файл .env в PRESETS_DIR?`,
                              )
                            ) {
                              deletePreset.mutate({ id: preset.id, deleteFile: true });
                            }
                          }}
                        >
                          <IconFileX />
                        </IconActionButton>
                      </div>
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

function ParameterRows({
  rows,
  onChange,
}: {
  rows: ParameterRow[];
  onChange: (rows: ParameterRow[]) => void;
}) {
  function updateRow(id: string, patch: Partial<ParameterRow>) {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  function removeRow(id: string) {
    onChange(rows.filter((row) => row.id !== id));
  }

  return (
    <div className="flex flex--col flex--gap-sm">
      {rows.length === 0 ? (
        <div className="empty-state" style={{ padding: 16 }}>
          Дополнительных параметров нет.
        </div>
      ) : (
        rows.map((row) => (
          <div className="form-grid" key={row.id} style={{ alignItems: "end" }}>
            <div>
              <label className="label">Ключ</label>
              <input
                className="input mono"
                list="preset-parameter-keys"
                value={row.key}
                onChange={(event) => updateRow(row.id, { key: event.target.value })}
                autoComplete="off"
              />
            </div>
            <div>
              <label className="label">Значение</label>
              <input
                className="input mono"
                value={row.value}
                onChange={(event) => updateRow(row.id, { value: event.target.value })}
                autoComplete="off"
              />
            </div>
            <div>
              <button type="button" className="btn btn--danger" onClick={() => removeRow(row.id)}>
                Удалить параметр
              </button>
            </div>
          </div>
        ))
      )}
      <datalist id="preset-parameter-keys">
        {COMMON_PARAMETERS.map((key) => (
          <option value={key} key={key} />
        ))}
      </datalist>
      <div>
        <button type="button" className="btn" onClick={() => onChange([...rows, newParameterRow()])}>
          Добавить параметр
        </button>
      </div>
    </div>
  );
}
