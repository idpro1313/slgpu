interface MetricCardProps {
  label: string;
  value: string | number;
  hint?: string;
  accent?: boolean;
}

export function MetricCard({ label, value, hint, accent }: MetricCardProps) {
  return (
    <div className={`metric-card${accent ? " metric-card--accent" : ""}`}>
      <div className="metric-card__label">{label}</div>
      <div className="metric-card__value">{value}</div>
      {hint ? <div className="metric-card__hint">{hint}</div> : null}
    </div>
  );
}
