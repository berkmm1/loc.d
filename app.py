import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import os
from bot import BingXBot
from backtest import run_backtest
from utils import get_timestamp, format_currency
from dotenv import load_dotenv

# Load .env for automatic API key filling
load_dotenv()

st.set_page_config(page_title="BingX BTC-USDT Trading Bot", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for dark theme and styling
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1f2937; padding: 15px; border-radius: 10px; }
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# Persistent state initialization
if 'bot' not in st.session_state:
    st.session_state.bot = None
if 'running' not in st.session_state:
    st.session_state.running = False

# Sidebar: Configurations
st.sidebar.title("🛠️ Bot Yapılandırması")

with st.sidebar.expander("🔑 API Anahtarları", expanded=True):
    default_key = os.getenv('BINGX_API_KEY', '')
    default_secret = os.getenv('BINGX_API_SECRET', '')

    api_key = st.text_input("BingX API Key", type="password", value=default_key)
    api_secret = st.text_input("BingX API Secret", type="password", value=default_secret)
    sandbox = st.checkbox("Sandbox (Demo) Modu", value=True)

with st.sidebar.expander("⚖️ Risk & Kaldıraç", expanded=True):
    leverage = st.slider("Kaldıraç (x)", 10, 50, 10)
    risk_pct = st.slider("İşlem Başına Risk (%)", 1.0, 5.0, 1.0)
    sl_percent = st.slider("Stop Loss (%)", 10, 50, 30, help="Pozisyon bazlı zarar kes")

with st.sidebar.expander("📈 Strateji Parametreleri", expanded=True):
    rsi_period = st.number_input("RSI Periyodu", 5, 30, 14)
    ema_period = st.number_input("EMA Periyodu", 10, 200, 50)
    timeframe = st.selectbox("Zaman Dilimi", ["1m", "5m", "15m", "1h", "4h", "1d"], index=3)

if st.sidebar.button("⚙️ Botu Güncelle / Uygula"):
    try:
        st.session_state.bot = BingXBot(api_key, api_secret, sandbox)
        st.session_state.bot.leverage = leverage
        st.session_state.bot.risk_percent = risk_pct
        st.session_state.bot.rsi_period = rsi_period
        st.session_state.bot.ema_period = ema_period
        st.session_state.bot.timeframe = timeframe
        st.session_state.bot.sl_percent = sl_percent
        st.sidebar.success("Ayarlar uygulandı!")
    except Exception as e:
        st.sidebar.error(f"Hata: {e}")

# Main Dashboard UI
st.title("🚀 BTC-USDT Perpetual Futures Bot")

if st.session_state.bot:
    bot = st.session_state.bot

    # 1. Update Market Data & Balance
    bot.bot_cycle()

    # 2. Header Metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("BTC-USDT Fiyat", format_currency(bot.current_price), f"{bot.price_change_24h:.2f}%")
    with col2:
        st.metric("Cüzdan Bakiyesi", f"${bot.balance:,.2f}")
    with col3:
        # Simple PNL calculation for display
        realized_pnl = sum(t.get('pnl', 0) for t in bot.trade_history if t.get('status') == 'CLOSED')
        st.metric("Session PNL", f"${realized_pnl:,.2f}", delta_color="normal")
    with col4:
        status_text = "🟢 ÇALIŞIYOR" if st.session_state.running else "🔴 DURDURULDU"
        st.metric("Bot Durumu", status_text)

    # 3. Live Chart with Plotly
    if not bot.df.empty:
        df = bot.df
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                           vertical_spacing=0.05,
                           subplot_titles=('Fiyat & EMA', 'RSI'),
                           row_heights=[0.7, 0.3])

        # Candlestick / Line Chart
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['close'], name='Fiyat', line=dict(color='#3b82f6', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['EMA'], name=f'EMA {ema_period}', line=dict(color='#f59e0b', width=1.5)), row=1, col=1)

        # RSI Chart
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['RSI'], name='RSI', line=dict(color='#10b981', width=1.5)), row=2, col=1)
        # RSI Threshold lines
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Aşırı Alım")
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Aşırı Satım")
        fig.add_hline(y=35, line_dash="dot", line_color="cyan", row=2, col=1)
        fig.add_hline(y=65, line_dash="dot", line_color="magenta", row=2, col=1)

        fig.update_layout(height=500, template='plotly_dark', margin=dict(l=20, r=20, t=40, b=20), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # 4. Positions & Controls
    pos_col, ctrl_col = st.columns([2, 1])

    with pos_col:
        st.subheader("💼 Mevcut Pozisyonlar")
        if bot.positions:
            for i, pos in enumerate(bot.positions):
                side = pos['side'].upper()
                pnl = pos.get('unrealizedPnl', '0.0')
                pnl_pct = pos.get('percentage', '0.0')
                color = "green" if float(pnl) >= 0 else "red"

                with st.container(border=True):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Sembol:** {pos['symbol']}")
                    c1.write(f"**Yön:** {side}")
                    c2.write(f"**Giriş:** ${float(pos['entryPrice']):,.2f}")
                    c2.write(f"**Miktar:** {pos['contracts']}")
                    c3.markdown(f"**PNL:** :{color}[{pnl} USDT ({pnl_pct}%)]")
        else:
            st.info("Açık pozisyon bulunmuyor.")

    with ctrl_col:
        st.subheader("🎮 Kontrol Paneli")

        # Start/Stop Button
        if not st.session_state.running:
            if st.button("▶️ Botu Başlat", type="primary"):
                st.session_state.running = True
                bot.start()
                st.rerun()
        else:
            if st.button("⏹️ Botu Durdur"):
                st.session_state.running = False
                bot.stop()
                st.rerun()

        st.divider()

        # Manual Trade Buttons
        m_col1, m_col2 = st.columns(2)
        if m_col1.button("🟢 Manuel LONG"):
            if bot.open_position('buy'): st.toast("Long pozisyon açıldı!")
        if m_col2.button("🔴 Manuel SHORT"):
            if bot.open_position('sell'): st.toast("Short pozisyon açıldı!")

        if st.button("❌ Tüm Pozisyonları Kapat", use_container_width=True):
            if bot.close_position(): st.toast("Tüm pozisyonlar kapatıldı.")

        st.divider()

        # Backtest Trigger
        if st.button("📊 Backtest Çalıştır", use_container_width=True):
            with st.spinner("Geçmiş veriler analiz ediliyor..."):
                results = run_backtest(bot.df, rsi_period, ema_period, leverage, risk_pct, sl_percent)
                st.write("#### Backtest Özeti")
                st.success(f"Bakiye: ${results['final_balance']:,.2f}")
                st.info(f"Win Rate: %{results['win_rate']*100:.1f}")
                st.info(f"Toplam İşlem: {results['total_trades']}")

    # 5. Trade Logs
    st.subheader("📜 İşlem Logu (Son 20)")
    if bot.trade_history:
        log_df = pd.DataFrame(bot.trade_history).tail(20)
        st.dataframe(log_df.iloc[::-1], use_container_width=True)
    else:
        st.caption("Henüz bir işlem gerçekleşmedi.")

    # Auto-refresh loop
    if st.session_state.running:
        time.sleep(5)
        st.rerun()

else:
    st.warning("⚠️ Lütfen sol menüden API anahtarlarınızı girin ve 'Botu Yapılandır' butonuna tıklayın.")
    st.image("https://streamlit.io/images/brand/streamlit-logo-secondary-colormark-darktext.png", width=200)
