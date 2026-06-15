import { useEffect, useState } from "react";

import {
  api,
  type Bar,
  type BacktestRun,
  type EquityPoint,
  type Readiness,
  type UniverseMember,
} from "./api";
import { Badge, Card, Chart, Dot, Empty, fmt, Metric, Spinner, Toaster, toast, tone } from "./ui";

type Tab = "overview" | "data" | "backtests" | "universe";
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "data", label: "Data" },
  { id: "backtests", label: "Backtests" },
  { id: "universe", label: "Universe" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◆</span> Quant Pilot
        </div>
        <nav>
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "nav active" : "nav"} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">NSE / BSE · paper</div>
      </aside>
      <main className="content">
        {tab === "overview" && <Overview />}
        {tab === "data" && <Data />}
        {tab === "backtests" && <Backtests />}
        {tab === "universe" && <Universe />}
      </main>
      <Toaster />
    </div>
  );
}

function Overview() {
  const [live, setLive] = useState<string>("…");
  const [ready, setReady] = useState<Readiness | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setErr(null);
    try {
      const h = await api.health();
      setLive(`${h.service} v${h.version}`);
      setReady(await api.readiness());
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <>
      <PageHead title="Overview" onRefresh={() => void load()} />
      {err && <p className="error">{err}</p>}
      <div className="cards">
        <Card title="API">
          <div className="status-line">
            <Dot ok={!!ready} /> {live}
          </div>
          <div className="muted">readiness: {ready?.status ?? "…"}</div>
        </Card>
        <Card title="Dependencies">
          <div className="status-line">
            <Dot ok={ready?.database === "ok"} /> database — {ready?.database ?? "…"}
          </div>
          <div className="status-line">
            <Dot ok={ready?.redis === "ok"} /> redis — {ready?.redis ?? "…"}
          </div>
        </Card>
        <Card title="Trading">
          <div className="status-line">
            <Dot ok={ready?.trading_enabled ?? false} />
            {ready?.trading_enabled ? "enabled" : "disabled (read-only)"}
          </div>
          <div className="muted">orders require trading_enabled + 2FA</div>
        </Card>
      </div>
    </>
  );
}

function Data() {
  const [symbols, setSymbols] = useState("RELIANCE.NS,TCS.NS,INFY.NS");
  const [start, setStart] = useState("2022-01-01");
  const [end, setEnd] = useState("2024-06-30");
  const [err, setErr] = useState<string | null>(null);
  const [viewSymbol, setViewSymbol] = useState("RELIANCE.NS");
  const [bars, setBars] = useState<Bar[]>([]);
  const [busy, setBusy] = useState(false);

  const syms = () => symbols.split(",").map((s) => s.trim()).filter(Boolean);

  const ingest = async () => {
    setErr(null);
    try {
      const r = await api.ingestOhlcv(syms(), start, end);
      toast(`Ingestion queued · job ${r.job_id.slice(0, 8)}`);
    } catch (e) {
      setErr(String(e));
    }
  };

  const loadBars = async () => {
    setErr(null);
    setBusy(true);
    try {
      setBars(await api.getBars(viewSymbol, start, end));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHead title="Data" />
      {err && <p className="error">{err}</p>}
      <Card title="Ingest OHLCV">
        <div className="form">
          <input value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="comma symbols" />
          <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="start" />
          <input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="end" />
          <button className="primary" onClick={() => void ingest()}>
            Ingest
          </button>
        </div>
      </Card>
      <Card
        title="Price"
        actions={
          <div className="form inline">
            <input value={viewSymbol} onChange={(e) => setViewSymbol(e.target.value)} />
            <button onClick={() => void loadBars()}>{busy ? <Spinner /> : "Load"}</button>
          </div>
        }
      >
        {bars.length > 1 ? (
          <>
            <Chart
              points={bars.map((b) => ({ label: b.date, value: b.close }))}
              format={(v) => fmt.num(v)}
            />
            <div className="muted">
              {bars.length} bars · last close {fmt.num(bars[bars.length - 1].close)}
            </div>
          </>
        ) : (
          <Empty>load a symbol to chart its close price</Empty>
        )}
      </Card>
    </>
  );
}

interface Metrics {
  summary: {
    total_return: number;
    total_costs: number;
    n_rebalances: number;
    final_equity: number;
    initial_capital: number;
  };
  performance: { cagr: number; sharpe: number; sortino: number; calmar: number; max_drawdown: number };
  significance: {
    deflated_sharpe: number;
    probabilistic_sharpe: number;
    p_value: number;
    ci_low: number;
    ci_high: number;
  };
  attribution?: {
    alpha_annual: number;
    alpha_tstat: number;
    alpha_significant: boolean;
    beta: number;
    r_squared: number;
    information_ratio: number;
  };
}

function Backtests() {
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [strategy, setStrategy] = useState("momentum");
  const [symbols, setSymbols] = useState("RELIANCE.NS,TCS.NS,INFY.NS");
  const [start, setStart] = useState("2022-01-01");
  const [end, setEnd] = useState("2024-06-30");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const rs = await api.listBacktests();
        if (alive) setRuns(rs);
      } catch (e) {
        if (alive) setErr(String(e));
      }
    };
    void tick();
    const h = setInterval(tick, 4000);
    return () => {
      alive = false;
      clearInterval(h);
    };
  }, []);

  const detail = selectedId ? (runs.find((r) => r.id === selectedId) ?? null) : null;

  useEffect(() => {
    if (detail?.status === "succeeded") {
      let alive = true;
      api.getEquity(detail.id).then((e) => alive && setEquity(e)).catch(() => undefined);
      return () => {
        alive = false;
      };
    }
    setEquity([]);
    return undefined;
  }, [detail?.id, detail?.status]);

  const submit = async () => {
    setErr(null);
    try {
      const params = {
        symbols: symbols.split(",").map((s) => s.trim()).filter(Boolean),
        start,
        end,
      };
      const r = await api.submitBacktest(strategy, params);
      setSelectedId(r.run_id);
      toast(`Backtest queued · ${r.run_id.slice(0, 8)}`);
      setRuns(await api.listBacktests());
    } catch (e) {
      setErr(String(e));
    }
  };

  const m = (detail?.metrics as unknown as Metrics | null) ?? null;
  const cfg = (detail?.params ?? {}) as { symbols?: string[]; start?: string; end?: string };

  return (
    <>
      <PageHead title="Backtests" />
      {err && <p className="error">{err}</p>}
      <Card title="New backtest">
        <div className="form">
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
            <option value="momentum">momentum</option>
            <option value="pairs">pairs</option>
          </select>
          <input value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="symbols" />
          <input value={start} onChange={(e) => setStart(e.target.value)} />
          <input value={end} onChange={(e) => setEnd(e.target.value)} />
          <button className="primary" onClick={() => void submit()}>
            Run
          </button>
        </div>
      </Card>

      <div className="split">
        <Card title="Runs">
          {runs.length === 0 ? (
            <Empty>no runs yet</Empty>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>id</th>
                  <th>status</th>
                  <th>requested</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    className={`clickable ${r.id === selectedId ? "sel" : ""}`}
                    onClick={() => setSelectedId(r.id)}
                  >
                    <td className="mono">{r.id.slice(0, 8)}</td>
                    <td>
                      <Badge status={r.status} />
                    </td>
                    <td className="muted">{r.requested_at?.slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card
          title={detail ? `Run ${detail.id.slice(0, 8)}` : "Detail"}
          actions={detail && <Badge status={detail.status} />}
        >
          {!detail && <Empty>select a run</Empty>}
          {detail && (
            <div className="muted run-config">
              {(cfg.symbols ?? []).join(", ") || "—"} · {cfg.start ?? "?"} → {cfg.end ?? "?"}
            </div>
          )}
          {detail?.status === "failed" && <p className="error">{detail.error}</p>}
          {detail && !m && detail.status !== "failed" && (
            <Empty>
              running… <Spinner />
            </Empty>
          )}
          {m && (
            <>
              <div className="metrics-grid">
                <Metric label="Total Return" value={fmt.pct(m.summary.total_return)} tone={tone(m.summary.total_return)} />
                <Metric label="CAGR" value={fmt.pct(m.performance.cagr)} tone={tone(m.performance.cagr)} />
                <Metric label="Sharpe" value={fmt.num(m.performance.sharpe)} />
                <Metric label="Sortino" value={fmt.num(m.performance.sortino)} />
                <Metric label="Calmar" value={fmt.num(m.performance.calmar)} />
                <Metric label="Max DD" value={fmt.pct(m.performance.max_drawdown)} tone="neg" />
                <Metric label="Final Equity" value={fmt.money(m.summary.final_equity)} />
                <Metric label="Costs" value={fmt.money(m.summary.total_costs)} tone="neg" />
                <Metric label="Rebalances" value={fmt.num(m.summary.n_rebalances, 0)} />
              </div>

              {equity.length > 1 && (
                <>
                  <h4>Equity curve</h4>
                  <Chart
                    points={equity.map((e) => ({ label: e.date, value: e.equity }))}
                    overlay={
                      equity.every((e) => e.benchmark != null)
                        ? equity.map((e) => ({ label: e.date, value: e.benchmark as number }))
                        : undefined
                    }
                    legend={equity.every((e) => e.benchmark != null) ? ["Strategy", "NIFTY"] : undefined}
                    baseline={m.summary.initial_capital}
                    format={(v) => fmt.money(v)}
                  />
                  <h4>Drawdown</h4>
                  <Chart
                    points={equity.map((e) => ({ label: e.date, value: e.drawdown }))}
                    stroke="#ff6b6b"
                    baseline={0}
                    format={(v) => fmt.pct(v)}
                  />
                </>
              )}

              <h4>Significance (is the Sharpe real?)</h4>
              <div className="metrics-grid">
                <Metric label="Deflated Sharpe" value={fmt.num(m.significance.deflated_sharpe)} />
                <Metric label="Prob. Sharpe" value={fmt.num(m.significance.probabilistic_sharpe)} />
                <Metric label="p-value" value={fmt.num(m.significance.p_value, 3)} />
                <Metric
                  label="95% Sharpe CI"
                  value={`${fmt.num(m.significance.ci_low)} – ${fmt.num(m.significance.ci_high)}`}
                />
              </div>

              {m.attribution && (
                <>
                  <h4>
                    Attribution vs NIFTY{" "}
                    <span className={m.attribution.alpha_significant ? "tag pos" : "tag muted"}>
                      {m.attribution.alpha_significant ? "alpha significant" : "alpha not significant"}
                    </span>
                  </h4>
                  <div className="metrics-grid">
                    <Metric
                      label="Alpha (annual)"
                      value={fmt.pct(m.attribution.alpha_annual)}
                      tone={tone(m.attribution.alpha_annual)}
                    />
                    <Metric label="Beta" value={fmt.num(m.attribution.beta)} />
                    <Metric
                      label="Info Ratio"
                      value={fmt.num(m.attribution.information_ratio)}
                      tone={tone(m.attribution.information_ratio)}
                    />
                    <Metric label="R²" value={fmt.pct(m.attribution.r_squared)} />
                    <Metric label="Alpha t-stat" value={fmt.num(m.attribution.alpha_tstat)} />
                  </div>
                </>
              )}
            </>
          )}
        </Card>
      </div>
    </>
  );
}

function Universe() {
  const [index, setIndex] = useState("NIFTY50");
  const [asOf, setAsOf] = useState("2018-06-01");
  const [members, setMembers] = useState<UniverseMember[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setErr(null);
    try {
      setMembers(await api.universe(index, asOf));
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <>
      <PageHead title="Universe" />
      {err && <p className="error">{err}</p>}
      <Card title="Point-in-time membership">
        <div className="form">
          <input value={index} onChange={(e) => setIndex(e.target.value)} />
          <input value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="YYYY-MM-DD" />
          <button className="primary" onClick={() => void load()}>
            Load
          </button>
        </div>
        {members.length === 0 ? (
          <Empty>query an index as of a date</Empty>
        ) : (
          <table>
            <thead>
              <tr>
                <th>symbol</th>
                <th>from</th>
                <th>to</th>
              </tr>
            </thead>
            <tbody>
              {members.map((mm) => (
                <tr key={mm.symbol + mm.effective_from}>
                  <td className="mono">{mm.symbol}</td>
                  <td className="muted">{mm.effective_from}</td>
                  <td className="muted">{mm.effective_to ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

function PageHead({ title, onRefresh }: { title: string; onRefresh?: () => void }) {
  return (
    <div className="page-head">
      <h2>{title}</h2>
      {onRefresh && <button onClick={onRefresh}>Refresh</button>}
    </div>
  );
}
