// Small presentational component library + formatters (no external deps).
import type { ReactNode } from "react";

export const fmt = {
  pct: (x: number | undefined | null) => (x == null ? "—" : `${(x * 100).toFixed(2)}%`),
  num: (x: number | undefined | null, d = 2) => (x == null ? "—" : x.toFixed(d)),
  money: (x: number | undefined | null) =>
    x == null ? "—" : `₹${Math.round(x).toLocaleString("en-IN")}`,
  compact: (x: number | undefined | null) =>
    x == null ? "—" : Intl.NumberFormat("en-IN", { notation: "compact" }).format(x),
};

export function Card({
  title,
  actions,
  children,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="card">
      {(title || actions) && (
        <div className="card-head">
          {title && <h3>{title}</h3>}
          {actions && <div className="card-actions">{actions}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </div>
  );
}

export function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "neutral";
}) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${tone}`}>{value}</div>
    </div>
  );
}

export function tone(x: number | undefined | null): "pos" | "neg" | "neutral" {
  if (x == null || x === 0) return "neutral";
  return x > 0 ? "pos" : "neg";
}

export function Badge({ status }: { status: string }) {
  const cls =
    status === "succeeded" || status === "ok"
      ? "ok"
      : status === "failed" || status === "down"
        ? "bad"
        : "warn";
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function Dot({ ok }: { ok: boolean }) {
  return <span className={`dot ${ok ? "ok" : "bad"}`} />;
}

export function Spinner() {
  return <span className="spinner" aria-label="loading" />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

// Lightweight SVG line chart (equity / price / drawdown). Scales via viewBox.
export function LineChart({
  values,
  height = 200,
  stroke = "#5b9cff",
  area = true,
  baseline,
}: {
  values: number[];
  height?: number;
  stroke?: string;
  area?: boolean;
  baseline?: number;
}) {
  if (values.length < 2) return <Empty>not enough data to chart</Empty>;
  const w = 800;
  const h = height;
  const pad = 10;
  const lo = Math.min(...values, baseline ?? Infinity);
  const hi = Math.max(...values, baseline ?? -Infinity);
  const span = hi - lo || 1;
  const x = (i: number) => (i / (values.length - 1)) * (w - 2 * pad) + pad;
  const y = (v: number) => h - pad - ((v - lo) / span) * (h - 2 * pad);
  const line = values.map((v, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const areaD = `${line} L ${x(values.length - 1).toFixed(1)} ${h - pad} L ${x(0).toFixed(1)} ${h - pad} Z`;
  const gid = `g-${stroke.replace("#", "")}`;
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      {baseline != null && (
        <line x1={pad} x2={w - pad} y1={y(baseline)} y2={y(baseline)} className="chart-baseline" />
      )}
      {area && <path d={areaD} fill={`url(#${gid})`} />}
      <path d={line} fill="none" stroke={stroke} strokeWidth={2} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
