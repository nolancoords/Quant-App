import { useState, useEffect, useRef } from "react";

const API = "http://localhost:8000";

const TICKERS = [
  "AAPL","MSFT","NVDA","GOOGL","GOOG","AMZN","META","TSLA","AVGO","TSM",
  "ASML","005930.KS","ORCL","ADBE","CRM","AMD","INTC","CSCO","IBM","QCOM",
  "TXN","NFLX","PYPL","NOW","SNOW","PLTR","SHOP","SPOT","ZM","UBER",
  "ABNB","MU","AMAT","LRCX","KLAC","ARM","MRVL","ROKU","SQ","CRWD",
  "ZS","FTNT","TEAM","ADSK","WDAY","DDOG","MDB","BIDU","BABA","TCEHY","SAP",
];

/* ── Refined ink-black & premium neon tokens ─────────────────────────── */
const C = {
  bg:      "#050506",
  panel:   "#0c0d10",
  border:  "rgba(255, 255, 255, 0.04)",
  borderActive: "rgba(255, 255, 255, 0.15)",
  text:    "#f3f4f6",
  muted:   "#64748b",
  blue:    "#38bdf8",
  green:   "#4ade80",
  red:     "#f87171",
  gold:    "#fbbf24",
  purple:  "#c084fc",
  orange:  "#fb923c",
};

const UI_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
const MONO_FONT = '"JetBrains Mono", "Fira Code", Menlo, monospace';

/* ── Formatters ─────────────────────────────────────────────────────────── */
const fmt = (v, d = 2) => (typeof v === "number" ? v.toFixed(d) : "—");
const fmtPct = v => (typeof v === "number" ? (v >= 0 ? "+" : "") + v.toFixed(2) + "%" : "—");
const signColor = v => ({ color: v >= 0 ? C.green : C.red });

/* ── Skeleton Shimmer Component ─────────────────────────────────────────── */
function Skeleton({ width, height, radius = 6 }) {
  return (
    <div style={{
      width,
      height,
      borderRadius: radius,
      background: "linear-gradient(90deg, #0c0d10 25%, #1a1c23 50%, #0c0d10 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.6s infinite linear",
    }} />
  );
}

/* ── Custom Skeleton Layout ─────────────────────────────────────────────── */
function DashboardSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header Block */}
      <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 12, padding: 24, display: "flex", justifyContent: "between", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
          <Skeleton width="180px" height="28px" />
          <Skeleton width="120px" height="20px" />
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}><Skeleton width="90px" height="22px" /><Skeleton width="70px" height="22px" /></div>
        </div>
      </div>
      {/* Grid Block */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))", gap: 8 }}>
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} style={{ background: C.panel, border: `1px solid ${C.border}`, padding: 14, borderRadius: 10, display: "flex", flexDirection: "column", gap: 8 }}>
            <Skeleton width="40px" height="10px" />
            <Skeleton width="70px" height="20px" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── StatPill ─────────────────────────────────────────────────────────────── */
function StatPill({ label, value, color, unit = "" }) {
  return (
    <div style={{
      background: C.panel,
      border: `1px solid ${C.border}`,
      borderRadius: 10,
      padding: "12px 16px",
      flex: "1 1 110px",
      display: "flex",
      flexDirection: "column",
      gap: 6,
    }}>
      <span style={{ fontSize: 10, color: C.muted, fontWeight: 500, letterSpacing: "0.05em", textTransform: "uppercase", fontFamily: UI_FONT }}>
        {label}
      </span>
      <span style={{ fontSize: 16, fontWeight: 600, color: color || C.text, fontFamily: MONO_FONT, letterSpacing: "-0.02em" }}>
        {value}{unit}
      </span>
    </div>
  );
}

/* ── SignalBadge ──────────────────────────────────────────────────────────── */
function SignalBadge({ label, active, trueColor, falseColor }) {
  const col = active ? (trueColor || C.green) : (falseColor || C.muted);
  return (
    <span style={{
      fontSize: 10, 
      fontWeight: 600,
      padding: "3px 8px", 
      borderRadius: 4,
      border: `1px solid ${col}25`,
      background: active ? `${col}08` : "transparent",
      color: col,
      fontFamily: UI_FONT,
      letterSpacing: "0.01em"
    }}>{label}</span>
  );
}

/* ── Sparkline SVG ────────────────────────────────────────────────────────── */
function Sparkline({ data, width = 180, height = 40 }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x},${y}`;
  }).join(" ");
  const last = data[data.length - 1];
  const color = last >= data[0] ? C.green : C.red;
  return (
    <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.25} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── TickerGrid ───────────────────────────────────────────────────────────── */
function TickerGrid({ selected, onSelect }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(72px, 1fr))", gap: 5 }}>
      {TICKERS.map(t => {
        const active = t === selected;
        return (
          <button
            key={t}
            onClick={() => onSelect(t)}
            style={{
              fontFamily: MONO_FONT,
              fontSize: 11,
              padding: "6px 0",
              textAlign: "center",
              borderRadius: 6,
              border: `1px solid ${active ? C.borderActive : C.border}`,
              background: active ? "#12131a" : "transparent",
              color: active ? C.text : C.muted,
              cursor: "pointer",
              transition: "all .15s ease",
            }}
          >{t}</button>
        );
      })}
    </div>
  );
}

/* ── Main App ─────────────────────────────────────────────────────────────── */
export default function App() {
  const [ticker, setTicker] = useState("NVDA");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [view, setView] = useState("chart");
  const abortRef = useRef(null);

  async function runTicker(t) {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setTicker(t);
    setLoading(true);
    setError(null);
    setData(null);

    try {
      const res = await fetch(`${API}/api/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: t }),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        const j = await res.json();
        throw new Error(j.error || `HTTP ${res.status}`);
      }
      const json = await res.json();
      setData(json);
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { runTicker(ticker); }, []);

  const s = data?.stats;

  return (
    <div style={{
      minHeight: "100vh",
      background: C.bg,
      color: C.text,
      fontFamily: UI_FONT,
      padding: "32px 24px",
      WebkitFontSmoothing: "antialiased",
    }}>
      {/* Dynamic Keyframes injection */}
      <style>{`
        @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
        button:hover { background: #0e1015 !important; border-color: rgba(255,255,255,0.1) !important; color: #fff !important; }
      `}</style>

      <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
        
        {/* ── Header Suite ── */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "between", flexWrap: "wrap", gap: 16 }}>
          <div>
            <h1 style={{ fontSize: 15, fontWeight: 600, margin: 0, color: C.text, letterSpacing: "-0.01em", display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ color: C.muted }}>/</span> quantsim_core
            </h1>
          </div>
          {data && !loading && (
            <div style={{ marginLeft: "auto", display: "flex", background: C.panel, padding: 3, borderRadius: 8, border: `1px solid ${C.border}` }}>
              {["chart", "stats"].map(v => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  style={{
                    fontFamily: UI_FONT, fontSize: 11, fontWeight: 500,
                    padding: "4px 12px", borderRadius: 6,
                    border: "none",
                    background: view === v ? "#1c1e26" : "transparent",
                    color: view === v ? C.text : C.muted,
                    cursor: "pointer",
                    transition: "all .12s ease"
                  }}
                >{v}</button>
              ))}
            </div>
          )}
        </div>

        {/* ── Global Universe Viewport ── */}
        <div style={{
          background: C.panel, border: `1px solid ${C.border}`,
          borderRadius: 12, padding: "16px",
        }}>
          <p style={{ fontSize: 10, color: C.muted, textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.05em", marginBottom: 12 }}>
            System Universe Pool
          </p>
          <TickerGrid selected={ticker} onSelect={runTicker} />
        </div>

        {/* ── Error handling ── */}
        {error && (
          <div style={{
            background: "transparent", border: `1px solid ${C.red}30`,
            borderRadius: 10, padding: "14px 18px", color: C.red, fontSize: 12, fontFamily: MONO_FONT
          }}>
            <span style={{ fontWeight: 'bold', marginRight: 6 }}>[ERR]</span> {error}
          </div>
        )}

        {/* ── Visual State Controllers ── */}
        {loading && <DashboardSkeleton />}

        {data && !loading && (
          <>
            {/* Price Identity Node */}
            <div style={{
              background: C.panel, border: `1px solid ${C.border}`,
              borderRadius: 12, padding: "20px 24px",
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 20 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color: C.text, letterSpacing: "-0.02em" }}>
                    {data.ticker} <span style={{ fontSize: 12, color: C.muted, marginLeft: 4, fontWeight: 400 }}>• 1Y timeline</span>
                  </div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: C.text, fontFamily: MONO_FONT, letterSpacing: "-0.04em", display: "flex", alignItems: "center", gap: 8 }}>
                    ${fmt(s.price)}
                    <span style={{ fontSize: 13, fontWeight: 500, fontFamily: UI_FONT, ...signColor(s.price_chg_pct) }}>
                      {fmtPct(s.price_chg_pct)}
                    </span>
                  </div>
                  <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <SignalBadge label={s.gc ? "Golden Cross" : "Death Cross"} active={s.gc} trueColor={C.green} falseColor={C.red} />
                    <SignalBadge label="Z-Long"  active={s.z_long}  trueColor={C.green} />
                    <SignalBadge label="Z-Short" active={s.z_short} trueColor={C.red}   />
                    <SignalBadge label="WR-OB"   active={s.wr_ob}   trueColor={C.red}   />
                    <SignalBadge label="WR-OS"   active={s.wr_os}   trueColor={C.green} />
                    {!s.quantsim_available && <SignalBadge label="Numpy Fallback" active={true} trueColor={C.gold} />}
                  </div>
                </div>
                <div style={{ marginLeft: "auto", background: "rgba(255,255,255,0.01)", padding: "12px 16px", borderRadius: 8, border: `1px solid ${C.border}` }}>
                  <Sparkline data={data.sparkline} />
                </div>
              </div>
            </div>

            {/* Matrix Metrics Array */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 6 }}>
              <StatPill label="CAGR"    value={fmtPct(s.cagr * 100)} color={s.cagr >= 0 ? C.green : C.red} />
              <StatPill label="Sharpe"  value={fmt(s.sharpe)}         color={s.sharpe >= 1 ? C.green : s.sharpe >= 0 ? C.gold : C.red} />
              <StatPill label="Beta"    value={fmt(s.beta)}           color={C.purple} />
              <StatPill label="Z-Score" value={fmt(s.z)}              color={s.z_long ? C.green : s.z_short ? C.red : C.text} />
              <StatPill label="RSI-14"  value={fmt(s.rsi, 1)}         color={s.rsi >= 70 ? C.red : s.rsi <= 30 ? C.green : C.text} />
              <StatPill label="MACD"    value={fmt(s.macd, 3)}        color={s.macd >= 0 ? C.green : C.red} />
              <StatPill label="CCI-20"  value={fmt(s.cci, 1)}         color={s.cci >= 100 ? C.red : s.cci <= -100 ? C.green : C.text} />
              <StatPill label="WR %R"   value={fmt(s.wr, 1)}          color={s.wr_ob ? C.red : s.wr_os ? C.green : C.text} />
              <StatPill label="ATR-14"  value={fmt(s.atr, 2)} unit="$" color={C.gold} />
              <StatPill label="Boll %B" value={fmt(s.pct_b)}          color={s.pct_b >= 1 ? C.red : s.pct_b <= 0 ? C.green : C.text} />
              <StatPill label="Ann.Ret" value={fmtPct(s.ann_ret)}     color={s.ann_ret >= 0 ? C.green : C.red} />
              <StatPill label="Ann.Vol" value={fmtPct(s.ann_std)}     color={C.orange} />
            </div>

            {/* Content View Container */}
            {view === "chart" && (
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`,
                borderRadius: 12, overflow: "hidden", padding: 12
              }}>
                <img
                  src={`data:image/png;base64,${data.chart}`}
                  alt={`${data.ticker} engine metrics`}
                  style={{ width: "100%", display: "block", borderRadius: 6, filter: "contrast(1.04) brightness(0.95)" }}
                />
              </div>
            )}

            {view === "stats" && (
              <div style={{
                background: C.panel, border: `1px solid ${C.border}`,
                borderRadius: 12, padding: "20px",
              }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: MONO_FONT }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      <th style={{ textAlign: "left", padding: "0 10px 10px 10px", color: C.muted, fontWeight: 500, fontFamily: UI_FONT, fontSize: 10, textTransform: "uppercase" }}>Metric Parameter</th>
                      <th style={{ textAlign: "left", padding: "0 10px 10px 10px", color: C.muted, fontWeight: 500, fontFamily: UI_FONT, fontSize: 10, textTransform: "uppercase" }}>Engine Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(s).map(([k, v]) => (
                      <tr key={k} style={{ borderBottom: `1px solid ${C.border}` }}>
                        <td style={{ padding: "10px", color: C.muted }}>{k}</td>
                        <td style={{ padding: "10px", color: C.text }}>
                          {typeof v === "boolean"
                            ? <SignalBadge label={String(v)} active={v} trueColor={C.green} falseColor={C.red} />
                            : typeof v === "number"
                              ? v.toFixed(5)
                              : String(v)
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}