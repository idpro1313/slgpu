interface StatusBadgeProps {
  status: string;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const normalised = (status || "unknown").toLowerCase();
  return <span className={`badge badge--${normalised}`}>{label ?? status}</span>;
}
