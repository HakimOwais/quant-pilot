// Small presentational component library + formatters (no external deps).
import { useEffect, useState, type ReactNode } from "react";

export const fmt = {
  pct: (x: number | undefined | null) => (x == null ? "—" : `${(x * 100).toFixed(2)}%`),
  num: (x: number | undefined | null, d = 2) => (x == null ? "—" : x.toFixed(d)),
  money: (x: number | undefined | null) =>
    x == null ? "—" : `₹${Math.round(x).toLocaleString("en-IN")}`,
};

export function tone(x: number | undefined | null): "pos" | "neg" | "neutral" {
  if (x == null || x === 0) return "neutral";
  return x > 0 ? "pos" : "neg";
}

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
  tone: t = "neutral",
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "neutral";
}) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${t}`}>{value}</div>
    </div>
  );
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

// ---------- toasts ----------
export function toast(message: string): void {
  window.dispatchEvent(new CustomEvent("qp-toast", { detail: message }));
}

export function Toaster() {
  const [items, setItems] = useState<{ id: number; msg: string }[]>([]);
  useEffect(() => {
    const handler = (e: Event) => {
      const msg = (e as CustomEvent<string>).detail;
      const id = Date.now() + Math.random();
      setItems((xs) => [...xs, { id, msg }]);
      setTimeout(() => setItems((xs) => xs.filter((i) => i.id !== id)), 3200);
    };
    window.addEventListener("qp-toast", handler);
    return () => window.removeEventListener("qp-toast", handler);
  }, []);
  return (
    <div className="toaster">
      {items.map((i) => (
        <div key={i.id} className="toast">
          {i.msg}
        </div>
      ))}
    </div>
  );
}

// ---------- interactive line chart (hover crosshair + tooltip + axes) ----------
export interface ChartPoint {
  label: string;
  value: number;
}

export function Chart({
  points,
  overlay,
  height = 200,
  stroke = "#5b9cff",
  overlayStroke = "#8b95a7",
  area = true,
  baseline,
  legend,
  format = (v) => v.toFixed(2),
}: {
  points: ChartPoint[];
  overlay?: ChartPoint[];
  height?: number;
  stroke?: string;
  overlayStroke?: string;
  area?: boolean;
  baseline?: number;
  legend?: [string, string];
  format?: (v: number) => string;
}) {
  const [hi, setHi] = useState<number | null>(null);
  if (points.length < 2) return <Empty>not enough data to chart</Empty>;

  const w = 800;
  const h = height;
  const pad = 10;
  const allValues = [...points.map((p) => p.value), ...(overlay?.map((p) => p.value) ?? [])];
  const lo = Math.min(...allValues, baseline ?? Infinity);
  const top = Math.max(...allValues, baseline ?? -Infinity);
  const span = top - lo || 1;
  const x = (i: number) => (i / (points.length - 1)) * (w - 2 * pad) + pad;
  const y = (v: number) => h - pad - ((v - lo) / span) * (h - 2 * pad);
  const path = (pts: ChartPoint[]) =>
    pts.map((p, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  const line = path(points);
  const areaD = `${line} L ${x(points.length - 1).toFixed(1)} ${h - pad} L ${x(0).toFixed(1)} ${h - pad} Z`;
  const gid = `g-${stroke.replace("#", "")}`;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - r.left) / r.width;
    setHi(Math.max(0, Math.min(points.length - 1, Math.round(frac * (points.length - 1)))));
  };

  const cur = hi != null ? points[hi] : null;
  const curOverlay = hi != null && overlay && hi < overlay.length ? overlay[hi] : null;
  const tipLeft = hi != null ? (hi / (points.length - 1)) * 100 : 0;

  return (
    <div className="chart-wrap" style={{ height }}>
      {legend && (
        <div className="chart-legend">
          <span>
            <i style={{ background: stroke }} /> {legend[0]}
          </span>
          <span>
            <i style={{ background: overlayStroke }} /> {legend[1]}
          </span>
        </div>
      )}
      <svg
        className="chart"
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        onMouseMove={onMove}
        onMouseLeave={() => setHi(null)}
        role="img"
      >
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
        {overlay && overlay.length > 1 && (
          <path
            d={path(overlay)}
            fill="none"
            stroke={overlayStroke}
            strokeWidth={1.5}
            strokeDasharray="5 4"
            vectorEffect="non-scaling-stroke"
          />
        )}
        <path d={line} fill="none" stroke={stroke} strokeWidth={2} vectorEffect="non-scaling-stroke" />
        {hi != null && (
          <line x1={x(hi)} x2={x(hi)} y1={pad} y2={h - pad} className="chart-cross" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      <div className="chart-yaxis">
        <span>{format(top)}</span>
        <span>{format(lo)}</span>
      </div>
      <div className="chart-xaxis">
        <span>{points[0].label}</span>
        <span>{points[points.length - 1].label}</span>
      </div>
      {cur && (
        <div className="chart-tip" style={{ left: `${tipLeft}%` }}>
          <div className="tip-val">{format(cur.value)}</div>
          {curOverlay && <div className="tip-val2">{format(curOverlay.value)}</div>}
          <div className="tip-lab">{cur.label}</div>
        </div>
      )}
    </div>
  );
}
