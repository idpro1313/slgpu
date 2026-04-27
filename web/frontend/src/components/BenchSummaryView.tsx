/** Визуализация summary.json прогонов bench_openai / bench_load. */

import type { ReactNode } from "react";

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return null;
}

function str(v: unknown): string | null {
  if (typeof v === "string" && v.length) return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return null;
}

function fmtFloat(v: unknown, digits = 2): string {
  const n = num(v);
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

/** bench_load: миллисекунды */
function fmtMs(v: unknown): string {
  const n = num(v);
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(1)} ms`;
}

/** bench_openai: секунды → ms */
function fmtSecAsMs(v: unknown): string {
  const n = num(v);
  if (n == null || n < 0 || Number.isNaN(n)) return "—";
  return `${(n * 1000).toFixed(1)} ms`;
}

function fmtRps(v: unknown): string {
  const n = num(v);
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}`;
}

function fmtErrRate(v: unknown): string {
  const n = num(v);
  if (n == null || Number.isNaN(n)) return "—";
  if (n <= 1 && n >= 0) return `${(n * 100).toFixed(2)} %`;
  return `${n.toFixed(2)} %`;
}

function isLoadSummary(d: Record<string, unknown>): boolean {
  return typeof d.users === "number" && typeof d.total_requests === "number";
}

function isScenarioSummary(d: Record<string, unknown>): boolean {
  return Array.isArray(d.scenarios);
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="bench-summary__section-title">{children}</h3>;
}

function MetaLine({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bench-summary__meta">
      <span className="bench-summary__meta-label">{label}</span>
      <span className="bench-summary__meta-value">{value}</span>
    </div>
  );
}

function LoadSummaryBody({ data }: { data: Record<string, unknown> }) {
  const phases = data.phases_summary;
  const phaseEntries =
    phases && typeof phases === "object" && !Array.isArray(phases)
      ? Object.entries(phases as Record<string, unknown>)
      : [];

  return (
    <>
      <div className="bench-summary__meta-grid">
        <MetaLine label="Модель" value={<span className="mono">{str(data.model) ?? "—"}</span>} />
        <MetaLine label="Engine" value={<span className="mono">{str(data.engine) ?? "—"}</span>} />
        <MetaLine
          label="Base URL"
          value={<span className="mono bench-summary__break">{str(data.base_url) ?? "—"}</span>}
        />
        <MetaLine label="Время (UTC)" value={<span className="mono">{str(data.timestamp) ?? "—"}</span>} />
      </div>

      <div className="metric-grid" style={{ marginBottom: 12 }}>
        <div className="metric-card metric-card--accent">
          <span className="metric-card__label">Throughput</span>
          <span className="metric-card__value" style={{ fontSize: "1.65rem" }}>
            {fmtRps(data.throughput_rps)}
          </span>
          <span className="metric-card__hint">запросов / с</span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Генерация</span>
          <span className="metric-card__value" style={{ fontSize: "1.65rem" }}>
            {fmtFloat(data.tokens_per_sec, 1)}
          </span>
          <span className="metric-card__hint">токенов / с</span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Ошибки</span>
          <span className="metric-card__value" style={{ fontSize: "1.65rem" }}>
            {fmtErrRate(data.error_rate)}
          </span>
          <span className="metric-card__hint">
            {num(data.err_requests) ?? 0} из {num(data.total_requests) ?? "—"}
          </span>
        </div>
      </div>

      <SectionTitle>Задержки (итог прогона)</SectionTitle>
      <div className="bench-summary__kv-grid">
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">TTFT p50</span>
          <span className="bench-summary__kv-v">{fmtMs(data.ttft_p50_ms)}</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">TTFT p95</span>
          <span className="bench-summary__kv-v">{fmtMs(data.ttft_p95_ms)}</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Latency p50</span>
          <span className="bench-summary__kv-v">{fmtMs(data.latency_p50_ms)}</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Latency p95</span>
          <span className="bench-summary__kv-v">{fmtMs(data.latency_p95_ms)}</span>
        </div>
      </div>

      <SectionTitle>Нагрузка</SectionTitle>
      <div className="bench-summary__kv-grid">
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Пользователи</span>
          <span className="bench-summary__kv-v">{str(data.users) ?? "—"}</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Ramp up</span>
          <span className="bench-summary__kv-v">{fmtFloat(data.ramp_up_sec, 0)} с</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Steady</span>
          <span className="bench-summary__kv-v">{fmtFloat(data.steady_sec, 0)} с</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Ramp down</span>
          <span className="bench-summary__kv-v">{fmtFloat(data.ramp_down_sec, 0)} с</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Фактическая длительность</span>
          <span className="bench-summary__kv-v">{fmtFloat(data.total_duration_sec, 1)} с</span>
        </div>
      </div>

      <SectionTitle>Запросы</SectionTitle>
      <div className="bench-summary__kv-grid">
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Всего</span>
          <span className="bench-summary__kv-v">{str(data.total_requests) ?? "—"}</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">Успешно</span>
          <span className="bench-summary__kv-v">{str(data.ok_requests) ?? "—"}</span>
        </div>
        <div className="bench-summary__kv">
          <span className="bench-summary__kv-k">С ошибкой</span>
          <span className="bench-summary__kv-v">{str(data.err_requests) ?? "—"}</span>
        </div>
      </div>

      {phaseEntries.length > 0 ? (
        <>
          <SectionTitle>Сводка по фазам</SectionTitle>
          <pre className="bench-summary__raw">{JSON.stringify(phases, null, 2)}</pre>
        </>
      ) : null}
    </>
  );
}

function ScenarioSummaryBody({ data }: { data: Record<string, unknown> }) {
  const scenarios = data.scenarios as Record<string, unknown>[];

  return (
    <>
      <div className="bench-summary__meta-grid">
        <MetaLine label="Модель" value={<span className="mono">{str(data.model) ?? "—"}</span>} />
        <MetaLine label="Engine" value={<span className="mono">{str(data.engine) ?? "—"}</span>} />
        <MetaLine
          label="Base URL"
          value={<span className="mono bench-summary__break">{str(data.base_url) ?? "—"}</span>}
        />
        <MetaLine label="Время (UTC)" value={<span className="mono">{str(data.timestamp) ?? "—"}</span>} />
      </div>

      <SectionTitle>Матрица сценариев</SectionTitle>
      <div style={{ overflowX: "auto" }}>
        <table className="table table--compact bench-summary__table">
          <thead>
            <tr>
              <th>Сценарий</th>
              <th>Concurrency</th>
              <th>TTFT p50</th>
              <th>TTFT p95</th>
              <th>Общее время (ср.)</th>
              <th>Out tok (ср.)</th>
              <th>RPS</th>
              <th>Ошибки</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((row, i) => (
              <tr key={`${str(row.name) ?? i}-${i}`}>
                <td className="mono">{str(row.name) ?? "—"}</td>
                <td>{str(row.concurrency) ?? "—"}</td>
                <td>{fmtSecAsMs(row.ttft_s_p50)}</td>
                <td>{fmtSecAsMs(row.ttft_s_p95)}</td>
                <td>{fmtFloat(row.total_s_mean, 3)} с</td>
                <td>{fmtFloat(row.out_tokens_mean, 1)}</td>
                <td>{fmtRps(row.rps)}</td>
                <td>{str(row.errors) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function RawFallback({ data }: { data: Record<string, unknown> }) {
  return (
    <div>
      <p className="muted" style={{ marginTop: 0 }}>
        Неизвестный формат summary — сырой JSON:
      </p>
      <pre className="bench-summary__raw">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

export function BenchSummaryView({ data }: { data: Record<string, unknown> }) {
  if (isScenarioSummary(data)) {
    return <ScenarioSummaryBody data={data} />;
  }
  if (isLoadSummary(data)) {
    return <LoadSummaryBody data={data} />;
  }
  return <RawFallback data={data} />;
}
