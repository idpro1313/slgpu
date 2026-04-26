import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { HFModel, JobAccepted } from "@/api/types";
import { formatBytes, formatDate } from "@/components/formatters";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";

interface AddModelForm {
  hf_id: string;
  revision: string;
  notes: string;
}

interface ModelEditorForm {
  revision: string;
  notes: string;
}

const EMPTY_FORM: AddModelForm = { hf_id: "", revision: "", notes: "" };

function editorFromModel(model: HFModel): ModelEditorForm {
  return {
    revision: model.revision ?? "",
    notes: model.notes ?? "",
  };
}

function isModelEditorDirty(editor: ModelEditorForm, model: HFModel): boolean {
  return (
    editor.revision !== (model.revision ?? "") || editor.notes !== (model.notes ?? "")
  );
}

export function ModelsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<AddModelForm>(EMPTY_FORM);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editor, setEditor] = useState<ModelEditorForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pulling, setPulling] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["models"],
    queryFn: () => api.get<HFModel[]>("/models"),
    refetchInterval: 8_000,
  });

  const addModel = useMutation({
    mutationFn: (payload: AddModelForm) =>
      api.post<HFModel>("/models", {
        hf_id: payload.hf_id,
        revision: payload.revision || null,
        notes: payload.notes || null,
      }),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const pullModel = useMutation({
    mutationFn: ({ id, revision }: { id: number; revision: string | null }) =>
      api.post<JobAccepted>(`/models/${id}/pull`, { revision }),
    onSuccess: (_, variables) => {
      setPulling(variables.id);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["models"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      window.setTimeout(() => setPulling(null), 1500);
    },
    onError: (err: Error) => setError(err.message),
  });

  const updateModel = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ModelEditorForm }) =>
      api.patch<HFModel>(`/models/${id}`, {
        revision: payload.revision || null,
        notes: payload.notes || null,
      }),
    onSuccess: (model) => {
      setError(null);
      setSelectedId(model.id);
      setEditor(editorFromModel(model));
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const deleteModel = useMutation({
    mutationFn: ({ id, deleteFiles }: { id: number; deleteFiles: boolean }) =>
      api.delete<{ deleted: boolean }>(`/models/${id}?delete_files=${deleteFiles ? "true" : "false"}`),
    onSuccess: () => {
      setError(null);
      setSelectedId(null);
      setEditor(null);
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const selectedModel = data?.find((model) => model.id === selectedId) ?? null;

  const cancelModelEdit = () => {
    if (!selectedModel || !editor) return;
    if (isModelEditorDirty(editor, selectedModel)) {
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

  return (
    <>
      <PageHeader
        title="Модели Hugging Face"
        subtitle="Реестр моделей. Загрузка идёт через ./slgpu pull, прогресс — на вкладке Задачи."
      />

      <Section
        title="Добавить модель"
        subtitle="Введите Hugging Face id вида org/repo. Revision и заметки опциональны."
      >
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            if (!form.hf_id.trim()) return;
            addModel.mutate(form);
          }}
        >
          <div>
            <label className="label" htmlFor="hf_id">
              HF ID
            </label>
            <input
              id="hf_id"
              className="input"
              placeholder="Qwen/Qwen3.6-35B-A3B"
              value={form.hf_id}
              onChange={(event) => setForm({ ...form, hf_id: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="rev">
              Revision
            </label>
            <input
              id="rev"
              className="input"
              placeholder="optional commit/tag"
              value={form.revision}
              onChange={(event) => setForm({ ...form, revision: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="notes">
              Заметка
            </label>
            <input
              id="notes"
              className="input"
              placeholder="зачем эта модель"
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
            />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button
              type="submit"
              className="btn btn--primary"
              disabled={addModel.isPending || !form.hf_id.trim()}
            >
              {addModel.isPending ? "Добавляем…" : "Зарегистрировать"}
            </button>
          </div>
        </form>
        {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}
      </Section>

      <Section
        title="Изменить модель"
        subtitle="Редактируется карточка модели в web-реестре: revision и заметка. HF ID и slug не меняются."
      >
        {!selectedModel || !editor ? (
          <div className="empty-state">Выберите модель в таблице ниже.</div>
        ) : (
          <>
            <div className="form-grid">
              <div>
                <label className="label">HF ID</label>
                <input className="input mono" value={selectedModel.hf_id} disabled />
              </div>
              <div>
                <label className="label">Revision</label>
                <input
                  className="input"
                  value={editor.revision}
                  onChange={(event) => setEditor({ ...editor, revision: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Заметка</label>
                <input
                  className="input"
                  value={editor.notes}
                  onChange={(event) => setEditor({ ...editor, notes: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Локальный путь</label>
                <input className="input mono" value={selectedModel.local_path ?? "—"} disabled />
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 16 }}>
              <button
                type="button"
                className="btn btn--primary"
                disabled={updateModel.isPending}
                onClick={() => updateModel.mutate({ id: selectedModel.id, payload: editor })}
              >
                {updateModel.isPending ? "Сохраняем…" : "Сохранить"}
              </button>
              <button type="button" className="btn btn--ghost" onClick={cancelModelEdit}>
                Отмена
              </button>
              <button
                type="button"
                className="btn btn--danger"
                disabled={deleteModel.isPending}
                onClick={() => {
                  if (window.confirm(`Удалить ${selectedModel.hf_id} только из web-реестра?`)) {
                    deleteModel.mutate({ id: selectedModel.id, deleteFiles: false });
                  }
                }}
              >
                Удалить из реестра
              </button>
              <button
                type="button"
                className="btn btn--danger"
                disabled={deleteModel.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `Удалить ${selectedModel.hf_id} из реестра и стереть локальную папку весов?`,
                    )
                  ) {
                    deleteModel.mutate({ id: selectedModel.id, deleteFiles: true });
                  }
                }}
              >
                Удалить с диска
              </button>
            </div>
          </>
        )}
      </Section>

      <Section
        title="Реестр моделей"
        subtitle="Состояние локального диска синхронизируется при каждом запросе."
      >
        {isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !data || data.length === 0 ? (
          <div className="empty-state">Моделей пока нет — добавьте первую.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>HF ID</th>
                  <th>Slug</th>
                  <th>Статус</th>
                  <th>Размер</th>
                  <th>Попытки</th>
                  <th>Последнее</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {data.map((model) => (
                  <tr key={model.id}>
                    <td className="mono">{model.hf_id}</td>
                    <td className="mono">{model.slug}</td>
                    <td>
                      <StatusBadge status={model.download_status} />
                    </td>
                    <td>{formatBytes(model.size_bytes)}</td>
                    <td>{model.attempts}</td>
                    <td>{formatDate(model.last_pulled_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--ghost"
                        onClick={() => {
                          setSelectedId(model.id);
                          setEditor(editorFromModel(model));
                        }}
                      >
                        Открыть
                      </button>{" "}
                      <button
                        type="button"
                        className="btn btn--primary"
                        onClick={() =>
                          pullModel.mutate({ id: model.id, revision: model.revision })
                        }
                        disabled={pullModel.isPending || pulling === model.id}
                      >
                        {pulling === model.id ? "Запущено" : "Скачать / докачать"}
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
