// Hand-written typed client for the Quant Pilot API (no codegen step to break).
// API base is baked at build time (VITE_API_BASE) or defaults to localhost:8000.

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export interface Health {
  status: string;
  service: string;
  version: string;
}

export interface Readiness {
  status: string;
  database: string;
  redis: string;
  trading_enabled: boolean;
}

export interface BacktestRun {
  id: string;
  status: string;
  params: Record<string, unknown>;
  metrics: Record<string, unknown> | null;
  error: string | null;
  requested_at: string;
  finished_at: string | null;
}

export interface SubmitOut {
  run_id: string;
  job_id: string;
  status: string;
}

export interface UniverseMember {
  symbol: string;
  index: string;
  effective_from: string;
  effective_to: string | null;
}

export interface Bar {
  date: string;
  open: number;
  high: number | null;
  low: number | null;
  close: number;
  adj_close: number | null;
  volume: number | null;
}

export interface EquityPoint {
  date: string;
  equity: number;
  drawdown: number;
  benchmark?: number | null;
}

export const api = {
  health: () => get<Health>("/health"),
  readiness: () => get<Readiness>("/api/v1/system/health"),
  listBacktests: () => get<BacktestRun[]>("/api/v1/backtests"),
  getBacktest: (id: string) => get<BacktestRun>(`/api/v1/backtests/${id}`),
  submitBacktest: (strategy: string, params: Record<string, unknown>) =>
    post<SubmitOut>("/api/v1/backtests", { strategy, params }),
  universe: (index: string, asOf: string) =>
    get<UniverseMember[]>(`/api/v1/universes/${index}/members?as_of=${asOf}`),
  ingestOhlcv: (symbols: string[], start: string, end: string) =>
    post<{ job_id: string }>("/api/v1/data/ohlcv", { symbols, start, end }),
  getBars: (symbol: string, start: string, end: string) =>
    get<Bar[]>(`/api/v1/data/ohlcv/${symbol}?start=${start}&end=${end}`),
  getEquity: (runId: string) => get<EquityPoint[]>(`/api/v1/backtests/${runId}/equity`),
};
