import { Fragment, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/api/client";
import type { Preset, PresetCloneRequest, PresetParameterSchemaOut, PresetParameterSchemaRow } from "@/api/types";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";
import {
  IconActionButton,
  IconCloudArrowDown,
  IconCopy,
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

function editorFromPreset(
  preset: Preset,
  schema?: PresetParameterSchemaRow[],
): PresetEditorForm {
  const saved = preset.parameters ?? {};
  const parameters =
    schema?.length && schema.length > 0
      ? mergeSchemaIntoRows(schema, saved)
      : parameterRowsFromRecord(saved);
  return {
    hf_id: preset.hf_id,
    tp: preset.tp == null ? "" : String(preset.tp),
    served_model_name: preset.served_model_name ?? "",
    gpu_mask: preset.gpu_mask ?? "",
    description: preset.description ?? "",
    parameters,
    is_active: preset.is_active,
  };
}

function mergeSchemaIntoRows(
  schema: PresetParameterSchemaRow[],
  saved: Record<string, unknown>,
): ParameterRow[] {
  return schema.map((row) => ({
    id: row.key,
    key: row.key,
    value:
      saved[row.key] == null || String(saved[row.key]).trim() === ""
        ? ""
        : String(saved[row.key]),
  }));
}

function applyDefaultsToEmptyFields(
  rows: ParameterRow[],
  schema: PresetParameterSchemaRow[],
): ParameterRow[] {
  const defaults = new Map(schema.map((r) => [r.key, r.default_value]));
  return rows.map((r) => {
    const d = defaults.get(r.key);
    if (!d || r.value.trim() !== "") return r;
    return { ...r, value: d };
  });
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

function saveBlobToClient(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
}

export function PresetsPage() {
  const queryClient = useQueryClient();
  const presetFileImportRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<NewPresetForm>(EMPTY);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editor, setEditor] = useState<PresetEditorForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cloneSource, setCloneSource] = useState<Preset | null>(null);
  const [cloneName, setCloneName] = useState("");
  const [cloneTp, setCloneTp] = useState<string>("");
  const [cloneDescription, setCloneDescription] = useState<string>("");

  const presets = useQuery({
    queryKey: ["presets"],
    queryFn: () => api.get<Preset[]>("/presets"),
    refetchInterval: 15_000,
  });

  const selectedPreset = presets.data?.find((preset) => preset.id === selectedId) ?? null;

  const presetParamSchema = useQuery({
    queryKey: ["presets", "parameter-schema"],
    queryFn: () => api.get<PresetParameterSchemaOut>("/presets/parameter-schema"),
    staleTime: 60 * 60 * 1000,
  });

  const schemaRows = presetParamSchema.data?.rows;

  useEffect(() => {
    const rows = presetParamSchema.data?.rows;
    if (!rows?.length) return;
    setForm((f) => {
      if (f.parameters.length > 0) return f;
      return { ...f, parameters: mergeSchemaIntoRows(rows, {}) };
    });
  }, [presetParamSchema.data]);

  useEffect(() => {
    const rows = presetParamSchema.data?.rows;
    if (!rows?.length || selectedId == null) return;
    setEditor((e) => {
      if (!e) return e;
      const preset = presets.data?.find((p) => p.id === selectedId);
      if (!preset) return e;
      if (e.parameters.length >= rows.length) return e;
      return {
        ...e,
        parameters: mergeSchemaIntoRows(rows, {
          ...(preset.parameters ?? {}),
          ...parametersFromRows(e.parameters),
        }),
      };
    });
  }, [presetParamSchema.data, selectedId, presets.data]);

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

  const importPresetFile = useMutation({
    mutationFn: ({ file, overwrite }: { file: File; overwrite: boolean }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("overwrite", overwrite ? "true" : "false");
      return api.postForm<Preset>("/presets/import-env", fd);
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
  });

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
      const rows = queryClient.getQueryData<PresetParameterSchemaOut>([
        "presets",
        "parameter-schema",
      ])?.rows;
      setForm({
        ...EMPTY,
        parameters: rows?.length ? mergeSchemaIntoRows(rows, {}) : [],
      });
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const exportPreset = useMutation({
    mutationFn: (id: number) => api.post<Preset>(`/presets/${id}/export`),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const downloadPresetEnv = useMutation({
    mutationFn: async (preset: Preset) => {
      const result = await api.download(`/presets/${preset.id}/download-env`);
      return { ...result, fallbackFilename: `${preset.name}.env` };
    },
    onSuccess: ({ blob, filename, fallbackFilename }) => {
      saveBlobToClient(blob, filename ?? fallbackFilename);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const clonePresetMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: PresetCloneRequest }) =>
      api.post<Preset>(`/presets/${id}/clone`, body),
    onSuccess: () => {
      setCloneSource(null);
      setCloneName("");
      setCloneTp("");
      setCloneDescription("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["presets"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
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
      const rows = queryClient.getQueryData<PresetParameterSchemaOut>([
        "presets",
        "parameter-schema",
      ])?.rows;
      setEditor(editorFromPreset(preset, rows));
      queryClient.invalidateQueries({ queryKey: ["presets"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
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
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    <>
      <PageHeader
        title="Пресеты запуска"
        subtitle="Реестр в БД для UI и Inference. «Скачать .env на ПК» сохраняет файл через браузер, а «Выгрузить в .env» пишет копию в PRESETS_DIR на сервере."
      />

      <Section
        title="Загрузить пресет из файла"
        subtitle="Файл как data/presets/*.env (KEY=VALUE), обязателен MODEL_ID. Имя пресета в БД = basename файла без расширения (slug), например qwen.env → qwen."
      >
        <input
          ref={presetFileImportRef}
          type="file"
          accept=".env,text/plain,application/octet-stream"
          style={{ display: "none" }}
          aria-hidden
          onChange={(event) => {
            void (async () => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              setError(null);
              try {
                await importPresetFile.mutateAsync({ file, overwrite: false });
              } catch (e) {
                if (e instanceof ApiError && e.status === 409) {
                  const ok = window.confirm(
                    "Пресет с таким именем уже есть в базе. Перезаписать данными из выбранного файла?",
                  );
                  if (!ok) return;
                  try {
                    await importPresetFile.mutateAsync({ file, overwrite: true });
                  } catch (e2) {
                    setError(e2 instanceof Error ? e2.message : String(e2));
                  }
                } else {
                  setError(e instanceof Error ? e.message : String(e));
                }
              }
            })();
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn--primary"
            disabled={importPresetFile.isPending}
            onClick={() => presetFileImportRef.current?.click()}
          >
            {importPresetFile.isPending ? "Загрузка…" : "Выбрать файл .env…"}
          </button>
          <span className="section__subtitle" style={{ margin: 0 }}>
            UTF-8; при совпадении имени без галочки «перезапись» будет предупреждение.
          </span>
        </div>
      </Section>

      <Section
        title="Создать пресет"
        subtitle="Минимальный пресет: имя, HF id и опционально TP. Таблица ниже содержит все поддерживаемые ключи параметров (как при экспорте .env); подсказка «дефолт» — значение из scripts/serve.sh, пустая ячейка не сохраняется в БД."
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
              schemaRows={schemaRows}
              isLoadingSchema={presetParamSchema.isLoading}
              loadSchemaError={
                presetParamSchema.isError
                  ? (presetParamSchema.error as Error)?.message ?? "ошибка запроса"
                  : undefined
              }
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
        subtitle="Сохранение в БД; клиентская загрузка скачивает .env в браузер, серверная выгрузка пишет data/presets/(slug).env."
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
                schemaRows={schemaRows}
                isLoadingSchema={presetParamSchema.isLoading}
                loadSchemaError={
                  presetParamSchema.isError
                    ? (presetParamSchema.error as Error)?.message ?? "ошибка запроса"
                    : undefined
                }
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
                onClick={() => downloadPresetEnv.mutate(selectedPreset)}
                disabled={downloadPresetEnv.isPending}
              >
                {downloadPresetEnv.isPending ? "Готовим…" : "Скачать .env на ПК"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => exportPreset.mutate(selectedPreset.id)}
                disabled={exportPreset.isPending}
              >
                {exportPreset.isPending ? "Выгружаем…" : "Выгрузить в PRESETS_DIR"}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setEditor(editorFromPreset(selectedPreset, schemaRows))}
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
              Путь к .env после выгрузки:{" "}
              <span className="mono">{selectedPreset.file_path ?? "— (ещё не выгружали)"}</span>
            </p>
          </>
        )}
      </Section>

      <Section
        title="Все пресеты"
        subtitle="Скачивание .env доступно прямо из таблицы; редактирование и серверная выгрузка — в карточке выше."
      >
        {presets.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !presets.data || presets.data.length === 0 ? (
          <div className="empty-state">Пресетов нет. Создайте новый выше.</div>
        ) : (
          <div style={{ overflowX: "auto", width: "100%" }}>
            <table className="table table--registry">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>HF ID</th>
                  <th>TP</th>
                  <th>Served name</th>
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
                            setEditor(editorFromPreset(preset, schemaRows));
                          }}
                        >
                          <IconEdit />
                        </IconActionButton>
                        <IconActionButton
                          label="Копия пресета в БД"
                          variant="default"
                          onClick={() => {
                            setCloneSource(preset);
                            setCloneName(`${preset.name}-copy`);
                          }}
                        >
                          <IconCopy />
                        </IconActionButton>
                        <IconActionButton
                          label="Скачать .env на клиентский ПК"
                          variant="default"
                          disabled={downloadPresetEnv.isPending}
                          onClick={() => downloadPresetEnv.mutate(preset)}
                        >
                          <IconCloudArrowDown />
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

      <Modal
        title="Копия пресета"
        subtitle={cloneSource ? `Источник: ${cloneSource.name}` : null}
        isOpen={cloneSource != null}
        onClose={() => {
          setCloneSource(null);
          setCloneName("");
          setCloneTp("");
          setCloneDescription("");
        }}
        actions={
          <button
            type="button"
            className="btn btn--primary"
            disabled={clonePresetMut.isPending || !cloneName.trim() || !cloneSource}
            onClick={() => {
              if (!cloneSource) return;
              const name = cloneName.trim();
              if (!name) return;
              const body: PresetCloneRequest = { name };
              if (cloneTp.trim()) {
                const n = Number(cloneTp);
                if (!Number.isNaN(n)) body.tp = n;
              }
              if (cloneDescription.trim()) body.description = cloneDescription.trim();
              clonePresetMut.mutate({ id: cloneSource.id, body });
            }}
          >
            {clonePresetMut.isPending ? "Создаём…" : "Создать копию"}
          </button>
        }
      >
        {cloneSource ? (
          <div className="form-grid" style={{ marginTop: 12 }}>
            <div>
              <label className="label">Новое имя (slug)</label>
              <input
                className="input mono"
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
                autoComplete="off"
              />
            </div>
            <details style={{ gridColumn: "1 / -1" }}>
              <summary className="section__subtitle" style={{ cursor: "pointer" }}>
                Дополнительно: TP и описание (необязательно)
              </summary>
              <div className="form-grid" style={{ marginTop: 12 }}>
                <div>
                  <label className="label">TP (пусто = как в источнике)</label>
                  <input
                    className="input mono"
                    type="number"
                    min={1}
                    value={cloneTp}
                    onChange={(e) => setCloneTp(e.target.value)}
                    placeholder={cloneSource.tp != null ? String(cloneSource.tp) : ""}
                  />
                </div>
                <div style={{ gridColumn: "1 / -1" }}>
                  <label className="label">Описание</label>
                  <input
                    className="input"
                    value={cloneDescription}
                    onChange={(e) => setCloneDescription(e.target.value)}
                    placeholder={cloneSource.description ?? ""}
                  />
                </div>
              </div>
            </details>
            <p className="section__subtitle" style={{ gridColumn: "1 / -1" }}>
              Остальные поля копируются с исходного пресета. При необходимости для CLI выгрузите новый
              пресет в .env в карточке редактирования.
            </p>
          </div>
        ) : null}
      </Modal>
    </>
  );
}

function ParameterRowsLegacy({
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
          Дополнительных параметров нет — добавьте пары ключ/значение.
        </div>
      ) : (
        rows.map((row) => (
          <div className="form-grid" key={row.id} style={{ alignItems: "end" }}>
            <div>
              <label className="label">Ключ</label>
              <input
                className="input mono"
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
      <div>
        <button type="button" className="btn" onClick={() => onChange([...rows, newParameterRow()])}>
          Добавить параметр
        </button>
      </div>
    </div>
  );
}

function ParameterRows({
  rows,
  schemaRows,
  isLoadingSchema,
  loadSchemaError,
  onChange,
}: {
  rows: ParameterRow[];
  schemaRows: PresetParameterSchemaRow[] | undefined;
  isLoadingSchema?: boolean;
  loadSchemaError?: string;
  onChange: (rows: ParameterRow[]) => void;
}) {
  function updateRow(id: string, patch: Partial<ParameterRow>) {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  if (isLoadingSchema) {
    return <div className="empty-state">Загружаем список поддерживаемых параметров…</div>;
  }

  if (loadSchemaError && !schemaRows?.length) {
    return (
      <div className="flex flex--col flex--gap-sm">
        <p className="section__subtitle" style={{ color: "var(--color-danger)" }}>
          Схема параметров не загружена ({loadSchemaError}). Добавляйте ключи вручную — только канонические ключи сохранятся в БД после сохранения карточки.
        </p>
        <ParameterRowsLegacy rows={rows} onChange={onChange} />
      </div>
    );
  }

  /**
   * Полный режим по API: группы как в экспорте .env, дефолт и описание колонкой.
   */
  if (schemaRows?.length) {
    let prevGroup = "";
    return (
      <div className="flex flex--col flex--gap-sm">
        <div style={{ overflowX: "auto", width: "100%" }}>
          <table className="table table--registry" style={{ fontSize: "0.9rem" }}>
            <thead>
              <tr>
                <th>Параметр</th>
                <th>Значение</th>
                <th>Дефолт (serve.sh)</th>
              </tr>
            </thead>
            <tbody>
              {schemaRows.map((meta) => {
                const row = rows.find((r) => r.key === meta.key);
                if (!row) return null;
                const showGroup = meta.group !== prevGroup;
                prevGroup = meta.group;
                return (
                  <Fragment key={meta.key}>
                    {showGroup ? (
                      <tr>
                        <td
                          colSpan={3}
                          style={{ background: "var(--color-muted-bg, rgba(10,58,138,0.06))" }}
                        >
                          <strong>{meta.group}</strong>
                        </td>
                      </tr>
                    ) : null}
                    <tr>
                      <td className="mono" title={meta.description}>
                        <span>{row.key}</span>
                        {meta.description ? (
                          <div className="section__subtitle" style={{ margin: "4px 0 0", maxWidth: 360 }}>
                            {meta.description}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <input
                          className="input mono"
                          value={row.value}
                          placeholder={meta.default_value !== "" ? meta.default_value : "—"}
                          onChange={(event) => updateRow(row.id, { value: event.target.value })}
                          autoComplete="off"
                          aria-label={`Значение ${row.key}`}
                        />
                      </td>
                      <td className="mono section__subtitle" style={{ whiteSpace: "nowrap" }}>
                        {meta.default_value !== "" ? meta.default_value : "—"}
                      </td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn"
            onClick={() => onChange(applyDefaultsToEmptyFields(rows, schemaRows))}
          >
            Подставить дефолты в пустые поля
          </button>
        </div>
      </div>
    );
  }

  return <ParameterRowsLegacy rows={rows} onChange={onChange} />;
}
