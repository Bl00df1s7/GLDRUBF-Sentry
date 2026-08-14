#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NG / NGM Futures Strategy — Backtesting Engine v4
==================================================

Standalone script для переноса в Qwen Coder.
Включает: непрерывные серии, v3-логику (HTF фильтр, откатные входы, безубыток),
анатомию рынка (диагностику свойств) и полный отчёт.

Использование:
    export T_SANDBOXAPI="ваш_токен"
    python ng_strategy.py
    python ng_strategy.py --base NG --regime trend --plot
    python ng_strategy.py --start-date 2022-01-01 --output-csv trades.csv
"""

import os
import re
import sys
import argparse
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

# T-Invest API
try:
    from t_tech.invest import Client, CandleInterval
except ImportError:
    print("Установи t-tech-investments:")
    print("  pip install t-tech-investments --index-url "
          "https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple")
    sys.exit(1)


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class Config:
    token: str
    start_date: datetime
    end_date: datetime
    bases: tuple = ("NG", "NGM")
    roll_days: int = 5
    min_bars_segment: int = 150

    initial_capital: float = 100_000.0
    commission_pct: float = 0.05
    slippage_pct: dict = None  # заполняется в post-init

    sl_atr: float = 1.5
    tp_atr: float = 2.0
    be_atr: float = 1.0
    max_hold_bars: int = 50

    def __post_init__(self):
        if self.slippage_pct is None:
            self.slippage_pct = {"NG": 0.05, "NGM": 0.10}


# =============================================================================
# DATA LOADING
# =============================================================================

MONTH_CODES = "FGHJKMNQUVXZ"


def quotation_to_float(value) -> float:
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    if hasattr(value, "units") and hasattr(value, "nano"):
        return float(value.units) + float(value.nano) / 1_000_000_000
    if hasattr(value, "value"):
        return float(value.value)
    return float(value)


def load_candles(client, uid, start_date, end_date) -> pd.DataFrame:
    rows = []
    current = start_date
    chunk = timedelta(days=90)

    while current < end_date:
        chunk_end = min(current + chunk, end_date)
        response = client.market_data.get_candles(
            instrument_id=uid,
            from_=current, to=chunk_end,
            interval=CandleInterval.CANDLE_INTERVAL_HOUR,
        )
        for c in response.candles:
            rows.append({
                "time": c.time,
                "open": quotation_to_float(c.open),
                "high": quotation_to_float(c.high),
                "low": quotation_to_float(c.low),
                "close": quotation_to_float(c.close),
                "volume": c.volume,
            })
        current = chunk_end

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def parse_base_ticker(ticker: str) -> Optional[str]:
    m = re.match(rf"^([A-Z]+)([{MONTH_CODES}])(\d)$", (ticker or "").upper())
    return m.group(1) if m else None


def load_all_contracts(client, bases) -> pd.DataFrame:
    resp = client.instruments.futures()
    rows = [
        {
            "base": parse_base_ticker(x.ticker),
            "ticker": x.ticker,
            "uid": x.uid,
            "expiration_date": pd.to_datetime(x.expiration_date, utc=True),
        }
        for x in resp.instruments
    ]
    df = pd.DataFrame(rows)
    df = df[df["base"].isin(bases)]
    return df.sort_values(["base", "expiration_date"]).reset_index(drop=True)


def build_continuous_series(
    client, contracts, start, end,
    roll_days: int = 5, min_bars: int = 150
) -> pd.DataFrame:
    """Сшивка фронт-месячных контрактов, аддитивный бэк-аджастмент."""
    segments = []
    prev_expiry = None

    for _, c in contracts.iterrows():
        win_start = (prev_expiry - timedelta(days=roll_days)
                     if prev_expiry is not None else start)
        win_end = c["expiration_date"] - timedelta(days=roll_days)

        if win_end > win_start:
            dfc = load_candles(client, c["uid"], win_start, win_end)
            if len(dfc) >= min_bars:
                segments.append(dfc)
                print(f"    {c['ticker']}: {len(dfc)} баров "
                      f"[{win_start.date()} → {win_end.date()}]")
        prev_expiry = c["expiration_date"]

    if not segments:
        return pd.DataFrame()

    offsets = [0.0] * len(segments)
    for i in range(len(segments) - 1, 0, -1):
        gap = segments[i]["close"].iloc[0] - segments[i - 1]["close"].iloc[-1]
        offsets[i - 1] = offsets[i] + gap

    adjusted = []
    for seg, off in zip(segments, offsets):
        s = seg.copy()
        s[["open", "high", "low", "close"]] += off
        adjusted.append(s)

    return (pd.concat(adjusted)
              .drop_duplicates("time")
              .sort_values("time")
              .reset_index(drop=True))


# =============================================================================
# MARKET ANATOMY — диагностика свойств рынка
# =============================================================================

def market_anatomy(df: pd.DataFrame, name: str) -> dict:
    d = df.set_index("time")["close"].resample("D").last().dropna()
    ret = d.pct_change().dropna()

    print("=" * 85)
    print(f"MARKET ANATOMY: {name} | daily bars: {len(d)}")
    print("=" * 85)

    # ACF
    ac = [ret.autocorr(l) for l in [1, 2, 3, 5, 10]]
    print("\nACF daily returns (lag 1,2,3,5,10):")
    print("  " + " | ".join(f"{x:+.3f}" for x in ac))

    # Variance ratio 5d
    ret5 = d.resample("5D").last().pct_change().dropna()
    vr = ret5.var() / (ret.var() * 5) if ret.var() > 0 else np.nan
    print(f"\nVariance ratio 5d: {vr:.2f}   (>1 trend, <1 mean rev)")

    # Volatility clustering
    ac_vol = [abs(ret).autocorr(l) for l in [1, 5, 10]]
    print("ACF |returns| (1,5,10): " + " | ".join(f"{x:+.3f}" for x in ac_vol))

    # Сезонность
    monthly = ret.groupby(ret.index.month).mean() * 100
    print("\nСредняя дневная доходность по месяцам (%):")
    print("  " + " | ".join(f"{m}:{v:+.3f}" for m, v in monthly.items()))

    # Fade-the-spike
    std = ret.rolling(60).std().shift(1)
    fwd5 = ((d.shift(-5) / d - 1) * 100).loc[ret.index]
    big_dn = ret < -2 * std
    big_up = ret > 2 * std
    print(f"\nПосле ОБВАЛА > 2σ:  n={int(big_dn.sum()):3d} | "
          f"ср. 5д: {fwd5[big_dn].mean():+.2f}%")
    print(f"После ВСПЛЕСКА > 2σ: n={int(big_up.sum()):3d} | "
          f"ср. 5д: {fwd5[big_up].mean():+.2f}%")
    print(f"Базовое среднее 5 дней:             {fwd5.mean():+.2f}%")

    # Часовая структура
    h = df.copy()
    h["ret"] = h["close"].pct_change()
    hr = h.groupby(h["time"].dt.hour)["ret"].mean() * 100
    top = hr.dropna().abs().sort_values(ascending=False).head(5)
    print("\nТоп-5 часов по средней |доходности| (UTC, %):")
    print("  " + " | ".join(f"{int(k)}h:{v:+.4f}" for k, v in top.items()))

    return {
        "name": name,
        "ac1": ac[0],
        "vr5": vr,
        "ac_vol1": ac_vol[0],
    }


# =============================================================================
# SIGNAL GENERATOR — v3
# =============================================================================

class SignalGenerator:

    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()

        # ATR
        prev_close = data["close"].shift(1)
        tr = pd.concat([
            data["high"] - data["low"],
            (data["high"] - prev_close).abs(),
            (data["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        data["atr"] = tr.rolling(14).mean()

        # Volume, нормированный на час суток
        data["hour"] = data["time"].dt.hour
        data["vol_hour_ma"] = (
            data.groupby("hour")["volume"]
            .transform(lambda s: s.rolling(20, min_periods=10).mean())
        )
        data["volume_ratio_norm"] = (
            data["volume"] / data["vol_hour_ma"]
        ).replace([np.inf, -np.inf], np.nan)

        # MACD
        ema_fast = data["close"].ewm(span=12, adjust=False).mean()
        ema_slow = data["close"].ewm(span=26, adjust=False).mean()
        data["macd"] = ema_fast - ema_slow
        data["macd_signal"] = data["macd"].ewm(span=9, adjust=False).mean()
        data["macd_hist"] = data["macd"] - data["macd_signal"]

        # RSI
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        data["rsi"] = 100 - (100 / (1 + gain / loss))

        # Ichimoku
        data["ichi_tenkan"] = (
            data["high"].rolling(9).max() + data["low"].rolling(9).min()
        ) / 2
        data["ichi_kijun"] = (
            data["high"].rolling(26).max() + data["low"].rolling(26).min()
        ) / 2
        span_a = (data["ichi_tenkan"] + data["ichi_kijun"]) / 2
        span_b = (
            data["high"].rolling(52).max() + data["low"].rolling(52).min()
        ) / 2
        data["ichi_cloud_top"] = pd.concat(
            [span_a.shift(26), span_b.shift(26)], axis=1
        ).max(axis=1)
        data["ichi_cloud_bottom"] = pd.concat(
            [span_a.shift(26), span_b.shift(26)], axis=1
        ).min(axis=1)
        data["above_cloud"] = data["close"] > data["ichi_cloud_top"]
        data["below_cloud"] = data["close"] < data["ichi_cloud_bottom"]
        data["inside_cloud"] = ~data["above_cloud"] & ~data["below_cloud"]

        # HTF-фильтр: D1 EMA50, без look-ahead
        d1 = data.set_index("time")["close"].resample("D").last().dropna()
        d1_up = (d1 > d1.ewm(span=50).mean()).shift(1)
        map_df = d1_up.rename("htf_up").reset_index()
        map_df["date"] = map_df["time"].dt.date
        data["date"] = data["time"].dt.date
        data = data.merge(map_df[["date", "htf_up"]], on="date", how="left")
        data = data.drop(columns=["date"])

        return data

    @staticmethod
    def detect_macd_divergence(data: pd.DataFrame) -> pd.DataFrame:
        result = data.copy()
        result["bullish_div"] = False
        result["bearish_div"] = False

        L, R = 3, 3
        result["pivot_low"] = (
            result["low"] == result["low"].rolling(L + R + 1, center=True).min()
        ).shift(R).fillna(False)
        result["pivot_high"] = (
            result["high"] == result["high"].rolling(L + R + 1, center=True).max()
        ).shift(R).fillna(False)

        last_lp, last_lm = np.nan, np.nan
        last_hp, last_hm = np.nan, np.nan

        for i in range(len(result)):
            if result["pivot_low"].iloc[i]:
                p = i - R
                cp, cm = result["low"].iloc[p], result["macd"].iloc[p]
                if not pd.isna(last_lp) and cp < last_lp and cm > last_lm:
                    result.iloc[i, result.columns.get_loc("bullish_div")] = True
                last_lp, last_lm = cp, cm

            if result["pivot_high"].iloc[i]:
                p = i - R
                cp, cm = result["high"].iloc[p], result["macd"].iloc[p]
                if not pd.isna(last_hp) and cp > last_hp and cm < last_hm:
                    result.iloc[i, result.columns.get_loc("bearish_div")] = True
                last_hp, last_hm = cp, cm

        return result

    @staticmethod
    def generate_signals(data: pd.DataFrame) -> pd.DataFrame:
        result = data.copy()
        kij = data["ichi_kijun"]

        touched_above = data["high"].rolling(3).max() >= kij
        touched_below = data["low"].rolling(3).min() <= kij

        # TREND: откат к Kijun в направлении D1-тренда
        result["trend_short"] = (
            (data["htf_up"] == False)
            & touched_above
            & (data["close"] < kij)
            & (data["close"] < data["open"])
        )
        result["trend_long"] = (
            (data["htf_up"] == True)
            & touched_below
            & (data["close"] > kij)
            & (data["close"] > data["open"])
        )

        # MEAN_REV: дивергенция + облако + RSI
        result["mean_rev_long"] = (
            data["bullish_div"] & data["inside_cloud"] & (data["rsi"] < 40)
        )
        result["mean_rev_short"] = (
            data["bearish_div"] & data["inside_cloud"] & (data["rsi"] > 60)
        )

        return result


# =============================================================================
# TRADE SIMULATOR
# =============================================================================

class TradeSimulator:

    def __init__(self, initial_capital, commission_pct, slippage_pct, be_atr):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct / 100
        self.slippage_pct = slippage_pct / 100
        self.be_atr = be_atr
        self.trades = []

    def simulate_trade(self, entry_time, entry_price, direction,
                       stop_loss, take_profit, data_window, atr=None):
        slip = self.slippage_pct
        actual_entry = (entry_price * (1 + slip) if direction == "LONG"
                        else entry_price * (1 - slip))

        stop = stop_loss
        mae = mfe = 0.0
        exit_price = exit_time = exit_reason = None
        bars_held = len(data_window)

        for j, (idx, row) in enumerate(data_window.iterrows()):
            bh = row["high"]
            bl = row["low"]

            if direction == "LONG":
                if bl <= stop:
                    exit_price = stop * (1 - slip)
                    exit_time = row["time"]
                    exit_reason = "BREAKEVEN" if stop >= actual_entry else "STOP_LOSS"
                    bars_held = j + 1
                    break
                if atr is not None and not np.isnan(atr) \
                        and bh >= actual_entry + self.be_atr * atr:
                    stop = max(stop, actual_entry)
                mae = min(mae, (bl - actual_entry) / actual_entry)
                mfe = max(mfe, (bh - actual_entry) / actual_entry)
                if bh >= take_profit:
                    exit_price = take_profit * (1 - slip)
                    exit_time = row["time"]
                    exit_reason = "TAKE_PROFIT"
                    bars_held = j + 1
                    break
            else:
                if bh >= stop:
                    exit_price = stop * (1 + slip)
                    exit_time = row["time"]
                    exit_reason = "BREAKEVEN" if stop <= actual_entry else "STOP_LOSS"
                    bars_held = j + 1
                    break
                if atr is not None and not np.isnan(atr) \
                        and bl <= actual_entry - self.be_atr * atr:
                    stop = min(stop, actual_entry)
                mae = min(mae, (actual_entry - bh) / actual_entry)
                mfe = max(mfe, (actual_entry - bl) / actual_entry)
                if bl <= take_profit:
                    exit_price = take_profit * (1 + slip)
                    exit_time = row["time"]
                    exit_reason = "TAKE_PROFIT"
                    bars_held = j + 1
                    break

        if exit_price is None:
            last = data_window.iloc[-1]
            exit_price = (last["close"] * (1 - slip) if direction == "LONG"
                          else last["close"] * (1 + slip))
            exit_time = last["time"]
            exit_reason = "TIME_EXIT"

        pnl = ((exit_price - actual_entry) / actual_entry if direction == "LONG"
               else (actual_entry - exit_price) / actual_entry)

        return {
            "entry_time": entry_time,
            "exit_time": exit_time,
            "direction": direction,
            "entry_price": actual_entry,
            "exit_price": exit_price,
            "pnl_pct": (pnl - 2 * self.commission_pct) * 100,
            "mae_pct": mae * 100,
            "mfe_pct": mfe * 100,
            "duration_hours": (exit_time - entry_time).total_seconds() / 3600,
            "exit_reason": exit_reason,
            "bars_held": bars_held,
        }

    def add_trade(self, trade):
        self.trades.append(trade)

    def get_trades_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.trades)


# =============================================================================
# RISK METRICS
# =============================================================================

class RiskMetrics:

    @staticmethod
    def calculate_metrics(trades_df: pd.DataFrame,
                          initial_capital: float) -> dict:
        if trades_df is None or trades_df.empty:
            return {"error": "No trades"}

        t = trades_df.sort_values("entry_time").reset_index(drop=True)

        total = len(t)
        wins = int((t["pnl_pct"] > 0).sum())
        losses = int((t["pnl_pct"] < 0).sum())
        win_rate = wins / total * 100

        gross_profit = t.loc[t["pnl_pct"] > 0, "pnl_pct"].sum()
        gross_loss = abs(t.loc[t["pnl_pct"] < 0, "pnl_pct"].sum())
        profit_factor = (gross_profit / gross_loss
                         if gross_loss > 0 else np.inf)

        avg_win = t.loc[t["pnl_pct"] > 0, "pnl_pct"].mean()
        avg_loss = t.loc[t["pnl_pct"] < 0, "pnl_pct"].mean()
        expectancy = ((win_rate / 100) * avg_win
                      + (1 - win_rate / 100) * avg_loss)

        equity = [initial_capital]
        for _, tr in t.iterrows():
            equity.append(equity[-1] * (1 + tr["pnl_pct"] / 100))
        equity = pd.Series(equity)

        returns = equity.pct_change().dropna()
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252 * 24)
        else:
            sharpe = 0

        neg = returns[returns < 0]
        if len(neg) > 1 and neg.std() > 0:
            sortino = (returns.mean() / neg.std()) * np.sqrt(252 * 24)
        else:
            sortino = 0

        cummax = equity.cummax()
        max_dd = ((equity - cummax) / cummax).min() * 100

        days = (t["exit_time"].max() - t["entry_time"].min()).days
        cagr = (((equity.iloc[-1] / initial_capital) ** (365 / max(days, 1)) - 1)
                * 100 if days > 0 else 0)

        return {
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": losses,
            "win_rate_%": win_rate,
            "avg_win_%": avg_win,
            "avg_loss_%": avg_loss,
            "profit_factor": profit_factor,
            "expectancy_%": expectancy,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_%": max_dd,
            "cagr_%": cagr,
            "avg_mae_%": t["mae_pct"].mean(),
            "avg_mfe_%": t["mfe_pct"].mean(),
            "exit_reasons": (t["exit_reason"]
                             .value_counts(normalize=True).mul(100).to_dict()),
            "equity_curve": equity,
        }


# =============================================================================
# STRATEGY
# =============================================================================

class Strategy:

    def __init__(self, config: Config, slippage_pct: float):
        self.sl_atr = config.sl_atr
        self.tp_atr = config.tp_atr
        self.max_hold = config.max_hold_bars
        self.simulator = TradeSimulator(
            initial_capital=config.initial_capital,
            commission_pct=config.commission_pct,
            slippage_pct=slippage_pct,
            be_atr=config.be_atr,
        )

    def run_backtest(self, data: pd.DataFrame, regime: str) -> pd.DataFrame:
        lock_until = -1

        for i in range(len(data) - 1):
            if i < lock_until:
                continue

            row = data.iloc[i]
            direction = None

            if regime == "trend":
                if row.get("trend_long", False):
                    direction = "LONG"
                elif row.get("trend_short", False):
                    direction = "SHORT"
            elif regime == "mean_rev":
                if row.get("mean_rev_long", False):
                    direction = "LONG"
                elif row.get("mean_rev_short", False):
                    direction = "SHORT"

            if direction is None:
                continue

            atr = row["atr"]
            if pd.isna(atr):
                continue

            entry = row["close"]
            if direction == "LONG":
                sl = entry - atr * self.sl_atr
                tp = entry + atr * self.tp_atr
            else:
                sl = entry + atr * self.sl_atr
                tp = entry - atr * self.tp_atr

            window = data.iloc[i + 1: i + 1 + self.max_hold]
            if len(window) < 5:
                continue

            trade = self.simulator.simulate_trade(
                entry_time=row["time"],
                entry_price=entry,
                direction=direction,
                stop_loss=sl,
                take_profit=tp,
                data_window=window,
                atr=atr,
            )
            trade["regime"] = regime
            self.simulator.add_trade(trade)

            lock_until = i + 1 + trade["bars_held"]

        return self.simulator.get_trades_df()


# =============================================================================
# REPORTER
# =============================================================================

def print_summary(tag: str, trades_df: pd.DataFrame, initial_capital: float):
    if trades_df is None or trades_df.empty:
        print(f"  {tag:30s}: нет сделок")
        return
    m = RiskMetrics.calculate_metrics(trades_df, initial_capital)
    print(f"  {tag:30s} N={m['total_trades']:4d} | "
          f"WR={m['win_rate_%']:5.1f}% | PF={m['profit_factor']:5.2f} | "
          f"Expect={m['expectancy_%']:+.2f}% | "
          f"MDD={m['max_drawdown_%']:6.1f}% | "
          f"MFE={m['avg_mfe_%']:.2f} MAE={m['avg_mae_%']:.2f}")


def print_detailed_report(key: str, trades_df: pd.DataFrame,
                          initial_capital: float):
    if trades_df is None or trades_df.empty:
        return
    m = RiskMetrics.calculate_metrics(trades_df, initial_capital)

    print("\n" + "=" * 90)
    print(f"REGIME: {key.upper()}")
    print("=" * 90)
    print(f"  Trades: {m['total_trades']} "
          f"(W={m['winning_trades']}, L={m['losing_trades']}) | "
          f"WR={m['win_rate_%']:.1f}%")
    print(f"  AvgWin={m['avg_win_%']:.2f}% | AvgLoss={m['avg_loss_%']:.2f}% | "
          f"PF={m['profit_factor']:.2f} | Expect={m['expectancy_%']:+.2f}%")
    print(f"  Sharpe={m['sharpe_ratio']:.2f} | Sortino={m['sortino_ratio']:.2f} | "
          f"MDD={m['max_drawdown_%']:.1f}% | CAGR={m['cagr_%']:.1f}%")
    print(f"  MAE={m['avg_mae_%']:.2f}% | MFE={m['avg_mfe_%']:.2f}%")
    print("  Exits: "
          + " | ".join(f"{k}={v:.0f}%" for k, v in m["exit_reasons"].items()))

    worst = trades_df.loc[trades_df["pnl_pct"].idxmin()]
    best = trades_df.loc[trades_df["pnl_pct"].idxmax()]
    print(f"  Worst: {worst['pnl_pct']:.2f}% ({worst['entry_time']} → "
          f"{worst['exit_time']}, {worst['exit_reason']})")
    print(f"  Best:  {best['pnl_pct']:+.2f}% ({best['entry_time']} → "
          f"{best['exit_time']}, {best['exit_reason']})")


def plot_equity(trades_pool: pd.DataFrame, initial_capital: float):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates  # noqa: F401
    except ImportError:
        print("⚠ matplotlib не установлен, график пропущен")
        return

    fig, axes = plt.subplots(1, 2, figsize=(18, 6))

    for regime in ["trend", "mean_rev"]:
        sub = trades_pool[trades_pool["regime"] == regime].sort_values("entry_time")
        if sub.empty:
            continue
        eq = [initial_capital]
        for _, t in sub.iterrows():
            eq.append(eq[-1] * (1 + t["pnl_pct"] / 100))
        axes[0].plot(sub["exit_time"], eq[1:], label=f"POOL {regime}", lw=2)

    axes[0].set_title("Pooled Equity (NG+NGM)")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    sub = trades_pool[trades_pool["regime"] == "trend"].sort_values("entry_time")
    if not sub.empty:
        colors = ["green" if x > 0 else "red" for x in sub["pnl_pct"]]
        axes[1].bar(range(len(sub)), sub["pnl_pct"], color=colors, alpha=0.7)
        axes[1].axhline(0, color="k", lw=0.5)
        axes[1].set_title(f"POOL trend: P&L (N={len(sub)})")

    plt.tight_layout()
    plt.show()


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="NG/NGM Futures Strategy Backtest")
    p.add_argument("--token", type=str, default=None,
                   help="T-Invest token (или env T_SANDBOXAPI)")
    p.add_argument("--base", type=str, default="NG,NGM",
                   help="Список базовых тикеров через запятую")
    p.add_argument("--start-date", type=str, default="2023-01-01",
                   help="YYYY-MM-DD")
    p.add_argument("--regime", type=str, default="all",
                   choices=["trend", "mean_rev", "all"],
                   help="Режим торговли")
    p.add_argument("--plot", action="store_true",
                   help="Показать график equity")
    p.add_argument("--output-csv", type=str, default=None,
                   help="Сохранить сделки в CSV")
    p.add_argument("--anatomy-only", action="store_true",
                   help="Только анатомия рынка, без бэктеста")
    return p.parse_args()


def main():
    args = parse_args()

    token = args.token or os.environ.get("T_SANDBOXAPI")
    if not token:
        print("Ошибка: нужен токен (--token или env T_SANDBOXAPI)")
        sys.exit(1)

    bases = tuple(b.strip().upper() for b in args.base.split(","))
    start = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)

    config = Config(token=token, start_date=start, end_date=end, bases=bases)

    regimes = ["trend", "mean_rev"] if args.regime == "all" else [args.regime]

    # --- LOAD DATA ---
    with Client(token) as client:
        contracts = load_all_contracts(client, bases)
    print("\nКонтрактов по базам:")
    print(contracts.groupby("base").size().to_string())

    series: Dict[str, pd.DataFrame] = {}
    with Client(token) as client:
        for base, grp in contracts.groupby("base"):
            print(f"\n=== {base} ===")
            series[base] = build_continuous_series(
                client, grp, start, end,
                roll_days=config.roll_days,
                min_bars=config.min_bars_segment,
            )

    for base, s in series.items():
        if not s.empty:
            print(f"\n{base}: {len(s)} баров | "
                  f"{s['time'].iloc[0].date()} → {s['time'].iloc[-1].date()}")

    # --- ANATOMY ---
    for base, s in series.items():
        if not s.empty:
            market_anatomy(s, base)

    if args.anatomy_only:
        print("\n✓ anatomy-only mode, завершение.")
        return

    # --- BACKTESTS ---
    results: Dict[str, dict] = {}
    all_trades: List[pd.DataFrame] = []

    for base, data_raw in series.items():
        if data_raw.empty:
            continue

        data = SignalGenerator.calculate_indicators(data_raw)
        data = SignalGenerator.detect_macd_divergence(data)
        data = SignalGenerator.generate_signals(data)
        data = data.dropna().reset_index(drop=True)

        print(f"\n{'#' * 70}")
        print(f"# {base}: {len(data)} баров | "
              f"trend L/S: {int(data['trend_long'].sum())}/"
              f"{int(data['trend_short'].sum())} | "
              f"mr L/S: {int(data['mean_rev_long'].sum())}/"
              f"{int(data['mean_rev_short'].sum())}")

        for regime in regimes:
            strat = Strategy(config, slippage_pct=config.slippage_pct.get(base, 0.05))
            trades_df = strat.run_backtest(data, regime)

            if len(trades_df):
                trades_df["instrument"] = base
                results[f"{base}_{regime}"] = {
                    "trades": trades_df,
                    "metrics": RiskMetrics.calculate_metrics(
                        trades_df, config.initial_capital
                    ),
                }
                all_trades.append(trades_df)
                print(f"  ✓ {regime}: {len(trades_df)} сделок")
            else:
                print(f"  ⚠ {regime}: нет сделок")

    trades_pool = (pd.concat(all_trades, ignore_index=True)
                   if all_trades else pd.DataFrame())

    # --- SUMMARY ---
    print("\n" + "=" * 100)
    print("PER-INSTRUMENT & POOLED SUMMARY")
    print("=" * 100)
    for key, d in results.items():
        print_summary(key, d["trades"], config.initial_capital)

    print("-" * 100)
    if not trades_pool.empty:
        print_summary("POOL trend (NG+NGM)",
                      trades_pool[trades_pool["regime"] == "trend"],
                      config.initial_capital)
        print_summary("POOL mean_rev (NG+NGM)",
                      trades_pool[trades_pool["regime"] == "mean_rev"],
                      config.initial_capital)
        print_summary("POOL ALL", trades_pool, config.initial_capital)

        t_ng = set(trades_pool[trades_pool.instrument == "NG"]["entry_time"].dt.floor("h"))
        t_ngm = set(trades_pool[trades_pool.instrument == "NGM"]["entry_time"].dt.floor("h"))
        dup = len(t_ng & t_ngm) / max(1, min(len(t_ng), len(t_ngm)))
        print(f"\nДубликация сигналов NG∩NGM: {dup:.0%} "
              f"(при >70% эффективный N ≈ N одного инструмента)")

    # --- DETAILED REPORT ---
    for key, d in results.items():
        print_detailed_report(key, d["trades"], config.initial_capital)

    # --- SAVE ---
    if args.output_csv and not trades_pool.empty:
        trades_pool.to_csv(args.output_csv, index=False)
        print(f"\n✓ Сделки сохранены: {args.output_csv}")

    # --- PLOT ---
    if args.plot and not trades_pool.empty:
        plot_equity(trades_pool, config.initial_capital)


if __name__ == "__main__":
    main()
