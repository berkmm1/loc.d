import ccxt
import pandas as pd
import time
import os
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from utils import calculate_indicators, setup_logger, get_timestamp

load_dotenv()

class BingXBot:
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
        self.sl_percent = 30.0

        self.symbol = 'BTC/USDT:USDT'
        self.is_running = False
        self.logger = setup_logger('trading_bot', 'bot.log')

        # State
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
            self.logger.info("Exchange connection established.")
        except Exception as e:
            self.logger.error(f"Exchange initialization failed: {e}")

    def _get_db_conn(self):
        if not self.db_url: return None
        try:
            return psycopg2.connect(self.db_url)
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
                # Format time for frontend
                for row in rows:
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
            # Log periodically or on change
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
            for pos in self.positions: self._manage_position(pos)
            return self.positions
        except Exception as e:
            self.logger.error(f"Error updating positions: {e}")
            return []

    def _manage_position(self, pos):
        side = pos['side'].lower()
        entry_price = float(pos['entryPrice'])
        curr_price = self.current_price
        if entry_price == 0: return
        if side == 'long': pnl_pct = (curr_price - entry_price) / entry_price * self.leverage * 100
        else: pnl_pct = (entry_price - curr_price) / entry_price * self.leverage * 100
        if pnl_pct <= -self.sl_percent:
            self.logger.warning(f"SL triggered for {side}")
            self.close_position(side, pnl_pct)
        last_rsi = self.df.iloc[-1]['RSI'] if not self.df.empty else 50
        if (side == 'long' and (last_rsi > 70 or pnl_pct >= self.sl_percent * 2)) or            (side == 'short' and (last_rsi < 30 or pnl_pct >= self.sl_percent * 2)):
            self.logger.info(f"TP triggered for {side}")
            self.close_position(side, pnl_pct)

    def open_position(self, side):
        try:
            if not self.exchange: return False
            self.exchange.set_leverage(self.leverage, self.symbol)
            amount = (self.balance * (self.risk_percent / 100)) / self.current_price * self.leverage
            amount = float(self.exchange.amount_to_precision(self.symbol, amount))
            order = self.exchange.create_market_order(self.symbol, side, amount)
            trade_type = 'LONG' if side == 'buy' else 'SHORT'
            self.save_trade(trade_type, self.current_price, amount, 0, 'OPEN')
            return True
        except Exception as e:
            self.logger.error(f"Failed to open position: {e}")
            return False

    def close_position(self, side=None, pnl=0):
        try:
            if not self.exchange: return False
            self.update_positions()
            target_positions = self.positions
            if side:
                side_map = {'buy': 'long', 'sell': 'short', 'long': 'long', 'short': 'short'}
                target_side = side_map.get(side.lower(), side.lower())
                target_positions = [p for p in self.positions if p['side'].lower() == target_side]
            if not target_positions: return False
            for pos in target_positions:
                close_side = 'sell' if pos['side'] == 'long' else 'buy'
                amount = float(pos['contracts'])
                self.exchange.create_market_order(self.symbol, close_side, amount, params={'reduceOnly': True})
                # Calculate real PNL if possible
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
            if self.last_signal_time != last_timestamp:
                signal = self._check_signals()
                if signal:
                    if self.open_position('buy' if signal == 'LONG' else 'sell'):
                        self.last_signal_time = last_timestamp

    def _check_signals(self):
        if self.df.empty: return None
        last_row = self.df.iloc[-1]
        if last_row['RSI'] < 35 and last_row['close'] > last_row['EMA']: return 'LONG'
        if last_row['RSI'] > 65 and last_row['close'] < last_row['EMA']: return 'SHORT'
        return None

    def start(self): self.is_running = True
    def stop(self): self.is_running = False
