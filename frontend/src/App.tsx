import { useCallback, useEffect, useState } from "react";

import { api, type Bar, type BacktestRun, type Readiness, type UniverseMember } from "./api";

type Tab = "overview" | "data" | "backtests" | "universe";
const TABS: Tab[] = ["overview", "data", "backtests", "universe"];

export function App() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="app">
      <header>
        <h1>Quant Pilot</h1>
        <nav>
          {TABS.map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {tab === "overview" && <Overview />}
        {tab === "data" && <Data />}
        {tab === "backtests" && <Backtests />}
        {tab === "universe" && <Universe />}
      </main>
    </div>
  );
}

function Overview() {
  const [liveness, setLiveness] = useState("loading…");
  const [ready, setReady] = useState<Readiness | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const h = await api.health();
      setLiveness(`${h.service} ${h.version} — ${h.status}`);
      setReady(await api.readiness());
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section>
      <div className="row">
        <h2>System</h2>
        <button onClick={() => void load()}>Refresh</button>
      </div>
      {err && <p className="error">{err}</p>}
      <p>Liveness: {liveness}</p>
      {ready && (
        <ul>
          <li>
            Readiness: <b>{ready.status}</b>
          </li>
          <li>Database: {ready.database}</li>
          <li>Redis: {ready.redis}</li>
          <li>Trading enabled: {String(ready.trading_enabled)}</li>
        </ul>
      )}
    </section>
  );
}

function Data() {
  const [symbols, setSymbols] = useState("RELIANCE.NS,TCS.NS");
  const [start, setStart] = useState("2018-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [viewSymbol, setViewSymbol] = useState("RELIANCE.NS");
  const [bars, setBars] = useState<Bar[]>([]);

  const syms = () =>
    symbols
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

  const ingest = async () => {
    setErr(null);
    setMsg(null);
    try {
      const r = await api.ingestOhlcv(syms(), start, end);
      setMsg(`ingestion queued: job ${r.job_id}`);
    } catch (e) {
      setErr(String(e));
    }
  };

  const loadBars = async () => {
    setErr(null);
    try {
      setBars(await api.getBars(viewSymbol, start, end));
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <section>
      <h2>Data ingestion</h2>
      <div className="row">
        <input value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="symbols" />
        <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="start" />
        <input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="end" />
        <button onClick={() => void ingest()}>Ingest OHLCV</button>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {err && <p className="error">{err}</p>}

      <h3>View cached bars</h3>
      <div className="row">
        <input value={viewSymbol} onChange={(e) => setViewSymbol(e.target.value)} />
        <button onClick={() => void loadBars()}>Load bars</button>
        <span className="muted">{bars.length ? `${bars.length} rows` : ""}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>date</th>
            <th>close</th>
            <th>volume</th>
          </tr>
        </thead>
        <tbody>
          {bars.slice(-15).map((b) => (
            <tr key={b.date}>
              <td>{b.date}</td>
              <td>{b.close}</td>
              <td>{b.volume ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Backtests() {
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [strategy, setStrategy] = useState("momentum");
  const [symbols, setSymbols] = useState("RELIANCE.NS,TCS.NS");
  const [selected, setSelected] = useState<BacktestRun | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRuns(await api.listBacktests());
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    setErr(null);
    try {
      const syms = symbols
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await api.submitBacktest(strategy, { symbols: syms });
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <section>
      <h2>Backtests</h2>
      <div className="row">
        <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          <option value="momentum">momentum</option>
          <option value="pairs">pairs</option>
        </select>
        <input
          value={symbols}
          onChange={(e) => setSymbols(e.target.value)}
          placeholder="comma-separated symbols"
        />
        <button onClick={() => void submit()}>Submit</button>
        <button onClick={() => void load()}>Refresh</button>
      </div>
      {err && <p className="error">{err}</p>}
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
            <tr key={r.id} className="clickable" onClick={() => setSelected(r)}>
              <td>{r.id.slice(0, 8)}</td>
              <td>{r.status}</td>
              <td>{r.requested_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && <pre className="json">{JSON.stringify(selected.metrics ?? selected, null, 2)}</pre>}
    </section>
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
    <section>
      <h2>Universe (point-in-time)</h2>
      <div className="row">
        <input value={index} onChange={(e) => setIndex(e.target.value)} />
        <input value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="YYYY-MM-DD" />
        <button onClick={() => void load()}>Load</button>
      </div>
      {err && <p className="error">{err}</p>}
      <table>
        <thead>
          <tr>
            <th>symbol</th>
            <th>from</th>
            <th>to</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.symbol + m.effective_from}>
              <td>{m.symbol}</td>
              <td>{m.effective_from}</td>
              <td>{m.effective_to ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
