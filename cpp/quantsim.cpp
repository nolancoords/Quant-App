#include <cmath>
#include <vector>
#include <numeric>
#include <algorithm>
#include <functional>
#include <stdexcept>
#include <random>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>

using namespace std;
namespace py = pybind11;

// ─────────────────────────────────────────────────────────────────────────────
// INTERNAL HELPERS  (not exposed — used by multiple indicators below)
// ─────────────────────────────────────────────────────────────────────────────

static double _mean(const vector<double>& v, size_t from, size_t to) {
    // mean of v[from..to] inclusive
    double s = 0;
    for (size_t i = from; i <= to; ++i) s += v[i];
    return s / (to - from + 1);
}

static double _std(const vector<double>& v, size_t from, size_t to, bool ddof1 = true) {
    double m = _mean(v, from, to);
    double var = 0;
    for (size_t i = from; i <= to; ++i) var += (v[i] - m) * (v[i] - m);
    size_t denom = (to - from + 1) - (ddof1 ? 1 : 0);
    return denom > 0 ? sqrt(var / denom) : 0.0;
}

static double _wilder_ema(const vector<double>& v, int period) {
    // Wilder smoothing: alpha = 1/period  (used for ATR, RSI)
    if ((int)v.size() < period) return 0.0;
    double s = 0;
    for (int i = 0; i < period; ++i) s += v[i];
    double ema = s / period;
    double alpha = 1.0 / period;
    for (size_t i = period; i < v.size(); ++i)
        ema = alpha * v[i] + (1 - alpha) * ema;
    return ema;
}

// ═════════════════════════════════════════════════════════════════════════════
// BASIC VALUATION FORMULAS  (unchanged from original)
// ═════════════════════════════════════════════════════════════════════════════

double PriceToEarnings(double price, double eps) {
    return eps != 0 ? price / eps : 0;
}
double PEG(double growthRate, double price, double eps) {
    return growthRate != 0 ? PriceToEarnings(price, eps) / growthRate : 0;
}
double PriceToBook(double marketPrice, double bookValuePerShare) {
    return bookValuePerShare != 0 ? marketPrice / bookValuePerShare : 0;
}
double DividendYield(double annualDividend, double stockPrice) {
    return stockPrice != 0 ? annualDividend / stockPrice : 0;
}
double EarningsYield(double eps, double price) {
    return price != 0 ? eps / price : 0;
}
double ROE(double netIncome, double equity) {
    return equity != 0 ? netIncome / equity : 0;
}
double ROA(double netIncome, double totalAssets) {
    return totalAssets != 0 ? netIncome / totalAssets : 0;
}
double DebtToEquity(double liabilities, double equity) {
    return equity != 0 ? liabilities / equity : 0;
}
double CurrentRatio(double currentAssets, double currentLiabilities) {
    return currentLiabilities != 0 ? currentAssets / currentLiabilities : 0;
}

// ═════════════════════════════════════════════════════════════════════════════
// MOVING AVERAGES  (original)
// ═════════════════════════════════════════════════════════════════════════════

double SMA(const vector<double>& prices) {
    if (prices.empty()) return 0;
    return accumulate(prices.begin(), prices.end(), 0.0) / prices.size();
}

double EMA(const vector<double>& prices, int period) {
    if (prices.empty()) return 0;
    double k = 2.0 / (period + 1);
    double ema = prices[0];
    for (size_t i = 1; i < prices.size(); ++i)
        ema = (prices[i] - ema) * k + ema;
    return ema;
}

// ── NEW: Kaufman Adaptive Moving Average ─────────────────────────────────────
// Returns the full rolling KAMA series (NaN-padded with 0 before warm-up).
// ER = |net change over er_period| / sum(|daily changes|, er_period)
// SC = [ER*(fast_sc - slow_sc) + slow_sc]²
// KAMA_t = KAMA_{t-1} + SC*(Price - KAMA_{t-1})
vector<double> KAMA(const vector<double>& prices,
                    int er_period = 10,
                    int fast = 2,
                    int slow = 30) {
    int n = prices.size();
    vector<double> out(n, 0.0);
    if (n <= er_period) return out;

    double fast_sc = 2.0 / (fast + 1);
    double slow_sc = 2.0 / (slow + 1);

    out[er_period] = prices[er_period];

    for (int i = er_period + 1; i < n; ++i) {
        double change = fabs(prices[i] - prices[i - er_period]);
        double vol = 0;
        for (int j = i - er_period; j < i; ++j)
            vol += fabs(prices[j + 1] - prices[j]);
        double er = (vol > 0) ? change / vol : 0.0;
        double sc = pow(er * (fast_sc - slow_sc) + slow_sc, 2);
        out[i] = out[i - 1] + sc * (prices[i] - out[i - 1]);
    }
    return out;
}

// ═════════════════════════════════════════════════════════════════════════════
// VOLATILITY & RISK  (original + new)
// ═════════════════════════════════════════════════════════════════════════════

double StandardDeviation(const vector<double>& values) {
    if (values.empty()) return 0;
    double mean = accumulate(values.begin(), values.end(), 0.0) / values.size();
    double var = 0;
    for (double v : values) var += (v - mean) * (v - mean);
    return sqrt(var / values.size());
}

double Beta(const vector<double>& stockReturns,
            const vector<double>& marketReturns) {
    if (stockReturns.size() != marketReturns.size() || stockReturns.empty()) return 0;
    double sm = accumulate(stockReturns.begin(),  stockReturns.end(),  0.0) / stockReturns.size();
    double mm = accumulate(marketReturns.begin(), marketReturns.end(), 0.0) / marketReturns.size();
    double cov = 0, mvar = 0;
    for (size_t i = 0; i < stockReturns.size(); ++i) {
        cov  += (stockReturns[i]  - sm) * (marketReturns[i] - mm);
        mvar += (marketReturns[i] - mm) * (marketReturns[i] - mm);
    }
    return mvar != 0 ? cov / mvar : 0;
}

double SharpeRatio(double portfolioReturn, double riskFreeRate, double stdDev) {
    return stdDev != 0 ? (portfolioReturn - riskFreeRate) / stdDev : 0;
}

// ── NEW: Average True Range (Wilder smoothing, close-only proxy) ──────────────
// TR_i = |Close_i - Close_{i-1}|  (true range requires H/L; this is the
//        standard close-only approximation used when OHLC is unavailable)
// ATR  = Wilder EMA(TR, period)
// Returns full series; index 0..period-1 are 0.
vector<double> ATR(const vector<double>& closes, int period = 14) {
    int n = closes.size();
    vector<double> out(n, 0.0);
    if (n < period + 1) return out;

    // build TR series (length n-1, offset +1 in price array)
    vector<double> tr(n, 0.0);
    for (int i = 1; i < n; ++i)
        tr[i] = fabs(closes[i] - closes[i - 1]);

    // seed with simple mean of first period TR values
    double seed = 0;
    for (int i = 1; i <= period; ++i) seed += tr[i];
    double atr = seed / period;
    out[period] = atr;

    double alpha = 1.0 / period;
    for (int i = period + 1; i < n; ++i) {
        atr = alpha * tr[i] + (1 - alpha) * atr;
        out[i] = atr;
    }
    return out;
}

// ── NEW: Rolling Bollinger Bands ──────────────────────────────────────────────
// Returns {mid, upper, lower, pct_b} each as a length-n vector.
// mid   = SMA(w)
// upper = mid + k*σ(w)
// lower = mid - k*σ(w)
// %B    = (Close - lower) / (upper - lower)
struct BollingerResult {
    vector<double> mid, upper, lower, pct_b;
};

BollingerResult BollingerBands(const vector<double>& prices,
                                int w = 20, double k = 2.0) {
    int n = prices.size();
    BollingerResult r;
    r.mid   = vector<double>(n, 0.0);
    r.upper = vector<double>(n, 0.0);
    r.lower = vector<double>(n, 0.0);
    r.pct_b = vector<double>(n, 0.5);

    for (int i = w - 1; i < n; ++i) {
        double m  = _mean(prices, i - w + 1, i);
        double sd = _std (prices, i - w + 1, i, true);
        r.mid[i]   = m;
        r.upper[i] = m + k * sd;
        r.lower[i] = m - k * sd;
        double bw  = r.upper[i] - r.lower[i];
        r.pct_b[i] = (bw > 0) ? (prices[i] - r.lower[i]) / bw : 0.5;
    }
    return r;
}

// ═════════════════════════════════════════════════════════════════════════════
// TECHNICAL INDICATORS  (original + new)
// ═════════════════════════════════════════════════════════════════════════════

double RSI(const vector<double>& prices, int period = 14) {
    if ((int)prices.size() <= period) return 0;
    double gains = 0, losses = 0;
    for (int i = 1; i <= period; ++i) {
        double d = prices[i] - prices[i - 1];
        if (d > 0) gains += d; else losses -= d;
    }
    if (losses == 0) return 100;
    return 100 - (100 / (1 + gains / losses));
}

double MACD(const vector<double>& prices) {
    return EMA(prices, 12) - EMA(prices, 26);
}

// ── NEW: Stochastic Oscillator ────────────────────────────────────────────────
// %K = (Close - LowestLow(k)) / (HighestHigh(k) - LowestLow(k)) * 100
// %D = SMA(%K, d_period)   ← signal line
// Returns {pct_k, pct_d} as full-length vectors.
struct StochasticResult {
    vector<double> pct_k, pct_d;
};

StochasticResult Stochastic(const vector<double>& prices,
                             int k_period = 14, int d_period = 3) {
    int n = prices.size();
    StochasticResult r;
    r.pct_k = vector<double>(n, 0.0);
    r.pct_d = vector<double>(n, 0.0);

    for (int i = k_period - 1; i < n; ++i) {
        double lo = *min_element(prices.begin() + i - k_period + 1, prices.begin() + i + 1);
        double hi = *max_element(prices.begin() + i - k_period + 1, prices.begin() + i + 1);
        double rng = hi - lo;
        r.pct_k[i] = (rng > 0) ? (prices[i] - lo) / rng * 100.0 : 50.0;
    }

    int d_start = k_period + d_period - 2;
    for (int i = d_start; i < n; ++i) {
        double s = 0;
        for (int j = i - d_period + 1; j <= i; ++j) s += r.pct_k[j];
        r.pct_d[i] = s / d_period;
    }
    return r;
}

// ── NEW: Williams %R ──────────────────────────────────────────────────────────
// %R = (HighestHigh - Close) / (HighestHigh - LowestLow) * -100
// Range: -100 (oversold) → 0 (overbought)
vector<double> WilliamsR(const vector<double>& prices, int period = 14) {
    int n = prices.size();
    vector<double> out(n, -50.0);
    for (int i = period - 1; i < n; ++i) {
        double lo = *min_element(prices.begin() + i - period + 1, prices.begin() + i + 1);
        double hi = *max_element(prices.begin() + i - period + 1, prices.begin() + i + 1);
        double rng = hi - lo;
        out[i] = (rng > 0) ? (hi - prices[i]) / rng * -100.0 : -50.0;
    }
    return out;
}

// ── NEW: Rate of Change ───────────────────────────────────────────────────────
// ROC = (Close - Close[n]) / Close[n] * 100
vector<double> ROC(const vector<double>& prices, int period = 10) {
    int n = prices.size();
    vector<double> out(n, 0.0);
    for (int i = period; i < n; ++i) {
        if (prices[i - period] != 0)
            out[i] = (prices[i] - prices[i - period]) / prices[i - period] * 100.0;
    }
    return out;
}

// ── NEW: Commodity Channel Index ──────────────────────────────────────────────
// TP  = Close  (approximation; true TP = (H+L+C)/3)
// CCI = (TP - SMA(TP, n)) / (0.015 * MeanAbsDev(TP, n))
vector<double> CCI(const vector<double>& prices, int period = 20) {
    int n = prices.size();
    vector<double> out(n, 0.0);
    for (int i = period - 1; i < n; ++i) {
        double m = _mean(prices, i - period + 1, i);
        double mad = 0;
        for (int j = i - period + 1; j <= i; ++j)
            mad += fabs(prices[j] - m);
        mad /= period;
        out[i] = (mad > 0) ? (prices[i] - m) / (0.015 * mad) : 0.0;
    }
    return out;
}

// ── NEW: OBV proxy (price-magnitude weighted directional cumsum) ───────────────
// OBV_i = OBV_{i-1} + sign(ΔP) * |ΔP|
// Without raw volume, price-move magnitude serves as the weight.
vector<double> OBVProxy(const vector<double>& prices) {
    int n = prices.size();
    vector<double> out(n, 0.0);
    for (int i = 1; i < n; ++i) {
        double d = prices[i] - prices[i - 1];
        out[i] = out[i - 1] + (d > 0 ? 1 : (d < 0 ? -1 : 0)) * fabs(d);
    }
    return out;
}

// ── NEW: Z-Score signal ───────────────────────────────────────────────────────
// Z = (Close - SMA(window)) / σ(window)
// |Z| > 2 → statistically anomalous; core of mean-reversion / stat-arb logic.
vector<double> ZScore(const vector<double>& prices, int window = 20) {
    int n = prices.size();
    vector<double> out(n, 0.0);
    for (int i = window - 1; i < n; ++i) {
        double m  = _mean(prices, i - window + 1, i);
        double sd = _std (prices, i - window + 1, i, true);
        out[i] = (sd > 0) ? (prices[i] - m) / sd : 0.0;
    }
    return out;
}

// ═════════════════════════════════════════════════════════════════════════════
// PORTFOLIO MATH  (original)
// ═════════════════════════════════════════════════════════════════════════════

double PortfolioReturn(const vector<double>& returns,
                       const vector<double>& weights) {
    if (returns.size() != weights.size()) return 0;
    double total = 0;
    for (size_t i = 0; i < returns.size(); ++i) total += returns[i] * weights[i];
    return total;
}

double CompoundReturn(double principal, double annualRate, int years) {
    return principal * pow(1 + annualRate, years);
}

double DiscountedCashFlow(const vector<double>& cashFlows, double discountRate) {
    double total = 0;
    for (size_t i = 0; i < cashFlows.size(); ++i)
        total += cashFlows[i] / pow(1 + discountRate, i + 1);
    return total;
}

double CAGR(double beginningValue, double endingValue, int years) {
    if (beginningValue <= 0 || years <= 0) return 0;
    return pow(endingValue / beginningValue, 1.0 / years) - 1;
}

// ═════════════════════════════════════════════════════════════════════════════
// ALGORITHMIC HELPERS  (original + new)
// ═════════════════════════════════════════════════════════════════════════════

bool GoldenCross(double shortMA, double longMA) { return shortMA > longMA; }
bool IsOversoldRSI(double rsi)                  { return rsi < 30; }
bool IsOverboughtRSI(double rsi)                { return rsi > 70; }

// Stochastic cross helpers
bool StochasticBullCross(double pct_k, double pct_d) { return pct_k > pct_d && pct_k < 20; }
bool StochasticBearCross(double pct_k, double pct_d) { return pct_k < pct_d && pct_k > 80; }

// Williams %R zone helpers
bool WROverBought(double wr) { return wr > -20; }
bool WROverSold(double wr)   { return wr < -80; }

// Z-score extreme helpers
bool ZScoreLong(double z)    { return z < -2.0; }
bool ZScoreShort(double z)   { return z > +2.0; }

// ═════════════════════════════════════════════════════════════════════════════
// CALCULUS  (original)
// ═════════════════════════════════════════════════════════════════════════════

double derivative(function<double(double)> f, double x, double h = 1e-7) {
    return (f(x + h) - f(x - h)) / (2.0 * h);
}
double derivative2(function<double(double)> f, double x) {
    double h = 0.0001;
    return (f(x + h) - 2 * f(x) + f(x - h)) / (h * h);
}
bool Momentum(function<double(double)> f, double t) {
    return derivative(f, t) > 0 && derivative2(f, t) > 0;
}

// ═════════════════════════════════════════════════════════════════════════════
// OPTIONS  (original)
// ═════════════════════════════════════════════════════════════════════════════

double BlackScholesCall(double S, double K, double T, double r, double sigma) {
    double d1 = (log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * sqrt(T));
    double d2 = d1 - sigma * sqrt(T);
    double N1 = 0.5 * (1 + erf(d1 / sqrt(2)));
    double N2 = 0.5 * (1 + erf(d2 / sqrt(2)));
    return S * N1 - K * exp(-r * T) * N2;
}

// ═════════════════════════════════════════════════════════════════════════════
// ORNSTEIN-UHLENBECK  (original)
// ═════════════════════════════════════════════════════════════════════════════

class OrnsteinUhlenbeck {
    double theta, sigma, dt, x;
    mt19937 rng;
    normal_distribution<double> normal;
public:
    OrnsteinUhlenbeck(double theta_, double sigma_, double dt_, double x0)
        : theta(theta_), sigma(sigma_), dt(dt_), x(x0),
          rng(random_device{}()), normal(0.0, 1.0) {}

    double step() {
        double dW = sqrt(dt) * normal(rng);
        x = x - theta * x * dt + sigma * dW;
        return x;
    }
    vector<double> simulate(int steps) {
        vector<double> path;
        path.reserve(steps);
        for (int i = 0; i < steps; ++i) path.push_back(step());
        return path;
    }
};

// ═════════════════════════════════════════════════════════════════════════════
// PYBIND11 MODULE
// ═════════════════════════════════════════════════════════════════════════════

PYBIND11_MODULE(quantsim, m) {

    // ── Moving averages ──
    m.def("SMA",  &SMA);
    m.def("EMA",  &EMA);
    m.def("KAMA", &KAMA, py::arg("prices"),
          py::arg("er_period")=10, py::arg("fast")=2, py::arg("slow")=30);

    // ── Volatility & risk ──
    m.def("StandardDeviation", &StandardDeviation);
    m.def("Beta",              &Beta);
    m.def("SharpeRatio",       &SharpeRatio);
    m.def("ATR",               &ATR,  py::arg("closes"), py::arg("period")=14);

    // ── Bollinger Bands (returns named tuple-like struct) ──
    py::class_<BollingerResult>(m, "BollingerResult")
        .def_readonly("mid",   &BollingerResult::mid)
        .def_readonly("upper", &BollingerResult::upper)
        .def_readonly("lower", &BollingerResult::lower)
        .def_readonly("pct_b", &BollingerResult::pct_b);
    m.def("BollingerBands", &BollingerBands,
          py::arg("prices"), py::arg("w")=20, py::arg("k")=2.0);

    // ── Technical indicators ──
    m.def("RSI",  &RSI,  py::arg("prices"), py::arg("period")=14);
    m.def("MACD", &MACD);
    m.def("ROC",  &ROC,  py::arg("prices"), py::arg("period")=10);
    m.def("CCI",  &CCI,  py::arg("prices"), py::arg("period")=20);
    m.def("ZScore", &ZScore, py::arg("prices"), py::arg("window")=20);
    m.def("OBVProxy", &OBVProxy);
    m.def("WilliamsR", &WilliamsR, py::arg("prices"), py::arg("period")=14);

    // ── Stochastic (returns named struct) ──
    py::class_<StochasticResult>(m, "StochasticResult")
        .def_readonly("pct_k", &StochasticResult::pct_k)
        .def_readonly("pct_d", &StochasticResult::pct_d);
    m.def("Stochastic", &Stochastic,
          py::arg("prices"), py::arg("k_period")=14, py::arg("d_period")=3);

    // ── Portfolio math ──
    m.def("CAGR",             &CAGR);
    m.def("PortfolioReturn",  &PortfolioReturn);
    m.def("CompoundReturn",   &CompoundReturn);
    m.def("DiscountedCashFlow", &DiscountedCashFlow);

    // ── Valuation ratios ──
    m.def("PriceToEarnings", &PriceToEarnings);
    m.def("PEG",             &PEG);
    m.def("PriceToBook",     &PriceToBook);
    m.def("DividendYield",   &DividendYield);
    m.def("EarningsYield",   &EarningsYield);
    m.def("ROE",             &ROE);
    m.def("ROA",             &ROA);
    m.def("DebtToEquity",    &DebtToEquity);
    m.def("CurrentRatio",    &CurrentRatio);
    m.def("BlackScholesCall",&BlackScholesCall);

    // ── Signal helpers ──
    m.def("GoldenCross",         &GoldenCross);
    m.def("IsOversoldRSI",       &IsOversoldRSI);
    m.def("IsOverboughtRSI",     &IsOverboughtRSI);
    m.def("StochasticBullCross", &StochasticBullCross);
    m.def("StochasticBearCross", &StochasticBearCross);
    m.def("WROverBought",        &WROverBought);
    m.def("WROverSold",          &WROverSold);
    m.def("ZScoreLong",          &ZScoreLong);
    m.def("ZScoreShort",         &ZScoreShort);

    // ── Calculus ──
    m.def("derivative",  &derivative);
    m.def("derivative2", &derivative2);
    m.def("Momentum",    &Momentum);

    // ── Stochastic process ──
    py::class_<OrnsteinUhlenbeck>(m, "OrnsteinUhlenbeck")
        .def(py::init<double, double, double, double>())
        .def("simulate", &OrnsteinUhlenbeck::simulate);
}