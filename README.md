

## Structure

```
quant_app/
├── backend/
│   ├── app.py            ← Flask API (wraps your quantsim pipeline)
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx        ← React dashboard
    │   └── main.jsx
    ├── index.html
    ├── package.json
    └── vite.config.js     ← proxies /api → Flask :8000
```

## Setup

### 1 — Backend

```bash
cd backend
pip install -r requirements.txt   # flask flask-cors yfinance numpy pandas matplotlib
# quantsim must already be installed (your C++/pybind11 package)
python app.py
# → http://localhost:8000
```

If `quantsim` is not importable, the backend falls back to pure-numpy
implementations of every indicator so you can still run without the C++ lib.

### 2 — Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Open http://localhost:5173 — click any ticker to run the pipeline.

## API

| Method | Path        | Body              | Returns                              |
|--------|-------------|-------------------|--------------------------------------|
| GET    | /api/tickers | —                | `{ tickers: [...] }`                 |
| POST   | /api/run    | `{ ticker: "NVDA" }` | `{ ticker, stats, chart (b64), sparkline, dates }` |

### Response shape — `stats`

| Field             | Description                         |
|-------------------|-------------------------------------|
| cagr              | annualised CAGR (decimal)           |
| sharpe            | Sharpe ratio                        |
| beta              | rolling 60-day beta vs S&P 500      |
| z                 | Z-score (20-day window)             |
| rsi               | RSI-14 (current)                    |
| macd              | MACD(12,26) (current)               |
| cci               | CCI-20 (current)                    |
| wr                | Williams %R-14 (current)            |
| atr               | ATR-14 (current)                    |
| pct_b             | Bollinger %B (current)              |
| gc                | bool — Golden Cross signal          |
| z_long / z_short  | bool — Z-score entry signals        |
| wr_ob / wr_os     | bool — Williams overbought/oversold |
| price             | latest close                        |
| price_chg_pct     | 1y price change %                   |
| ann_ret / ann_std | annualised return & volatility %    |
| quantsim_available| bool — C++ lib loaded               |

## Extending

- **Add indicators**: implement in `backend/app.py`, add to the `stats` dict,
  then add a `<StatPill>` in `frontend/src/App.jsx`.
- **Add chart panels**: extend `build_chart()` in `app.py` — the matplotlib
  figure is returned as a base64 PNG and displayed by the React `<img>` tag.
- **Production**: serve the Vite build (`npm run build`) via Flask's
  `static_folder` or nginx, remove `flask-cors`.
