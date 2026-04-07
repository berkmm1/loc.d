import ccxt
import pandas as pd
import time
import os
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from utils import calculate_indicators, setup_logger, get_timestamp
from datetime import datetime

load_dotenv()

class BingXBot:
    """
    Enhanced BingX Trading Bot with Database Persistence and Robust Error Handling.
    """
    def __init__(self, api_key=None, api_secret=None, sandbox=True, db_url=None):
        self.api_key = api_key or os.getenv('BINGX_API_KEY')
        self.api_secret = api_secret or os.getenv('BINGX_API_SECRET')
        self.sandbox = sandbox
        self.db_url = db_url or os.getenv('DATABASE_URL')

        # Strategy Parameters
        self.leverage = 10
        self.risk_percent = 1.0
        self.rsi_period = 14
        self.ema_period = 50
        self.timeframe = '1h'
        self.sl_percent = 30.0 # Position-based

        self.symbol = 'BTC/USDT:USDT'
        self.is_running = False
        self.logger = setup_logger('trading_bot', 'bot.log')

        # Internal State
        self.df = pd.DataFrame()
        self.current_price = 0.0
        self.price_change_24h = 0.0
        self.balance = 0.0
        self.positions = []
        self.trade_history = []
        self.last_signal_time = None

        # Initialize Exchange
        self.exchange = None
        self._init_exchange()
        self._check_db_tables()

    def _init_exchange(self):
        try:
            exchange_options = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,
                'options': { 'defaultType': 'swap' }
            }
            self.exchange = ccxt.bingx(exchange_options)
            if self.sandbox:
                self.exchange.set_sandbox_mode(True)
            self.update_balance()
            self.logger.info(f"Exchange initialized. Sandbox: {self.sandbox}")
        except Exception as e:
            self.logger.error(f"Exchange initialization failed: {e}")

    def _get_db_conn(self):
        if not self.db_url: return None
        try:
            # Add connect_timeout to avoid hanging
            return psycopg2.connect(self.db_url, connect_timeout=5)
        except Exception as e:
            self.logger.error(f"DB connection failed: {e}")
            return None

    def save_trade(self, trade_type, price, amount, pnl=0, status='OPEN'):
        conn = self._get_db_conn()
        if not conn: return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO trades (symbol, type, price, amount, pnl, status) VALUES (%s, %s, %s, %s, %s, %s)",
                    (self.symbol, trade_type, price, amount, pnl, status)
                )
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error saving trade to DB: {e}")
        finally:
            conn.close()

    def save_balance(self):
        conn = self._get_db_conn()
        if not conn: return
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO balance_history (balance) VALUES (%s)", (self.balance,))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error saving balance to DB: {e}")
        finally:
            conn.close()

    def get_trade_history(self, limit=50):
        conn = self._get_db_conn()
        if not conn: return self.trade_history
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT time, type, price, amount, status, pnl FROM trades ORDER BY time DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
                for row in rows:
                    if isinstance(row['time'], datetime):
                        row['time'] = row['time'].strftime("%Y-%m-%d %H:%M:%S")
                return rows
        except Exception as e:
            self.logger.error(f"Error fetching history: {e}")
            return self.trade_history
        finally:
            conn.close()

    def update_balance(self):
        try:
            if not self.exchange: return 0.0
            balance_info = self.exchange.fetch_balance()
            self.balance = balance_info['total'].get('USDT', 0.0)
            return self.balance
        except Exception as e:
            self.logger.error(f"Error fetching balance: {e}")
            return 0.0

    def update_market_data(self):
        try:
            if not self.exchange: return False
            ticker = self.exchange.fetch_ticker(self.symbol)
            self.current_price = ticker['last']
            self.price_change_24h = ticker['percentage']

            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            self.df = calculate_indicators(df, self.rsi_period, self.ema_period)
            return True
        except Exception as e:
            self.logger.error(f"Error updating market data: {e}")
            return False

    def update_positions(self):
        try:
            if not self.exchange: return []
            raw_positions = self.exchange.fetch_positions([self.symbol])
            self.positions = [p for p in raw_positions if float(p.get('contracts', 0)) > 0]

            # Management loop
            for pos in self.positions:
                self._manage_position(pos)
            return self.positions
        except Exception as e:
            self.logger.error(f"Error updating positions: {e}")
            return []

    def _manage_position(self, pos):
        side = pos['side'].lower()
        entry_price = float(pos['entryPrice'])
        curr_price = self.current_price
        if entry_price == 0: return

        # Leveraged PNL calculation
        if side == 'long':
            pnl_pct = (curr_price - entry_price) / entry_price * self.leverage * 100
        else:
            pnl_pct = (entry_price - curr_price) / entry_price * self.leverage * 100

        # SL Check
        if pnl_pct <= -self.sl_percent:
            self.logger.warning(f"AUTO-SL: Closing {side} at {pnl_pct:.2f}%")
            self.close_position(side, pnl_pct)
            return

        # TP Check
        if not self.df.empty:
            last_rsi = self.df.iloc[-1]['RSI']
            # Exit signals: Long if RSI > 70, Short if RSI < 30
            if (side == 'long' and (last_rsi > 70 or pnl_pct >= self.sl_percent * 2)) or                (side == 'short' and (last_rsi < 30 or pnl_pct >= self.sl_percent * 2)):
                self.logger.info(f"AUTO-TP: Closing {side} at {pnl_pct:.2f}% (RSI: {last_rsi:.2f})")
                self.close_position(side, pnl_pct)

    def open_position(self, side):
        try:
            if not self.exchange: return False
            self.exchange.set_leverage(self.leverage, self.symbol)

            amount = (self.balance * (self.risk_percent / 100)) / self.current_price * self.leverage
            amount = float(self.exchange.amount_to_precision(self.symbol, amount))

            order = self.exchange.create_market_order(self.symbol, side, amount)
            trade_type = 'LONG' if side == 'buy' else 'SHORT'
            self.logger.info(f"Opened {trade_type} position: {amount}")

            self.save_trade(trade_type, self.current_price, amount, 0, 'OPEN')
            return True
        except Exception as e:
            self.logger.error(f"Failed to open position: {e}")
            return False

    def close_position(self, side=None, pnl=0):
        try:
            if not self.exchange: return False
            # Ensure we have fresh position data
            raw_positions = self.exchange.fetch_positions([self.symbol])
            active_positions = [p for p in raw_positions if float(p.get('contracts', 0)) > 0]

            if side:
                side_map = {'buy': 'long', 'sell': 'short', 'long': 'long', 'short': 'short'}
                target_side = side_map.get(side.lower(), side.lower())
                target_positions = [p for p in active_positions if p['side'].lower() == target_side]
            else:
                target_positions = active_positions

            if not target_positions: return False

            for pos in target_positions:
                close_side = 'sell' if pos['side'] == 'long' else 'buy'
                amount = float(pos['contracts'])
                self.exchange.create_market_order(self.symbol, close_side, amount, params={'reduceOnly': True})
                self.logger.info(f"Closed {pos['side'].upper()} position of {amount}")
                self.save_trade(f"CLOSE {pos['side'].upper()}", self.current_price, amount, pnl, 'CLOSED')

            self.update_balance()
            self.save_balance()
            return True
        except Exception as e:
            self.logger.error(f"Error during position closure: {e}")
            return False

    def bot_cycle(self):
        if not self.update_market_data(): return
        self.update_positions()
        self.update_balance()

        if self.is_running and not self.df.empty:
            last_timestamp = self.df.iloc[-1]['timestamp']

            # Use timestamp to avoid multiple entries on same candle
            if self.last_signal_time != last_timestamp:
                signal = self._check_signals()
                if signal:
                    self.logger.info(f"Signal detected: {signal} at {last_timestamp}")
                    if self.open_position('buy' if signal == 'LONG' else 'sell'):
                        self.last_signal_time = last_timestamp

    def _check_signals(self):
        if self.df.empty: return None
        last_row = self.df.iloc[-1]

        # Strategy:
        # LONG: RSI < 35 & Price > EMA 50
        # SHORT: RSI > 65 & Price < EMA 50
        if last_row['RSI'] < 35 and last_row['close'] > last_row['EMA']:
            return 'LONG'
        elif last_row['RSI'] > 65 and last_row['close'] < last_row['EMA']:
            return 'SHORT'
        return None

    def start(self):
        self.is_running = True
        self.logger.info("Bot Engine Started")

    def stop(self):
        self.is_running = False
        self.logger.info("Bot Engine Stopped")


    def _check_db_tables(self):
        conn = self._get_db_conn()
        if not conn: return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM trades LIMIT 1")
                cur.execute("SELECT 1 FROM balance_history LIMIT 1")
                self.logger.info("Database tables verified.")
        except Exception as e:
            self.logger.error(f"Database table verification failed: {e}")
            # Try to create them if they don't exist
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS trades (
                            id SERIAL PRIMARY KEY,
                            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            symbol VARCHAR(20),
                            type VARCHAR(20),
                            price DECIMAL(20, 2),
                            amount DECIMAL(20, 8),
                            pnl DECIMAL(20, 4) DEFAULT 0,
                            status VARCHAR(20)
                        );
                        CREATE TABLE IF NOT EXISTS balance_history (
                            id SERIAL PRIMARY KEY,
                            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            balance DECIMAL(20, 2)
                        );
                    """)
                    conn.commit()
                    self.logger.info("Database tables created.")
            except Exception as e2:
                self.logger.error(f"Failed to create tables: {e2}")
        finally:
            conn.close()
