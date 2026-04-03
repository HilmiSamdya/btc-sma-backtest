import streamlit as st
import pandas as pd
import numpy as np
import glob
import os
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# ============ PAGE CONFIG ============
st.set_page_config(
    page_title="BTC Backtest Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Set dark theme
plt.style.use('dark_background')

# ============ BACKTEST LOGIC ============
def run_backtest(SMA_FAST, SMA_SLOW, TICKS_TP, TICKS_SL, TICK_SIZE):
    """Run SMA crossover backtest on BTC data"""
    
    files = sorted(
        glob.glob("data/btcusdt2024h1/BTCUSDT-1h-2024-*.csv")
        + glob.glob("data/btcusdt2025h1/BTCUSDT-1h-2025-*.csv")
        + glob.glob("data/btcusdt2023h1/BTCUSDT-1h-2023-*.csv")
        + glob.glob("data/btcusdt2022h1/BTCUSDT-1h-2022-*.csv")
    )
    
    if not files:
        return None, "Tidak ada file CSV ditemukan di folder data/"
    
    dfs = []
    for f in files:
        try:
            df_temp = pd.read_csv(f)
            df_temp["close"] = df_temp["close"].astype(float)
            df_temp["high"] = df_temp["high"].astype(float)
            df_temp["low"] = df_temp["low"].astype(float)
            df_temp["open_time"] = pd.to_datetime(
                df_temp["open_time"], unit="ms", utc=True
            ).dt.tz_convert("Asia/Jakarta")
            dfs.append(df_temp)
        except Exception as e:
            st.warning(f"Error reading {f}: {str(e)}")
            continue
    
    if not dfs:
        return None, "Gagal membaca file CSV"
    
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
        
        ts = str(curr["open_time"])[:16]
        
        if position is None:
            if golden:
                signals.append({
                    "time": ts, 
                    "price": round(curr["close"], 2), 
                    "signal": "Golden Cross", 
                    "type": "golden"
                })
                position = {"side": "BUY", "entry": curr["close"]}
            elif death:
                signals.append({
                    "time": ts, 
                    "price": round(curr["close"], 2), 
                    "signal": "Death Cross", 
                    "type": "death"
                })
                position = {"side": "SELL", "entry": curr["close"]}
        else:
            entry = position["entry"]
            if position["side"] == "BUY":
                tp_level = entry + TICKS_TP * TICK_SIZE
                sl_level = entry - TICKS_SL * TICK_SIZE
                if curr["high"] >= tp_level:
                    trades.append(tp_level - entry)
                    signals.append({
                        "time": ts, 
                        "price": round(tp_level, 2), 
                        "signal": "TP BUY ✓", 
                        "type": "tp"
                    })
                    position = None
                elif curr["low"] <= sl_level:
                    trades.append(sl_level - entry)
                    signals.append({
                        "time": ts, 
                        "price": round(sl_level, 2), 
                        "signal": "SL BUY ✗", 
                        "type": "sl"
                    })
                    position = None
                elif death:
                    trades.append(curr["close"] - entry)
                    signals.append({
                        "time": ts, 
                        "price": round(curr["close"], 2), 
                        "signal": "Exit BUY (Death)", 
                        "type": "exit"
                    })
                    position = {"side": "SELL", "entry": curr["close"]}
            else:
                tp_level = entry - TICKS_TP * TICK_SIZE
                sl_level = entry + TICKS_SL * TICK_SIZE
                if curr["low"] <= tp_level:
                    trades.append(entry - tp_level)
                    signals.append({
                        "time": ts, 
                        "price": round(tp_level, 2), 
                        "signal": "TP SELL ✓", 
                        "type": "tp"
                    })
                    position = None
                elif curr["high"] >= sl_level:
                    trades.append(entry - sl_level)
                    signals.append({
                        "time": ts, 
                        "price": round(sl_level, 2), 
                        "signal": "SL SELL ✗", 
                        "type": "sl"
                    })
                    position = None
                elif golden:
                    trades.append(entry - curr["close"])
                    signals.append({
                        "time": ts, 
                        "price": round(curr["close"], 2), 
                        "signal": "Exit SELL (Golden)", 
                        "type": "exit"
                    })
                    position = {"side": "BUY", "entry": curr["close"]}
    
    if not trades:
        return None, "Tidak ada trade yang dihasilkan. Coba ubah parameter."
    
    total_profit = sum(trades)
    win_rate = sum(1 for t in trades if t > 0) / len(trades)
    equity = list(np.cumsum(trades))
    mean_r = float(np.mean(trades))
    std_r = float(np.std(trades))
    sharpe = round(mean_r / std_r, 4) if std_r != 0 else 0
    
    peak = list(np.maximum.accumulate(equity))
    drawdown = [e - p for e, p in zip(equity, peak)]
    
    streaks = []
    s = 0
    max_win = 0
    max_loss = 0
    for t in trades:
        if t > 0:
            s = s + 1 if s >= 0 else 1
        else:
            s = s - 1 if s <= 0 else -1
        streaks.append(s)
        max_win = max(max_win, s if s > 0 else 0)
        max_loss = min(max_loss, s if s < 0 else 0)
    
    return {
        "total_trades": len(trades),
        "total_profit": round(total_profit, 2),
        "win_rate": round(win_rate * 100, 2),
        "sharpe": sharpe,
        "max_win_streak": max_win,
        "max_loss_streak": abs(max_loss),
        "equity": equity,
        "drawdown": drawdown,
        "streaks": streaks,
        "trades": trades,
        "signals": signals[-500:],
    }, None

# ============ PLOTTING FUNCTIONS ============
def plot_equity(equity):
    fig, ax = plt.subplots(figsize=(12, 4))
    peak = list(np.maximum.accumulate(equity))
    ax.plot(equity, label='Equity', color='#00e5a0', linewidth=2)
    ax.plot(peak, label='Peak', color='#f5a623', linewidth=1, linestyle='--', alpha=0.7)
    ax.fill_between(range(len(equity)), equity, alpha=0.1, color='#00e5a0')
    ax.set_title('Equity Curve', fontsize=14, fontweight='bold', color='#00e5a0')
    ax.set_xlabel('Trade #')
    ax.set_ylabel('Cumulative P&L')
    ax.legend(loc='best', facecolor='#0a1520', edgecolor='#0f2535')
    ax.grid(True, alpha=0.2)
    return fig

def plot_histogram(trades):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.hist(trades, bins=25, color='#00e5a0', edgecolor='#0f2535', alpha=0.7)
    ax.set_title('Trade Distribution', fontsize=14, fontweight='bold', color='#00e5a0')
    ax.set_xlabel('P&L')
    ax.set_ylabel('Frequency')
    ax.grid(True, alpha=0.2, axis='y')
    return fig

def plot_streak(streaks, max_win, max_loss):
    fig, ax = plt.subplots(figsize=(12, 4))
    colors = ['#00e5a0' if s > 0 else '#ff4757' for s in streaks]
    ax.bar(range(len(streaks)), streaks, color=colors, edgecolor='#0f2535', alpha=0.8)
    ax.set_title(f'Win/Loss Streak (Max Win: {max_win} / Max Loss: {max_loss})', 
                 fontsize=14, fontweight='bold', color='#00e5a0')
    ax.set_xlabel('Trade #')
    ax.set_ylabel('Streak')
    ax.grid(True, alpha=0.2, axis='y')
    ax.axhline(y=0, color='#f5a623', linewidth=0.8)
    return fig

def plot_drawdown(drawdown):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(drawdown, label='Drawdown', color='#ff4757', linewidth=2)
    ax.fill_between(range(len(drawdown)), drawdown, alpha=0.1, color='#ff4757')
    ax.set_title('Drawdown Curve', fontsize=14, fontweight='bold', color='#ff4757')
    ax.set_xlabel('Trade #')
    ax.set_ylabel('Drawdown')
    ax.grid(True, alpha=0.2)
    return fig

# ============ STREAMLIT APP ============
def main():
    # Create directories
    os.makedirs("data", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # Header
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        st.markdown("## 📈 BTC BACKTEST TERMINAL")
        st.caption("BTC/USDT · H1 · 2022–2025 | SMA Crossover Strategy")
    
    with col2:
        st.metric("Status", "🟢 Ready")
    
    # ============ SIDEBAR ============
    with st.sidebar:
        st.header("⚙️ Parameter Strategi")
        
        sma_fast = st.slider("SMA Fast", min_value=5, max_value=100, value=50, step=1)
        sma_slow = st.slider("SMA Slow", min_value=20, max_value=200, value=100, step=1)
        ticks_tp = st.number_input("Take Profit (ticks)", min_value=1000.0, max_value=200000.0, value=50000.0, step=1000.0)
        ticks_sl = st.number_input("Stop Loss (ticks)", min_value=1000.0, max_value=200000.0, value=30000.0, step=1000.0)
        tick_size = st.number_input("Tick Size", min_value=0.01, max_value=1.0, value=0.1, step=0.01)
        
        if ticks_sl > 0:
            rr_ratio = ticks_tp / ticks_sl
            st.metric("R/R Ratio", f"{rr_ratio:.2f}")
        
        run_button = st.button("▶ RUN BACKTEST", use_container_width=True, type="primary")
        
        st.divider()
        st.markdown("""
        ### 📋 Info Server
        - **Framework:** Streamlit
        - **Lokasi Data:** Folder `data/`
        - **Format:** `BTCUSDT-1h-YYYY-MM.csv`
        - **●** Golden Cross → BUY
        - **●** Death Cross → SELL
        """)
    
    # ============ MAIN ============
    if run_button:
        with st.spinner("⏳ Menjalankan backtest..."):
            result, error = run_backtest(sma_fast, sma_slow, ticks_tp, ticks_sl, tick_size)
        
        if error:
            st.error(f"❌ {error}")
        else:
            st.success(f"✅ Backtest berhasil - {result['total_trades']} trades")
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Trades", result["total_trades"])
            with col2:
                profit_color = "🟢" if result["total_profit"] >= 0 else "🔴"
                st.metric("Total Profit", f"{profit_color} {result['total_profit']:.2f}")
            with col3:
                wr_color = "🟢" if result["win_rate"] >= 50 else "🔴"
                st.metric("Win Rate", f"{wr_color} {result['win_rate']:.1f}%")
            with col4:
                sharpe_color = "🟢" if result["sharpe"] >= 0 else "🔴"
                st.metric("Sharpe Ratio", f"{sharpe_color} {result['sharpe']:.2f}")
            
            st.divider()
            
            # Tabs
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Equity", "📊 Distribusi", "🔥 Streak", "📉 Drawdown", "📋 Signals"])
            
            with tab1:
                st.pyplot(plot_equity(result["equity"]))
            
            with tab2:
                st.pyplot(plot_histogram(result["trades"]))
            
            with tab3:
                st.pyplot(plot_streak(result["streaks"], result["max_win_streak"], result["max_loss_streak"]))
            
            with tab4:
                st.pyplot(plot_drawdown(result["drawdown"]))
            
            with tab5:
                signals_df = pd.DataFrame(result["signals"])
                st.dataframe(signals_df, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
