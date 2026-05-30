"""
quant_dashboard backend
-----------------------
POST /api/run   { ticker: "NVDA" }
  → runs the quantsim pipeline for the requested ticker
  → returns JSON with all indicators + base64 chart PNG

GET  /api/tickers
  → returns the universe list
"""

import io, base64, warnings, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import yfinance as yf

from flask import Flask, jsonify, request
from flask_cors import CORS

# quantsim is a local C++/pybind11 package — must be importable
try:
    import quantsim
    QUANTSIM_AVAILABLE = True
except ImportError:
    QUANTSIM_AVAILABLE = False
    print("WARNING: quantsim not found — all indicator calls will use numpy fallbacks", flush=True)

warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app)  # allow the React dev server (localhost:5173) to call us

# ─── Universe ────────────────────────────────────────────────────────────────
TICKERS = [
    "AAPL","MSFT","NVDA","GOOGL","GOOG","AMZN","META","TSLA","AVGO","TSM",
    "ASML","005930.KS","ORCL","ADBE","CRM","AMD","INTC","CSCO","IBM","QCOM",
    "TXN","NFLX","PYPL","NOW","SNOW","PLTR","SHOP","SPOT","ZM","UBER",
    "ABNB","MU","AMAT","LRCX","KLAC","ARM","MRVL","ROKU","SQ","CRWD",
    "ZS","FTNT","TEAM","ADSK","WDAY","DDOG","MDB","BIDU","BABA","TCEHY","SAP"
]

BENCHMARK  = "^GSPC"
RISK_FREE  = 0.0
OU_THETA   = 0.15
OU_SIGMA   = 0.02
OU_STEPS   = 500
PERIOD     = "1y"

# ─── numpy fallbacks (used when quantsim is absent) ───────────────────────────
def _sma(arr, w):
    return float(np.mean(arr[-w:])) if len(arr) >= w else float(np.mean(arr))

def _ema(arr, period):
    k = 2 / (period + 1)
    v = float(arr[0])
    for x in arr[1:]:
        v = x * k + v * (1 - k)
    return v

def _rsi(arr, period=14):
    diffs = np.diff(arr)
    gains = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)
    ag = np.mean(gains[-period:]) if len(gains) >= period else np.mean(gains)
    al = np.mean(losses[-period:]) if len(losses) >= period else np.mean(losses)
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)

def _std(arr):
    return float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0

def _sharpe(ret, rf, std):
    return (ret - rf) / std if std > 0 else 0.0

def _cagr(start, end, years):
    if start <= 0 or years <= 0:
        return 0.0
    return float((end / start) ** (1 / years) - 1)

def _beta(sx, bx):
    sx, bx = np.array(sx), np.array(bx)
    cov = np.cov(sx, bx, ddof=1)
    return float(cov[0, 1] / cov[1, 1]) if cov[1, 1] != 0 else 1.0

def _macd_val(arr):
    if len(arr) < 26:
        return 0.0
    return _ema(arr, 12) - _ema(arr, 26)

def _zscore(arr, window=20):
    w = arr[-window:] if len(arr) >= window else arr
    m, s = np.mean(w), np.std(w, ddof=1)
    return float((arr[-1] - m) / s) if s > 0 else 0.0


# ─── Indicator wrappers (quantsim if available, else fallback) ────────────────

def qs_sma(prices_list, w):
    if QUANTSIM_AVAILABLE:
        return quantsim.SMA(prices_list[-w:])
    return _sma(prices_list, w)

def qs_ema(prices_list, period):
    if QUANTSIM_AVAILABLE:
        return quantsim.EMA(prices_list, period)
    return _ema(prices_list, period)

def qs_rsi(prices_list, period=14):
    if QUANTSIM_AVAILABLE:
        return quantsim.RSI(prices_list, period=period)
    return _rsi(prices_list, period)

def qs_macd(prices_list):
    if QUANTSIM_AVAILABLE:
        return quantsim.MACD(prices_list)
    return _macd_val(prices_list)

def qs_std(arr_list):
    if QUANTSIM_AVAILABLE:
        return quantsim.StandardDeviation(arr_list)
    return _std(arr_list)

def qs_sharpe(ret, rf, std):
    if QUANTSIM_AVAILABLE:
        return quantsim.SharpeRatio(ret, rf, std)
    return _sharpe(ret, rf, std)

def qs_cagr(start, end, years):
    if QUANTSIM_AVAILABLE:
        return quantsim.CAGR(start, end, years)
    return _cagr(start, end, years)

def qs_beta(sx, bx):
    if QUANTSIM_AVAILABLE:
        return quantsim.Beta(sx, bx)
    return _beta(sx, bx)

def qs_golden_cross(sma_fast, sma_slow):
    if QUANTSIM_AVAILABLE:
        return quantsim.GoldenCross(sma_fast, sma_slow)
    return bool(sma_fast > sma_slow)

def qs_zscore_long(z):
    if QUANTSIM_AVAILABLE:
        return quantsim.ZScoreLong(z)
    return z <= -2.0

def qs_zscore_short(z):
    if QUANTSIM_AVAILABLE:
        return quantsim.ZScoreShort(z)
    return z >= 2.0

def qs_wr_overbought(wr):
    if QUANTSIM_AVAILABLE:
        return quantsim.WROverBought(wr)
    return wr >= -20.0

def qs_wr_oversold(wr):
    if QUANTSIM_AVAILABLE:
        return quantsim.WROverSold(wr)
    return wr <= -80.0


# ─── Full-series indicators ───────────────────────────────────────────────────

def compute_kama(cl):
    if QUANTSIM_AVAILABLE:
        arr = np.array(quantsim.KAMA(cl, er_period=10, fast=2, slow=30))
    else:
        arr = np.array(cl, dtype=float)
    arr[arr == 0.0] = np.nan
    return arr

def compute_roc(cl, period=10):
    if QUANTSIM_AVAILABLE:
        arr = np.array(quantsim.ROC(cl, period=period))
    else:
        a = np.array(cl, dtype=float)
        arr = np.full(len(a), np.nan)
        arr[period:] = (a[period:] - a[:-period]) / a[:-period] * 100
    arr[arr == 0.0] = np.nan
    return arr

def compute_cci(cl, period=20):
    if QUANTSIM_AVAILABLE:
        arr = np.array(quantsim.CCI(cl, period=period))
    else:
        a = np.array(cl, dtype=float)
        arr = np.full(len(a), np.nan)
        for i in range(period - 1, len(a)):
            w = a[i-period+1:i+1]
            m = np.mean(w)
            md = np.mean(np.abs(w - m))
            arr[i] = (a[i] - m) / (0.015 * md) if md != 0 else 0.0
    arr[arr == 0.0] = np.nan
    return arr

def compute_williams_r(cl, period=14):
    if QUANTSIM_AVAILABLE:
        arr = np.array(quantsim.WilliamsR(cl, period=period))
    else:
        a = np.array(cl, dtype=float)
        arr = np.full(len(a), np.nan)
        for i in range(period - 1, len(a)):
            w = a[i-period+1:i+1]
            hh, ll = np.max(w), np.min(w)
            arr[i] = ((hh - a[i]) / (hh - ll) * -100) if hh != ll else -50.0
    arr[arr == 0.0] = np.nan
    return arr

def compute_obv(cl):
    if QUANTSIM_AVAILABLE:
        return np.array(quantsim.OBVProxy(cl))
    a = np.array(cl, dtype=float)
    d = np.diff(a)
    obv = np.concatenate([[0.0], np.cumsum(np.where(d > 0, a[1:], np.where(d < 0, -a[1:], 0.0)))])
    return obv

def compute_zscore_series(cl, window=20):
    if QUANTSIM_AVAILABLE:
        arr = np.array(quantsim.ZScore(cl, window=window))
    else:
        a = np.array(cl, dtype=float)
        arr = np.full(len(a), np.nan)
        for i in range(window - 1, len(a)):
            w = a[i-window+1:i+1]
            m, s = np.mean(w), np.std(w, ddof=1)
            arr[i] = (a[i] - m) / s if s > 0 else 0.0
    arr[arr == 0.0] = np.nan
    return arr

def compute_atr(cl, period=14):
    if QUANTSIM_AVAILABLE:
        arr = np.array(quantsim.ATR(cl, period=period))
    else:
        a = np.array(cl, dtype=float)
        arr = np.full(len(a), np.nan)
        trs = np.abs(np.diff(a))
        for i in range(period, len(a)):
            arr[i] = np.mean(trs[i-period:i])
    arr[arr == 0.0] = np.nan
    return arr

def compute_bollinger(cl, w=20, k=2.0):
    if QUANTSIM_AVAILABLE:
        bb = quantsim.BollingerBands(cl, w=w, k=k)
        mid   = np.array(bb.mid)
        upper = np.array(bb.upper)
        lower = np.array(bb.lower)
        pct_b = np.array(bb.pct_b)
    else:
        a = np.array(cl, dtype=float)
        mid   = np.full(len(a), np.nan)
        upper = np.full(len(a), np.nan)
        lower = np.full(len(a), np.nan)
        pct_b = np.full(len(a), np.nan)
        for i in range(w - 1, len(a)):
            sl = a[i-w+1:i+1]
            m, s = np.mean(sl), np.std(sl, ddof=1)
            mid[i]   = m
            upper[i] = m + k * s
            lower[i] = m - k * s
            pct_b[i] = (a[i] - lower[i]) / (upper[i] - lower[i]) if upper[i] != lower[i] else 0.5
    for arr in (mid, upper, lower):
        arr[arr == 0.0] = np.nan
    return mid, upper, lower, pct_b

def compute_stochastic(cl, k_period=14, d_period=3):
    if QUANTSIM_AVAILABLE:
        st = quantsim.Stochastic(cl, k_period=k_period, d_period=d_period)
        k = np.array(st.pct_k)
        d = np.array(st.pct_d)
    else:
        a = np.array(cl, dtype=float)
        k = np.full(len(a), np.nan)
        for i in range(k_period - 1, len(a)):
            w = a[i-k_period+1:i+1]
            hh, ll = np.max(w), np.min(w)
            k[i] = (a[i] - ll) / (hh - ll) * 100 if hh != ll else 50.0
        d = np.full(len(a), np.nan)
        for i in range(d_period - 1, len(a)):
            valid = k[i-d_period+1:i+1]
            if not np.any(np.isnan(valid)):
                d[i] = np.mean(valid)
    k[k == 0.0] = np.nan
    d[d == 0.0] = np.nan
    return k, d

def compute_ou_path():
    if QUANTSIM_AVAILABLE:
        ou = quantsim.OrnsteinUhlenbeck(OU_THETA, OU_SIGMA, 1/252, 0.0)
        return np.array(ou.simulate(OU_STEPS))
    dt = 1/252
    path = np.zeros(OU_STEPS)
    for i in range(1, OU_STEPS):
        path[i] = (path[i-1]
                   + OU_THETA * (0.0 - path[i-1]) * dt
                   + OU_SIGMA * np.sqrt(dt) * np.random.randn())
    return path


# ─── Rolling helpers ──────────────────────────────────────────────────────────

def rolling_sma(prices, w):
    out = np.full(len(prices), np.nan)
    for i in range(w - 1, len(prices)):
        out[i] = qs_sma(prices[i-w+1:i+1].tolist(), w)
    return out

def rolling_ema(prices, period):
    out = np.full(len(prices), np.nan)
    for i in range(period - 1, len(prices)):
        out[i] = qs_ema(prices[:i+1].tolist(), period)
    return out

def rolling_rsi(prices, period=14):
    out = np.full(len(prices), np.nan)
    for i in range(period, len(prices)):
        out[i] = qs_rsi(prices[:i+1].tolist(), period=period)
    return out

def rolling_macd(prices):
    out = np.full(len(prices), np.nan)
    for i in range(25, len(prices)):
        out[i] = qs_macd(prices[:i+1].tolist())
    return out


# ─── Plotting ─────────────────────────────────────────────────────────────────

BG, PANEL_BG, GRID_C = "#0d1117", "#161b22", "#21262d"
TEXT_C, ACCENT_C, GREEN = "#e6edf3", "#58a6ff", "#3fb950"
RED, GOLD, PURPLE, ORANGE = "#f85149", "#d29922", "#bc8cff", "#ffa657"
CYAN, LIME = "#39d0d8", "#b5e853"

plt.rcParams.update({
    "figure.facecolor": BG,    "axes.facecolor": PANEL_BG,
    "axes.edgecolor": GRID_C,  "axes.labelcolor": TEXT_C,
    "text.color": TEXT_C,      "xtick.color": TEXT_C,
    "ytick.color": TEXT_C,     "grid.color": GRID_C,
    "grid.linestyle": "--",    "grid.linewidth": 0.5,
    "font.family": "monospace","font.size": 9,
})

def build_chart(ticker, closes, bench_c, dates, indicators, stats):
    n         = len(closes)
    x         = np.arange(n)
    tick_idx  = np.linspace(0, n-1, 8, dtype=int)
    tick_lbl  = [str(dates[i])[:10] for i in tick_idx]

    fig = plt.figure(figsize=(20, 22))
    fig.patch.set_facecolor(BG)
    gs  = gridspec.GridSpec(5, 3, figure=fig, hspace=0.55, wspace=0.35)

    ax_price  = fig.add_subplot(gs[0, :])
    ax_macd   = fig.add_subplot(gs[1, 0])
    ax_rsi    = fig.add_subplot(gs[1, 1])
    ax_stoch  = fig.add_subplot(gs[1, 2])
    ax_bb     = fig.add_subplot(gs[2, 0])
    ax_atr    = fig.add_subplot(gs[2, 1])
    ax_zscore = fig.add_subplot(gs[2, 2])
    ax_beta   = fig.add_subplot(gs[3, 0:2])
    ax_obv    = fig.add_subplot(gs[3, 2])
    ax_cci    = fig.add_subplot(gs[4, 0])
    ax_wr     = fig.add_subplot(gs[4, 1])
    ax_ou     = fig.add_subplot(gs[4, 2])

    I = indicators
    S = stats

    # P1: Price
    ax_price.fill_between(x, I["bb_upper"], I["bb_lower"], alpha=0.07, color=ACCENT_C)
    ax_price.plot(x, I["bb_upper"], color=ACCENT_C, lw=0.6, ls="--")
    ax_price.plot(x, I["bb_lower"], color=ACCENT_C, lw=0.6, ls="--")
    ax_price.plot(x, closes,        color=TEXT_C,   lw=1.0, alpha=0.9, label="Close")
    ax_price.plot(x, I["sma20"],    color=ACCENT_C, lw=1.2, label="SMA-20")
    ax_price.plot(x, I["sma50"],    color=GOLD,     lw=1.2, label="SMA-50")
    ax_price.plot(x, I["ema20"],    color=PURPLE,   lw=1.0, ls="--", label="EMA-20")
    ax_price.plot(x, I["kama"],     color=LIME,     lw=1.1, label="KAMA-10")
    ax_price.axhline(closes[-1], color=GREEN if S["gc"] else RED, lw=0.7, ls=":")
    ax_price.set_title(
        f"{ticker}  ·  {PERIOD}  |  CAGR {S['cagr']*100:+.1f}%  Sharpe {S['sharpe']:.2f}  "
        f"β={S['beta']:.2f}  Z={S['z']:.2f}  ATR={S['atr']:.2f}  |  "
        f"{'⬆ Golden Cross' if S['gc'] else '⬇ Death Cross'}",
        color=TEXT_C, fontsize=10, pad=8)
    ax_price.set_ylabel("Price (USD)")
    ax_price.grid(True)
    ax_price.set_xticks(tick_idx); ax_price.set_xticklabels(tick_lbl, rotation=20, ha="right")
    ax_price.legend(loc="upper left", fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C, ncol=3)

    # P2: MACD
    vm = np.nan_to_num(I["macd"])
    ax_macd.plot(x, I["macd"], color=ACCENT_C, lw=1.0)
    ax_macd.axhline(0, color=GRID_C, lw=0.8)
    ax_macd.fill_between(x, I["macd"], 0, where=vm>=0, alpha=0.25, color=GREEN)
    ax_macd.fill_between(x, I["macd"], 0, where=vm<0,  alpha=0.25, color=RED)
    ax_macd.set_title(f"MACD (12/26)  cur={S['macd']:.3f}", color=TEXT_C)
    ax_macd.set_ylabel("EMA diff"); ax_macd.grid(True); ax_macd.set_xticks([])

    # P3: RSI
    vr = np.nan_to_num(I["rsi14"], nan=50.0)
    ax_rsi.plot(x, I["rsi14"], color=ORANGE, lw=1.0)
    ax_rsi.axhline(70, color=RED,   lw=0.8, ls="--", label="OB 70")
    ax_rsi.axhline(30, color=GREEN, lw=0.8, ls="--", label="OS 30")
    ax_rsi.fill_between(x, I["rsi14"], 70, where=vr>=70, alpha=0.2, color=RED)
    ax_rsi.fill_between(x, I["rsi14"], 30, where=vr<=30, alpha=0.2, color=GREEN)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_title(f"RSI (14)  cur={S['rsi']:.1f}", color=TEXT_C)
    ax_rsi.set_ylabel("RSI"); ax_rsi.grid(True); ax_rsi.set_xticks([])
    ax_rsi.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P4: Stochastic
    vsk = np.nan_to_num(I["stoch_k"], nan=50.0)
    ax_stoch.plot(x, I["stoch_k"], color=CYAN,   lw=1.0, label="%K")
    ax_stoch.plot(x, I["stoch_d"], color=ORANGE, lw=1.0, ls="--", label="%D signal")
    ax_stoch.axhline(80, color=RED,   lw=0.7, ls=":")
    ax_stoch.axhline(20, color=GREEN, lw=0.7, ls=":")
    ax_stoch.fill_between(x, I["stoch_k"], 80, where=vsk>=80, alpha=0.15, color=RED)
    ax_stoch.fill_between(x, I["stoch_k"], 20, where=vsk<=20, alpha=0.15, color=GREEN)
    ax_stoch.set_ylim(0, 100)
    ax_stoch.set_title("Stochastic %K/%D (14,3)", color=TEXT_C)
    ax_stoch.grid(True); ax_stoch.set_xticks([])
    ax_stoch.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P5: Bollinger %B
    vpb = np.nan_to_num(I["pct_b"], nan=0.5)
    ax_bb.plot(x, I["pct_b"], color=ACCENT_C, lw=1.0)
    ax_bb.axhline(1.0, color=RED,   lw=0.8, ls="--", label="%B=1 upper")
    ax_bb.axhline(0.0, color=GREEN, lw=0.8, ls="--", label="%B=0 lower")
    ax_bb.axhline(0.5, color=GRID_C, lw=0.6, ls=":")
    ax_bb.fill_between(x, I["pct_b"], 1.0, where=vpb>=1.0, alpha=0.2, color=RED)
    ax_bb.fill_between(x, I["pct_b"], 0.0, where=vpb<=0.0, alpha=0.2, color=GREEN)
    ax_bb.set_title(f"Bollinger %B (20, 2σ)  cur={S['pct_b']:.2f}", color=TEXT_C)
    ax_bb.set_ylabel("%B"); ax_bb.grid(True); ax_bb.set_xticks([])
    ax_bb.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P6: ATR
    ax_atr.plot(x, I["atr14"], color=GOLD, lw=1.0)
    ax_atr.fill_between(x, I["atr14"], alpha=0.15, color=GOLD)
    ax_atr.set_title(f"ATR (14, Wilder)  cur={S['atr']:.2f}", color=TEXT_C)
    ax_atr.set_ylabel("ATR $"); ax_atr.grid(True); ax_atr.set_xticks([])

    # P7: Z-Score
    vz = np.nan_to_num(I["z20"])
    z_color = GREEN if S["z_long"] else (RED if S["z_short"] else TEXT_C)
    ax_zscore.plot(x, I["z20"], color=PURPLE, lw=1.0)
    ax_zscore.axhline( 2, color=RED,   lw=0.7, ls="--", label="+2σ short")
    ax_zscore.axhline(-2, color=GREEN, lw=0.7, ls="--", label="-2σ long")
    ax_zscore.axhline( 0, color=GRID_C, lw=0.6)
    ax_zscore.fill_between(x, I["z20"],  2, where=vz>= 2, alpha=0.2, color=RED)
    ax_zscore.fill_between(x, I["z20"], -2, where=vz<=-2, alpha=0.2, color=GREEN)
    ax_zscore.set_title(f"Z-Score (20d)  cur={S['z']:.2f}", color=z_color)
    ax_zscore.set_ylabel("Std devs"); ax_zscore.grid(True); ax_zscore.set_xticks([])
    ax_zscore.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P8: Beta
    vb = np.nan_to_num(I["beta"], nan=1.0)
    ax_beta.plot(x, I["beta"], color=PURPLE, lw=1.0)
    ax_beta.axhline(1.0, color=GRID_C, lw=0.8, ls="--", label="β=1 market")
    ax_beta.axhline(0.0, color=GOLD,   lw=0.6, ls=":")
    ax_beta.fill_between(x, I["beta"], 1, where=vb>=1, alpha=0.15, color=RED,   label="High-β")
    ax_beta.fill_between(x, I["beta"], 1, where=vb<1,  alpha=0.15, color=GREEN, label="Low-β")
    ax_beta.set_title(f"Rolling β vs {BENCHMARK} (60d)  cur={S['beta']:.2f}", color=TEXT_C)
    ax_beta.set_ylabel("β"); ax_beta.grid(True)
    ax_beta.set_xticks(tick_idx); ax_beta.set_xticklabels(tick_lbl, rotation=20, ha="right")
    ax_beta.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P9: OBV
    obv = I["obv"]
    ax_obv.plot(x, obv, color=LIME, lw=1.0)
    ax_obv.fill_between(x, obv, 0, where=obv>=0, alpha=0.15, color=GREEN)
    ax_obv.fill_between(x, obv, 0, where=obv<0,  alpha=0.15, color=RED)
    ax_obv.axhline(0, color=GRID_C, lw=0.6)
    ax_obv.set_title("OBV proxy (price-momentum)", color=TEXT_C)
    ax_obv.set_ylabel("Cum. Δ$"); ax_obv.grid(True); ax_obv.set_xticks([])

    # P10: CCI
    vc = np.nan_to_num(I["cci20"])
    ax_cci.plot(x, I["cci20"], color=CYAN, lw=1.0)
    ax_cci.axhline( 100, color=RED,   lw=0.7, ls="--", label="+100 OB")
    ax_cci.axhline(-100, color=GREEN, lw=0.7, ls="--", label="-100 OS")
    ax_cci.axhline(0, color=GRID_C, lw=0.6)
    ax_cci.fill_between(x, I["cci20"],  100, where=vc>= 100, alpha=0.2, color=RED)
    ax_cci.fill_between(x, I["cci20"], -100, where=vc<=-100, alpha=0.2, color=GREEN)
    ax_cci.set_title(f"CCI (20)  cur={S['cci']:.1f}", color=TEXT_C)
    ax_cci.set_ylabel("CCI"); ax_cci.grid(True)
    ax_cci.set_xticks(tick_idx[:4]); ax_cci.set_xticklabels(tick_lbl[:4], rotation=20, ha="right")
    ax_cci.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P11: Williams %R
    vw = np.nan_to_num(I["wr14"], nan=-50.0)
    wr_color = RED if S["wr_ob"] else (GREEN if S["wr_os"] else TEXT_C)
    ax_wr.plot(x, I["wr14"], color=ORANGE, lw=1.0)
    ax_wr.axhline(-20, color=RED,   lw=0.7, ls="--", label="-20 OB")
    ax_wr.axhline(-80, color=GREEN, lw=0.7, ls="--", label="-80 OS")
    ax_wr.fill_between(x, I["wr14"], -20, where=vw>=-20, alpha=0.2, color=RED)
    ax_wr.fill_between(x, I["wr14"], -80, where=vw<=-80, alpha=0.2, color=GREEN)
    ax_wr.set_ylim(-105, 5)
    ax_wr.set_title(f"Williams %R (14)  cur={S['wr']:.1f}", color=wr_color)
    ax_wr.set_ylabel("%R"); ax_wr.grid(True)
    ax_wr.set_xticks(tick_idx[:4]); ax_wr.set_xticklabels(tick_lbl[:4], rotation=20, ha="right")
    ax_wr.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # P12: OU
    ou_path = compute_ou_path()
    ou_x = np.arange(OU_STEPS)
    ax_ou.plot(ou_x, ou_path, color=GREEN, lw=0.9, alpha=0.85)
    ax_ou.axhline(0, color=GOLD, lw=0.7, ls="--", label="Long-run mean (0)")
    ax_ou.fill_between(ou_x, ou_path, 0, alpha=0.12, color=GREEN)
    ax_ou.set_title(f"OU Mean-Reversion  θ={OU_THETA}  σ={OU_SIGMA}", color=TEXT_C)
    ax_ou.set_xlabel("Steps (1/252 yr)"); ax_ou.set_ylabel("X(t)")
    ax_ou.grid(True); ax_ou.legend(fontsize=7, facecolor=PANEL_BG, edgecolor=GRID_C)

    # Footer
    fig.text(
        0.5, -0.002,
        f"quantsim {'C++/pybind11' if QUANTSIM_AVAILABLE else '(numpy fallback)'}  ·  {ticker} {PERIOD}  "
        f"·  CAGR {S['cagr']*100:+.1f}%  Sharpe {S['sharpe']:.2f}  β={S['beta']:.2f}  "
        f"Z={S['z']:.2f}  RSI={S['rsi']:.1f}  CCI={S['cci']:.1f}  WR={S['wr']:.1f}  ATR={S['atr']:.2f}",
        ha="center", color=GRID_C, fontsize=8
    )

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ─── Core pipeline ────────────────────────────────────────────────────────────

def run_pipeline(ticker):
    stock_df = yf.download(ticker,    period=PERIOD, auto_adjust=True, progress=False)
    bench_df = yf.download(BENCHMARK, period=PERIOD, auto_adjust=True, progress=False)

    if stock_df.empty or bench_df.empty:
        raise ValueError(f"No data returned for {ticker}")

    df = pd.concat(
        [stock_df["Close"].squeeze().rename("stock"),
         bench_df["Close"].squeeze().rename("bench")],
        axis=1
    ).dropna()

    closes  = df["stock"].to_numpy(dtype=float)
    bench_c = df["bench"].to_numpy(dtype=float)
    dates   = df.index
    n       = len(df)
    cl      = closes.tolist()

    # Full-series indicators
    kama             = compute_kama(cl)
    roc10            = compute_roc(cl, 10)
    cci20            = compute_cci(cl, 20)
    wr14             = compute_williams_r(cl, 14)
    obv              = compute_obv(cl)
    z20              = compute_zscore_series(cl, 20)
    atr14            = compute_atr(cl, 14)
    bb_mid, bb_upper, bb_lower, pct_b = compute_bollinger(cl, 20, 2.0)
    stoch_k, stoch_d = compute_stochastic(cl, 14, 3)

    # Rolling indicators
    sma20 = rolling_sma(closes, 20)
    sma50 = rolling_sma(closes, 50)
    ema20 = rolling_ema(closes, 20)
    rsi14 = rolling_rsi(closes, 14)
    macd  = rolling_macd(closes)

    # Beta (60-day rolling)
    stock_ret = np.diff(np.log(closes))
    bench_ret = np.diff(np.log(bench_c[:n]))
    min_len   = min(len(stock_ret), len(bench_ret))
    stock_ret, bench_ret = stock_ret[:min_len], bench_ret[:min_len]

    beta60 = np.full(len(stock_ret), np.nan)
    for i in range(59, len(stock_ret)):
        beta60[i] = qs_beta(
            stock_ret[i-59:i+1].tolist(),
            bench_ret[i-59:i+1].tolist()
        )
    beta_series = np.concatenate([[np.nan], beta60])

    # Scalar stats
    def safe_last(arr):
        a = arr[~np.isnan(arr)]
        return float(a[-1]) if len(a) else 0.0

    ann_ret  = float(np.nanmean(stock_ret) * 252)
    ann_std  = qs_std(stock_ret.tolist()) * (252 ** 0.5)
    sharpe   = qs_sharpe(ann_ret, RISK_FREE, ann_std)
    cagr_val = qs_cagr(closes[0], closes[-1], max(1, n // 252))
    gc       = qs_golden_cross(sma20[-1], sma50[-1]) if not np.isnan(sma20[-1]) else False

    cur_rsi  = safe_last(rsi14)
    cur_macd = safe_last(macd)
    cur_z    = safe_last(z20)
    cur_wr   = safe_last(wr14)
    cur_cci  = safe_last(cci20)
    cur_beta = safe_last(beta_series)
    cur_pctb = safe_last(pct_b)
    cur_atr  = safe_last(atr14)

    stats = dict(
        cagr=cagr_val, sharpe=sharpe, beta=cur_beta, z=cur_z, atr=cur_atr,
        rsi=cur_rsi, macd=cur_macd, cci=cur_cci, wr=cur_wr, pct_b=cur_pctb,
        gc=bool(gc),
        z_long=bool(qs_zscore_long(cur_z)),
        z_short=bool(qs_zscore_short(cur_z)),
        wr_ob=bool(qs_wr_overbought(cur_wr)),
        wr_os=bool(qs_wr_oversold(cur_wr)),
        price=float(closes[-1]),
        price_chg_pct=float((closes[-1] - closes[0]) / closes[0] * 100),
        ann_ret=float(ann_ret * 100),
        ann_std=float(ann_std * 100),
        quantsim_available=QUANTSIM_AVAILABLE,
    )

    indicators = dict(
        sma20=sma20, sma50=sma50, ema20=ema20, kama=kama,
        rsi14=rsi14, macd=macd,
        bb_upper=bb_upper, bb_lower=bb_lower, bb_mid=bb_mid, pct_b=pct_b,
        stoch_k=stoch_k, stoch_d=stoch_d,
        atr14=atr14, z20=z20, beta=beta_series, obv=obv, cci20=cci20, wr14=wr14,
    )

    chart_b64 = build_chart(ticker, closes, bench_c, dates, indicators, stats)

    # Build sparkline data (downsample to 60 points for JSON)
    step = max(1, n // 60)
    spark = closes[::step].tolist()

    return {
        "ticker": ticker,
        "stats": stats,
        "chart": chart_b64,
        "sparkline": spark,
        "dates": [str(d)[:10] for d in dates[::step]],
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/tickers")
def get_tickers():
    return jsonify({"tickers": TICKERS})


@app.post("/api/run")
def run():
    body   = request.get_json(force=True)
    ticker = str(body.get("ticker", "")).strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    if ticker not in TICKERS:
        return jsonify({"error": f"{ticker} not in universe"}), 400
    try:
        result = run_pipeline(ticker)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting quant backend on http://localhost:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
