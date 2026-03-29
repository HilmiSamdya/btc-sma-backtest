import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import glob

SMA_FAST = 50
SMA_SLOW = 100
TICKS_TP = 50000
TICKS_SL = 30000
TICK_SIZE = 0.1

def run_backtest(SMA_FAST, SMA_SLOW, TICKS_TP, TICKS_SL, TICK_SIZE):
    files = sorted(
        glob.glob("btcusdt2024h1/BTCUSDT-1h-2024-*.csv")
        + glob.glob("btcusdt2025h1/BTCUSDT-1h-2025-*.csv")
        + glob.glob("btcusdt2023h1/BTCUSDT-1h-2023-*.csv")
        + glob.glob("btcusdt2022h1/BTCUSDT-1h-2022-*.csv")
    )
    dfs = []
    for f in files:
        df_temp = pd.read_csv(f)
        df_temp["close"] = df_temp["close"].astype(float)
        df_temp["high"] = df_temp["high"].astype(float)
        df_temp["low"] = df_temp["low"].astype(float)
        df_temp["open_time"] = (
            pd.to_datetime(df_temp["open_time"], unit="ms", utc=True)
            .dt.tz_convert("Asia/Jakarta")
        )
        dfs.append(df_temp)

    df = pd.concat(dfs, ignore_index=True)
    df = df.sort_values("open_time").drop_duplicates(subset="open_time").reset_index(drop=True)

    df["sma_fast"] = df["close"].rolling(SMA_FAST).mean()
    df["sma_slow"] = df["close"].rolling(SMA_SLOW).mean()

    trades = []
    signals = [] 
    position = None

    for i in range(SMA_SLOW + 1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]

        golden = (prev["sma_fast"] <= prev["sma_slow"]) and (curr["sma_fast"] > curr["sma_slow"])
        death = (prev["sma_fast"] >= prev["sma_slow"]) and (curr["sma_fast"] < curr["sma_slow"])

        if position is None:
            if golden:
                signals.append({"time": curr["open_time"], "price": curr["close"], "signal": "Golden Cross"})
                position = {"side": "BUY", "entry": curr["close"]}
            elif death:
                signals.append({"time": curr["open_time"], "price": curr["close"], "signal": "Death Cross"})
                position = {"side": "SELL", "entry": curr["close"]}
        else:
            entry = position["entry"]
            if position["side"] == "BUY":
                tp_level = entry + TICKS_TP * TICK_SIZE
                sl_level = entry - TICKS_SL * TICK_SIZE
                if curr["high"] >= tp_level:
                    trades.append(tp_level - entry)
                    signals.append({"time": curr["open_time"], "price": tp_level, "signal": "TP BUY"})
                    position = None
                elif curr["low"] <= sl_level:
                    trades.append(sl_level - entry)
                    signals.append({"time": curr["open_time"], "price": sl_level, "signal": "SL BUY"})
                    position = None
                elif death:
                    trades.append(curr["close"] - entry)
                    signals.append({"time": curr["open_time"], "price": curr["close"], "signal": "Exit BUY (Death Cross)"})
                    position = {"side": "SELL", "entry": curr["close"]}
            else: 
                tp_level = entry - TICKS_TP * TICK_SIZE
                sl_level = entry + TICKS_SL * TICK_SIZE
                if curr["low"] <= tp_level:
                    trades.append(entry - tp_level)
                    signals.append({"time": curr["open_time"], "price": tp_level, "signal": "TP SELL"})
                    position = None
                elif curr["high"] >= sl_level:
                    trades.append(entry - sl_level)
                    signals.append({"time": curr["open_time"], "price": sl_level, "signal": "SL SELL"})
                    position = None
                elif golden:
                    trades.append(entry - curr["close"])
                    signals.append({"time": curr["open_time"], "price": curr["close"], "signal": "Exit SELL (Golden Cross)"})
                    position = {"side": "BUY", "entry": curr["close"]}

    total_profit = sum(trades)
    win_rate = sum(1 for t in trades if t > 0) / len(trades) if trades else 0

    return trades, df, total_profit, win_rate, signals

st.title("Backtest BTCUSDT - SMA Crossover - Timeframe H1 data 2022-2025")

st.markdown(
    """
    ### Penjelasan Strategi SMA Crossover
    - **SMA Fast**: rata-rata harga jangka pendek, lebih sensitif terhadap perubahan harga.
    - **SMA Slow**: rata-rata harga jangka panjang, lebih halus dan menunjukkan tren utama.
    - **Golden Cross**: SMA Fast menembus ke atas SMA Slow → sinyal bullish (BUY).
    - **Death Cross**: SMA Fast menembus ke bawah SMA Slow → sinyal bearish (SELL).

    Strategi ini efektif untuk menangkap tren besar, tetapi bisa menghasilkan sinyal palsu saat pasar sideways.
    """
)


with st.form("backtest_form"):
    SMA_FAST = st.slider("SMA Fast", 1, 100, 50)
    SMA_SLOW = st.slider("SMA Slow", 1, 200, 100)
    TICKS_TP = st.number_input("Take Profit (ticks)", value=50000)
    TICKS_SL = st.number_input("Stop Loss (ticks)", value=30000)
    TICK_SIZE = st.number_input("Tick Size", value=0.1)

    run_button = st.form_submit_button("Run Backtest")

if run_button:
    trades, df, total_profit, win_rate, signals = run_backtest(SMA_FAST, SMA_SLOW, TICKS_TP, TICKS_SL, TICK_SIZE)

    st.write("Jumlah trade:", len(trades))
    st.write("Total Profit:", round(total_profit, 2))
    st.write("Win Rate:", round(win_rate * 100, 2), "%")

    st.write("### Log Sinyal Trading")
    signals_df = pd.DataFrame(signals)
    st.dataframe(signals_df)

    equity = np.cumsum(trades)
    mean_return = np.mean(trades)
    std_return = np.std(trades)
    sharpe_ratio = mean_return / std_return if std_return != 0 else 0

    tab1, tab2, tab3, tab4 = st.tabs(["Equity Curve", "Histogram Profit", "Win/Loss Streak", "Drawdown Curve"])

    with tab1:
        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(equity, label=f"Equity Curve (Total: {total_profit:.2f})", color="blue")
        ax.scatter(np.argmax(equity), np.max(equity), color="red", label="Peak Equity")
        ax.set_title("Equity Curve")
        ax.legend()
        st.pyplot(fig)

    with tab2:
        fig, ax = plt.subplots(figsize=(6,4))
        ax.hist(trades, bins=30, color="green", edgecolor="black")
        ax.axvline(np.mean(trades), color='red', linestyle='dashed', linewidth=1, label=f"Mean: {np.mean(trades):.2f}")
        ax.axvline(0, color='black', linestyle='dotted', linewidth=1)
        ax.set_title("Distribusi Profit per Trade")
        ax.legend()
        st.pyplot(fig)

    with tab3:
        streaks = []
        streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        for t in trades:
            if t > 0:
                streak = streak + 1 if streak >= 0 else 1
            else:
                streak = streak - 1 if streak <= 0 else -1
            streaks.append(streak)
            max_win_streak = max(max_win_streak, streak if streak > 0 else 0)
            max_loss_streak = min(max_loss_streak, streak if streak < 0 else 0)

        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(streaks, label=f"Win/Loss Streak (Max Win: {max_win_streak}, Max Loss: {abs(max_loss_streak)})", color="purple")
        ax.set_title("Win/Loss Streak")
        ax.legend()
        st.pyplot(fig)

    with tab4:
        peak = np.maximum.accumulate(equity)
        drawdown = equity - peak
        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(drawdown, color='red', label='Drawdown')
        ax.set_title("Drawdown Curve")
        ax.legend()
        st.pyplot(fig)

    st.markdown(
        f"""
        ---
        ### Kesimpulan Analisa
        - Total Profit: **{round(total_profit,2)}**
        - Win Rate: **{round(win_rate*100,2)}%**
        - Sharpe Ratio: **{sharpe_ratio:.2f}**

        Interpretasi:
        - Strategi SMA crossover cocok untuk tren panjang (bull run BTC).
        - Kelemahan: di kondisi sideways muncul banyak sinyal palsu.
        - Dengan RR sekitar {round(TICKS_TP/TICKS_SL,2)}, strategi ini cukup sehat karena TP lebih besar dari SL.
        """
    )
