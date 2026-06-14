import { useCallback, useEffect, useState } from "react";

import { api, type BacktestRun, type Readiness, type UniverseMember } from "./api";

type Tab = "overview" | "backtests" | "universe";
const TABS: Tab[] = ["overview", "backtests", "universe"];

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
