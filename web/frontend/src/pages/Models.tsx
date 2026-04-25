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

const EMPTY_FORM: AddModelForm = { hf_id: "", revision: "", notes: "" };

export function ModelsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<AddModelForm>(EMPTY_FORM);
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
