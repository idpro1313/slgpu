/** Полоса заполнения VRAM (MiB → процент ширины). */

interface VramBarProps {
  /** 0–100 */
  pct: number;
  height?: number;
  borderRadius?: number;
  marginTop?: number;
  className?: string;
}

export function VramBar({
  pct,
  height = 6,
  borderRadius = 3,
  marginTop = 4,
  className = "gpu-vram-bar",
}: VramBarProps) {
  const safePct = Math.min(100, Math.max(0, pct));
  return (
    <div
      className={className}
      style={{
        marginTop,
        height,
        borderRadius,
        background: "var(--color-border)",
      }}
      aria-hidden
    >
      <div
        style={{
          width: `${safePct}%`,
          height: "100%",
          borderRadius,
          background: "var(--color-accent)",
        }}
      />
    </div>
  );
}
