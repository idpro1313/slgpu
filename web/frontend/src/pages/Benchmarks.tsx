import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { BenchRun, JobAccepted, RuntimeSnapshot } from "@/api/types";
import { BenchSummaryView } from "@/components/BenchSummaryView";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Section } from "@/components/Section";

export function BenchmarksPage() {
  const queryClient = useQueryClient();
  const appliedRuntimeKey = useRef<string | null>(null);
  const [detailRun, setDetailRun] = useState<BenchRun | null>(null);
  const [scenarioEngine, setScenarioEngine] = useState("vllm");
  const [scenarioPreset, setScenarioPreset] = useState("");
  const [scenarioRounds, setScenarioRounds] = useState(1);
  const [scenarioWarmup, setScenarioWarmup] = useState(3);
  const [loadEngine, setLoadEngine] = useState("vllm");
  const [loadPreset, setLoadPreset] = useState("");
  const [loadUsers, setLoadUsers] = useState(250);
  const [loadDuration, setLoadDuration] = useState(900);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runtime = useQuery({
    queryKey: ["runtime-snapshot"],
    queryFn: ({ signal }) => api.get<RuntimeSnapshot>("/runtime/snapshot", { signal }),
    refetchInterval: 8_000,
  });

  useEffect(() => {
    const s = runtime.data;
    if (!s) {
      return;
    }
    if (!s.engine) {
      appliedRuntimeKey.current = null;
      return;
    }
    if (!s.preset_name?.trim()) {
      return;
    }
    const eng = s.engine;
    const preset = s.preset_name.trim();
    const key = `${eng}\0${preset}`;
    if (appliedRuntimeKey.current === key) {
      return;
    }
    appliedRuntimeKey.current = key;
    setScenarioEngine(eng);
    setLoadEngine(eng);
    setScenarioPreset(preset);
    setLoadPreset(preset);
  }, [runtime.data]);

  const runs = useQuery({
    queryKey: ["bench", "runs"],
    queryFn: ({ signal }) => api.get<BenchRun[]>("/bench/runs", { signal }),
    refetchInterval: 8_000,
  });

  const summary = useQuery({
    queryKey: ["bench", "summary", detailRun?.engine, detailRun?.timestamp],
    queryFn: ({ signal }) =>
      api.get<Record<string, unknown>>(
        `/bench/runs/${detailRun!.engine}/${detailRun!.timestamp}/summary`,
        { signal },
      ),
    enabled: Boolean(detailRun),
  });

  const scenarioMut = useMutation({
    mutationFn: () =>
      api.post<JobAccepted>("/bench/scenario", {
        engine: scenarioEngine,
        preset: scenarioPreset,
        rounds: scenarioRounds,
        warmup_requests: scenarioWarmup,
      }),
    onSuccess: (data) => {
      setError(null);
      setMessage(`Задача бенча #${data.job_id} поставлена в очередь.`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (err: Error) => {
      setMessage(null);
      setError(err.message);
    },
  });

  const loadMut = useMutation({
    mutationFn: () =>
      api.post<JobAccepted>("/bench/load", {
        engine: loadEngine,
        preset: loadPreset,
        users: loadUsers,
        duration: loadDuration,
        ramp_up: 120,
        ramp_down: 60,
        think_time: "2000,5000",
        max_prompt: 512,
        max_output: 256,
        report_interval: 5,
        warmup_requests: 3,
        burst: false,
      }),
    onSuccess: (data) => {
      setError(null);
      setMessage(`Load-тест #${data.job_id} поставлен в очередь (долгий прогон).`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (err: Error) => {
      setMessage(null);
      setError(err.message);
    },
  });

  function onScenario(event: FormEvent) {
    event.preventDefault();
    if (!scenarioPreset.trim()) {
      setError(
        "Укажите пресет (slug) или поднимите Inference с пресетом — поля подставятся из runtime.",
      );
      return;
    }
    scenarioMut.mutate();
  }

  function onLoad(event: FormEvent) {
    event.preventDefault();
    if (!loadPreset.trim()) {
      setError(
        "Укажите пресет (slug) или поднимите Inference с пресетом — поля подставятся из runtime.",
      );
      return;
    }
    loadMut.mutate();
  }

  return (
    <>
      <PageHeader
        title="Бенчмарки"
        subtitle="Прогоны scenario (`bench_openai.py`) и load (`bench_load.py`) через API; артефакты в `data/bench/results/` на хосте. Движок и пресет подставляются из текущего запуска Inference (`/runtime/snapshot`), если известны."
      />

      {runtime.data?.engine && runtime.data.preset_name?.trim() ? (
        <p className="muted" style={{ marginTop: 0 }}>
          Текущий runtime: <span className="mono">{runtime.data.engine}</span>, пресет{" "}
          <span className="mono">{runtime.data.preset_name.trim()}</span>
          {runtime.isFetching ? " (обновление…)" : ""}.
        </p>
      ) : runtime.isSuccess ? (
        <p className="muted" style={{ marginTop: 0 }}>
          Нет пары «движок + пресет» в snapshot (запустите Inference и выберите пресет, либо введите slug
          вручную).
        </p>
      ) : null}

      {message ? <p style={{ color: "var(--color-success)" }}>{message}</p> : null}
      {error ? <p style={{ color: "var(--color-danger)" }}>{error}</p> : null}

      <Section title="Запуск scenario" subtitle="Короткая матрица сценариев; пресет задаёт MAX_MODEL_LEN и имя модели для бенча.">
        <form className="flex flex--col flex--gap-md" onSubmit={onScenario}>
          <div className="flex flex--gap-md flex--wrap">
            <label>
              <span className="label">Движок</span>
              <select
                className="input"
                value={scenarioEngine}
                onChange={(e) => setScenarioEngine(e.target.value)}
              >
                <option value="vllm">vllm</option>
                <option value="sglang">sglang</option>
              </select>
            </label>
            <label>
              <span className="label">Пресет (slug)</span>
              <input
                className="input"
                value={scenarioPreset}
                onChange={(e) => setScenarioPreset(e.target.value)}
                placeholder="qwen3.6-35b-a3b"
              />
            </label>
            <label>
              <span className="label">Раунды</span>
              <input
                className="input"
                type="number"
                min={1}
                value={scenarioRounds}
                onChange={(e) => setScenarioRounds(Number(e.target.value))}
              />
            </label>
            <label>
              <span className="label">Warmup запросов</span>
              <input
                className="input"
                type="number"
                min={0}
                value={scenarioWarmup}
                onChange={(e) => setScenarioWarmup(Number(e.target.value))}
              />
            </label>
          </div>
          <button type="submit" className="btn btn--primary" disabled={scenarioMut.isPending}>
            {scenarioMut.isPending ? "Отправка…" : "Запустить scenario"}
          </button>
        </form>
      </Section>

      <Section
        title="Запуск load"
        subtitle="Длительный нагрузочный тест; по умолчанию 250 пользователей, steady 900 с (как в CLI). Прогресс — в «Задачи»."
      >
        <form className="flex flex--col flex--gap-md" onSubmit={onLoad}>
          <div className="flex flex--gap-md flex--wrap">
            <label>
              <span className="label">Движок</span>
              <select
                className="input"
                value={loadEngine}
                onChange={(e) => setLoadEngine(e.target.value)}
              >
                <option value="vllm">vllm</option>
                <option value="sglang">sglang</option>
              </select>
            </label>
            <label>
              <span className="label">Пресет (slug)</span>
              <input
                className="input"
                value={loadPreset}
                onChange={(e) => setLoadPreset(e.target.value)}
                placeholder="qwen3.6-35b-a3b"
              />
            </label>
            <label>
              <span className="label">Пользователи</span>
              <input
                className="input"
                type="number"
                min={1}
                value={loadUsers}
                onChange={(e) => setLoadUsers(Number(e.target.value))}
              />
            </label>
            <label>
              <span className="label">Steady, сек</span>
              <input
                className="input"
                type="number"
                min={60}
                value={loadDuration}
                onChange={(e) => setLoadDuration(Number(e.target.value))}
              />
            </label>
          </div>
          <button type="submit" className="btn btn--ghost" disabled={loadMut.isPending}>
            {loadMut.isPending ? "Отправка…" : "Запустить load"}
          </button>
        </form>
      </Section>

      <Section
        title="Прогоны на диске"
        subtitle="Каталоги из `data/bench/results` (обновление каждые 8 с). Нажмите строку — откроется отчёт."
      >
        {runs.isLoading ? (
          <div className="empty-state">Загружаем…</div>
        ) : !runs.data?.length ? (
          <div className="empty-state">Пока нет каталогов с summary.json.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>Движок</th>
                  <th>Метка времени</th>
                  <th>Тип</th>
                  <th>Путь</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr
                    key={`${r.engine}-${r.timestamp}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => setDetailRun(r)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setDetailRun(r);
                      }
                    }}
                    style={{
                      cursor: "pointer",
                      background:
                        detailRun?.engine === r.engine && detailRun?.timestamp === r.timestamp
                          ? "rgba(148, 203, 255, 0.22)"
                          : undefined,
                    }}
                  >
                    <td>{r.engine}</td>
                    <td className="mono">{r.timestamp}</td>
                    <td>{r.kind}</td>
                    <td className="mono">{r.path}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Modal
        title={detailRun ? `Результаты · ${detailRun.kind}` : "Результаты"}
        subtitle={
          detailRun ? `${detailRun.engine} · ${detailRun.timestamp} · ${detailRun.path}` : null
        }
        isOpen={Boolean(detailRun)}
        onClose={() => setDetailRun(null)}
        size="wide"
      >
        {!detailRun ? null : summary.isLoading ? (
          <div className="empty-state">Загружаем summary…</div>
        ) : summary.isError ? (
          <div className="empty-state">Не удалось загрузить summary.json.</div>
        ) : summary.data ? (
          <BenchSummaryView data={summary.data} />
        ) : (
          <div className="empty-state">Нет данных.</div>
        )}
      </Modal>
    </>
  );
}
