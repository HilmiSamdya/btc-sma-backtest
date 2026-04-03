import streamlit as st
import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px

# ============ PAGE CONFIG ============
st.set_page_config(
    page_title="BTC Backtest Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ CUSTOM STYLING ============
st.markdown("""
<style>
    /* Terminal-like styling */
    :root {
        --bg: #050a0e;
        --panel: #0a1520;
        --border: #0f2535;
        --accent: #00e5a0;
        --accent2: #f5a623;
        --red: #ff4757;
        --text: #cde8f0;
        --muted: #3a6070;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #0a1520 0%, #0f2535 100%);
        border: 1px solid #0f2535;
        border-radius: 8px;
        padding: 20px;
        margin: 10px 0;
    }
    
    .positive { color: #00e5a0; font-weight: bold; }
    .negative { color: #ff4757; font-weight: bold; }
    .neutral { color: #f5a623; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ============ BACKTEST LOGIC ============
def run_backtest(SMA_FAST, SMA_SLOW, TICKS_TP, TICKS_SL, TICK_SIZE):
    """Run SMA crossover backtest on BTC data"""
    
    # Find CSV files
    files = sorted(
        glob.glob("data/btcusdt2024h1/BTCUSDT-1h-2024-*.csv")
        + glob.glob("data/btcusdt2025h1/BTCUSDT-1h-2025-*.csv")
        + glob.glob("data/btcusdt2023h1/BTCUSDT-1h-2023-*.csv")
        + glob.glob("data/btcusdt2022h1/BTCUSDT-1h-2022-*.csv")
    )
    
    if not files:
        return None, "Tidak ada file CSV ditemukan di folder data/"
    
    # Load and combine data
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
    
    # Calculate SMAs
    df["sma_fast"] = df["close"].rolling(SMA_FAST).mean()
    df["sma_slow"] = df["close"].rolling(SMA_SLOW).mean()
    
    # Backtest logic
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
    
    # Calculate metrics
    total_profit = sum(trades)
    win_rate = sum(1 for t in trades if t > 0) / len(trades)
    equity = list(np.cumsum(trades))
    mean_r = float(np.mean(trades))
    std_r = float(np.std(trades))
    sharpe = round(mean_r / std_r, 4) if std_r != 0 else 0
    
    # Drawdown calculation
    peak = list(np.maximum.accumulate(equity))
    drawdown = [e - p for e, p in zip(equity, peak)]
    
    # Win/Loss streak
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


# ============ STREAMLIT APP ============
def main():
    # Header
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        st.markdown("## 📈 BTC BACKTEST TERMINAL")
        st.caption("BTC/USDT · H1 · 2022–2025 | SMA Crossover Strategy")
    
    with col2:
        st.metric("Status", "🟢 Ready")
    
    # Create directories
    os.makedirs("data", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    
    # ============ SIDEBAR CONTROLS ============
    with st.sidebar:
        st.header("⚙️ Parameter Strategi")
        
        # SMA Fast
        sma_fast = st.slider(
            "SMA Fast",
            min_value=5,
            max_value=100,
            value=50,
            step=1,
            help="Fast moving average period"
        )
        
        # SMA Slow
        sma_slow = st.slider(
            "SMA Slow",
            min_value=20,
            max_value=200,
            value=100,
            step=1,
            help="Slow moving average period"
        )
        
        # Take Profit
        ticks_tp = st.number_input(
            "Take Profit (ticks)",
            min_value=1000.0,
            max_value=200000.0,
            value=50000.0,
            step=1000.0
        )
        
        # Stop Loss
        ticks_sl = st.number_input(
            "Stop Loss (ticks)",
            min_value=1000.0,
            max_value=200000.0,
            value=30000.0,
            step=1000.0
        )
        
        # Tick Size
        tick_size = st.number_input(
            "Tick Size",
            min_value=0.01,
            max_value=1.0,
            value=0.1,
            step=0.01
        )
        
        # Calculate R/R Ratio
        if ticks_sl > 0:
            rr_ratio = ticks_tp / ticks_sl
            st.metric("R/R Ratio", f"{rr_ratio:.2f}")
        
        # Run button
        if st.button("▶ RUN BACKTEST", use_container_width=True, type="primary"):
            st.session_state.run_backtest = True
        
        st.divider()
        
        # Info
        st.markdown("""
        ### 📋 Info Server
        - **Framework:** Streamlit
        - **Lokasi Data:** Folder `data/`
        - **Format:** `BTCUSDT-1h-YYYY-MM.csv`
        - **●** Golden Cross → BUY
        - **●** Death Cross → SELL
        """)
    
    # ============ MAIN CONTENT ============
    if "run_backtest" not in st.session_state:
        st.session_state.run_backtest = False
    
    if st.session_state.run_backtest:
        with st.spinner("⏳ Menjalankan backtest..."):
            result, error = run_backtest(sma_fast, sma_slow, ticks_tp, ticks_sl, tick_size)
        
        if error:
            st.error(f"❌ {error}")
        else:
            # Display Metrics
            st.success(f"✅ Backtest berhasil - {result['total_trades']} trades")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Total Trades",
                    result["total_trades"]
                )
            
            with col2:
                profit_color = "🟢" if result["total_profit"] >= 0 else "🔴"
                st.metric(
                    "Total Profit",
                    f"{profit_color} {result['total_profit']:.2f}",
                )
            
            with col3:
                wr_color = "🟢" if result["win_rate"] >= 50 else "🔴"
                st.metric(
                    "Win Rate",
                    f"{wr_color} {result['win_rate']:.1f}%"
                )
            
            with col4:
                sharpe_color = "🟢" if result["sharpe"] >= 0 else "🔴"
                st.metric(
                    "Sharpe Ratio",
                    f"{sharpe_color} {result['sharpe']:.2f}"
                )
            
            st.divider()
            
            # Tabs
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Equity", "📊 Distribusi", "🔥 Streak", "📉 Drawdown", "📋 Signals"])
            
            with tab1:
                # Equity Chart
                equity_data = result["equity"]
                peak_data = list(np.maximum.accumulate(equity_data))
                
                fig_equity = go.Figure()
                fig_equity.add_trace(go.Scatter(
                    y=equity_data,
                    mode='lines',
                    name='Equity',
                    line=dict(color='#00e5a0', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(0,229,160,0.1)'
                ))
                fig_equity.add_trace(go.Scatter(
                    y=peak_data,
                    mode='lines',
                    name='Peak',
                    line=dict(color='#f5a623', width=1, dash='dash')
                ))
                fig_equity.update_layout(
                    title="Equity Curve",
                    xaxis_title="Trade #",
                    yaxis_title="Cumulative P&L",
                    template="plotly_dark",
                    hovermode="x unified",
                    height=400
                )
                st.plotly_chart(fig_equity, use_container_width=True)
            
            with tab2:
                # Histogram of trades
                fig_hist = go.Figure()
                fig_hist.add_trace(go.Histogram(
                    x=result["trades"],
                    nbinsx=25,
                    name='Trade Distribution',
                    marker=dict(color='#00e5a0')
                ))
                fig_hist.update_layout(
                    title="Distribusi P&L per Trade",
                    xaxis_title="P&L",
                    yaxis_title="Frekuensi",
                    template="plotly_dark",
                    height=400
                )
                st.plotly_chart(fig_hist, use_container_width=True)
            
            with tab3:
                # Streak Chart
                fig_streak = go.Figure()
                colors = ['#00e5a0' if x > 0 else '#ff4757' for x in result["streaks"]]
                fig_streak.add_trace(go.Bar(
                    y=result["streaks"],
                    marker=dict(color=colors),
                    name='Streak'
                ))
                fig_streak.update_layout(
                    title=f"Win/Loss Streak (Max Win: {result['max_win_streak']} / Max Loss: {result['max_loss_streak']})",
                    xaxis_title="Trade #",
                    yaxis_title="Streak",
                    template="plotly_dark",
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig_streak, use_container_width=True)
            
            with tab4:
                # Drawdown Chart
                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(
                    y=result["drawdown"],
                    mode='lines',
                    name='Drawdown',
                    line=dict(color='#ff4757', width=2),
                    fill='tozeroy',
                    fillcolor='rgba(255,71,87,0.1)'
                ))
                fig_dd.update_layout(
                    title="Drawdown Curve",
                    xaxis_title="Trade #",
                    yaxis_title="Drawdown",
                    template="plotly_dark",
                    hovermode="x unified",
                    height=400
                )
                st.plotly_chart(fig_dd, use_container_width=True)
            
            with tab5:
                # Signal Table
                signals_df = pd.DataFrame(result["signals"])
                st.dataframe(
                    signals_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "time": st.column_config.TextColumn("Waktu"),
                        "price": st.column_config.NumberColumn("Harga", format="%.2f"),
                        "signal": st.column_config.TextColumn("Sinyal"),
                        "type": st.column_config.TextColumn("Tipe")
                    }
                )
        
        st.session_state.run_backtest = False

if __name__ == "__main__":
    main()
