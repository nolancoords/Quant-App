# Quant App

A full-stack quantitative finance dashboard built with **Flask, React (Vite), NumPy, Pandas, Matplotlib**, and an optional high-performance **C++ pybind11 module (`quantsim`)** for financial indicators.

---

## Structure

```
quant_app/
├── backend/
│   ├── app.py        
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   └── main.jsx
    ├── index.html
    ├── package.json
    └── vite.config.js    ← proxies /api → Flask :8000
```

---

## Setup

## 0 — Build C++ Quant Library (REQUIRED FIRST STEP)

Before running anything, you must compile and install the C++ `pybind11` module (`quantsim`).

This step generates the `quantsim` Python extension used by the backend.

### Install build dependencies

```bash
pip install pybind11 setuptools wheel
```

---

### Build and install the module

From the project root (where your `setup.py` or `CMakeLists.txt` is located):

```bash
pip install .
```

Or for development mode:

```bash
pip install -e .
```

---

### What this does

- Compiles `quantsim.cpp`
- Links `pybind11` bindings (`PYBIND11_MODULE`)
- Generates the compiled extension (`quantsim.pyd` on Windows)
- Makes the module importable in Python:

```python
import quantsim
```

---

### Verify installation

```bash
python -c "import quantsim; print(dir(quantsim))"
```

If this runs successfully, the C++ layer is correctly installed.

---

## 1
Simply open up the folder and run build.bat to setup both the frontend and backend together, which will then open up a local server. 

## 2 extra info

## API

| Method | Endpoint     | Body                     | Returns |
|--------|-------------|--------------------------|----------|
| GET    | /api/tickers | —                        | `{ tickers: [...] }` |
| POST   | /api/run     | `{ ticker: "NVDA" }`     | `{ ticker, stats, chart (base64), sparkline, dates }` |

---

## Stats Output

| Field | Description |
|------|-------------|
| cagr | Annualized CAGR |
| sharpe | Sharpe ratio |
| beta | 60-day beta vs S&P 500 |
| z | 20-day Z-score |
| rsi | RSI-14 |
| macd | MACD(12,26) |
| cci | Commodity Channel Index |
| wr | Williams %R |
| atr | Average True Range |
| pct_b | Bollinger Band %B |
| gc | Golden cross signal |
| z_long / z_short | Z-score entry signals |
| wr_ob / wr_os | Overbought/oversold signals |
| price | Latest closing price |
| price_chg_pct | 1-year price change |
| ann_ret / ann_std | Annual return & volatility |
| quantsim_available | Whether C++ module is loaded |

---

## Extending the Project

### Add new indicators
- Implement in `backend/app.py`
- Add to `stats` dictionary
- Display in `frontend/src/App.jsx` using a new `<StatPill />`

---

### Add new charts
- Modify `build_chart()` in `app.py`
- Matplotlib figure is returned as a base64 PNG
- Rendered in React via `<img />`

---

### Production deployment
- Run `npm run build` in frontend
- Serve static build via Flask or nginx
- Remove `flask-cors` in production

---

## Notes

- C++ extension is optional but recommended for performance
- Backend is designed to gracefully degrade if `quantsim` is unavailable
- Frontend communicates via `/api/run` proxy through Vite

---

## Tech Stack

- Python (Flask)
- React (Vite)
- NumPy / Pandas
- Matplotlib
- yfinance
- C++ (pybind11 optional acceleration layer)
```
