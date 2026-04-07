import pandas as pd
import numpy as np
from utils import calculate_indicators

def run_backtest(df, rsi_period=14, ema_period=50, leverage=10, risk_percent=1.0, sl_percent=30.0):
    """
    Simulates trading strategy on historical dataframe.
    """
    if df is None or df.empty:
        return {'initial_balance': 0, 'final_balance': 0, 'total_pnl': 0, 'win_rate': 0, 'total_trades': 0, 'trades': []}

    df = calculate_indicators(df, rsi_period, ema_period)

    balance = 1000.0 # Starting virtual balance
    initial_balance = balance
    position = None # None, 'LONG', 'SHORT'
    entry_price = 0
    trades = []

    # Extract only necessary columns to speed up
    data = df[['timestamp', 'close', 'RSI', 'EMA']].dropna()

    for _, row in data.iterrows():
        price = row['close']
        rsi = row['RSI']
        ema = row['EMA']

        # 1. Exit Logic for open positions
        if position == 'LONG':
            # SL is 30% of position (including leverage)
            # Price drop % = SL% / Leverage
            sl_price = entry_price * (1 - (sl_percent / 100) / leverage)
            # TP is 1:2 RR or RSI > 70
            tp_price = entry_price * (1 + (sl_percent * 2 / 100) / leverage)

            if price <= sl_price or price >= tp_price or rsi > 70:
                pnl_ratio = (price - entry_price) / entry_price * leverage
                # Change in balance = balance * risk_pct * pnl_ratio
                trade_pnl = balance * (risk_percent / 100) * pnl_ratio
                balance += trade_pnl
                trades.append({
                    'side': 'LONG',
                    'entry': entry_price,
                    'exit': price,
                    'pnl': trade_pnl,
                    'pnl_pct': pnl_ratio * 100,
                    'timestamp': row['timestamp']
                })
                position = None

        elif position == 'SHORT':
            sl_price = entry_price * (1 + (sl_percent / 100) / leverage)
            tp_price = entry_price * (1 - (sl_percent * 2 / 100) / leverage)

            if price >= sl_price or price <= tp_price or rsi < 30:
                pnl_ratio = (entry_price - price) / entry_price * leverage
                trade_pnl = balance * (risk_percent / 100) * pnl_ratio
                balance += trade_pnl
                trades.append({
                    'side': 'SHORT',
                    'entry': entry_price,
                    'exit': price,
                    'pnl': trade_pnl,
                    'pnl_pct': pnl_ratio * 100,
                    'timestamp': row['timestamp']
                })
                position = None

        # 2. Entry Logic
        if position is None:
            # LONG: RSI < 35 & Price > EMA 50
            if rsi < 35 and price > ema:
                position = 'LONG'
                entry_price = price
            # SHORT: RSI > 65 & Price < EMA 50
            elif rsi > 65 and price < ema:
                position = 'SHORT'
                entry_price = price

    total_pnl = balance - initial_balance
    win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades) if trades else 0

    return {
        'initial_balance': initial_balance,
        'final_balance': balance,
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'total_trades': len(trades),
        'trades': trades
    }
