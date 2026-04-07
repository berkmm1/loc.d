import ccxt
import pandas as pd
import time
import os
import threading
from dotenv import load_dotenv
from utils import calculate_indicators, setup_logger, get_timestamp

load_dotenv()

class BingXBot:
    """
    Core Trading Bot class for BingX BTC-USDT Perpetual Futures.
    Handles exchange connectivity, market data, position management, and strategy execution.
    """
    def __init__(self, api_key=None, api_secret=None, sandbox=True):
        self.api_key = api_key or os.getenv('BINGX_API_KEY')
        self.api_secret = api_secret or os.getenv('BINGX_API_SECRET')
        self.sandbox = sandbox

        # Strategy & Risk Parameters (can be updated from UI)
        self.leverage = 10
        self.risk_percent = 1.0
        self.rsi_period = 14
        self.ema_period = 50
        self.timeframe = '1h'
        self.sl_percent = 30.0  # Stop Loss as % of position (including leverage)

        self.symbol = 'BTC/USDT:USDT'
        self.is_running = False
        self.logger = setup_logger('trading_bot', 'bot.log')

        # Internal State
        self.df = pd.DataFrame()
        self.current_price = 0.0
        self.price_change_24h = 0.0
        self.balance = 0.0
        self.positions = []      # Active positions from exchange
        self.trade_history = []  # Local log of trades performed in this session
        self.last_signal_time = None # To prevent multiple entries on same candle

        # Initialize Exchange
        self.exchange = None
        self._init_exchange()

    def _init_exchange(self):
        """Initializes the CCXT BingX exchange instance."""
        try:
            exchange_options = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                }
            }
            self.exchange = ccxt.bingx(exchange_options)

            if self.sandbox:
                self.exchange.set_sandbox_mode(True)
                self.logger.info("Sandbox mode activated.")

            self.update_balance()
            self.logger.info("Exchange connection established.")
        except Exception as e:
            self.logger.error(f"Exchange initialization failed: {e}")

    def update_balance(self):
        """Fetches the current USDT balance from the exchange."""
        try:
            if not self.exchange: return 0.0
            balance_info = self.exchange.fetch_balance()
            self.balance = balance_info['total'].get('USDT', 0.0)
            return self.balance
        except Exception as e:
            self.logger.error(f"Error fetching balance: {e}")
            return 0.0

    def update_market_data(self):
        """Fetches ticker and OHLCV data, then calculates indicators."""
        try:
            if not self.exchange: return False

            # 1. Fetch Ticker for real-time price
            ticker = self.exchange.fetch_ticker(self.symbol)
            self.current_price = ticker['last']
            self.price_change_24h = ticker['percentage']

            # 2. Fetch OHLCV for indicators
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            # 3. Calculate Indicators
            self.df = calculate_indicators(df, self.rsi_period, self.ema_period)

            return True
        except Exception as e:
            self.logger.error(f"Error updating market data: {e}")
            return False

    def update_positions(self):
        """Fetches active positions and performs automated SL/TP management."""
        try:
            if not self.exchange: return []

            raw_positions = self.exchange.fetch_positions([self.symbol])
            self.positions = [p for p in raw_positions if float(p.get('contracts', 0)) > 0]

            # Manage each position automatically
            for pos in self.positions:
                self._manage_position(pos)

            return self.positions
        except Exception as e:
            self.logger.error(f"Error updating positions: {e}")
            return []

    def _manage_position(self, pos):
        """Handles SL/TP for a position."""
        side = pos['side'].lower()
        entry_price = float(pos['entryPrice'])
        curr_price = self.current_price

        if entry_price == 0: return

        # PNL percentage calculation
        if side == 'long':
            pnl_pct = (curr_price - entry_price) / entry_price * self.leverage * 100
        else:
            pnl_pct = (entry_price - curr_price) / entry_price * self.leverage * 100

        # SL: -30%
        if pnl_pct <= -self.sl_percent:
            self.logger.warning(f"STOP LOSS triggered for {side.upper()} at {pnl_pct:.2f}%")
            self.close_position(side)

        # TP: RSI signal or 1:2 RR
        last_rsi = self.df.iloc[-1]['RSI'] if not self.df.empty else 50

        # LONG exit: RSI > 70
        # SHORT exit: RSI < 30
        long_tp = side == 'long' and (last_rsi > 70 or pnl_pct >= self.sl_percent * 2)
        short_tp = side == 'short' and (last_rsi < 30 or pnl_pct >= self.sl_percent * 2)

        if long_tp or short_tp:
            self.logger.info(f"TAKE PROFIT triggered for {side.upper()} at {pnl_pct:.2f}% (RSI: {last_rsi:.2f})")
            self.close_position(side)

    def open_position(self, side):
        """Executes a market order to open a position."""
        try:
            if not self.exchange: return False
            self.exchange.set_leverage(self.leverage, self.symbol)

            amount = (self.balance * (self.risk_percent / 100)) / self.current_price * self.leverage
            amount = float(self.exchange.amount_to_precision(self.symbol, amount))

            order = self.exchange.create_market_order(self.symbol, side, amount)
            trade_type = 'LONG' if side == 'buy' else 'SHORT'
            self.logger.info(f"Successfully opened {trade_type} position. Amount: {amount}")

            self.trade_history.append({
                'time': get_timestamp(),
                'type': trade_type,
                'price': self.current_price,
                'amount': amount,
                'status': 'OPEN'
            })
            return True
        except Exception as e:
            self.logger.error(f"Failed to open position: {e}")
            return False

    def close_position(self, side=None):
        """Closes positions for the symbol."""
        try:
            if not self.exchange: return False
            self.update_positions()

            target_positions = self.positions
            if side:
                # Handle 'buy'/'sell' to 'long'/'short' mapping
                side_map = {'buy': 'long', 'sell': 'short', 'long': 'long', 'short': 'short'}
                target_side = side_map.get(side.lower(), side.lower())
                target_positions = [p for p in self.positions if p['side'].lower() == target_side]

            if not target_positions: return False

            for pos in target_positions:
                close_side = 'sell' if pos['side'] == 'long' else 'buy'
                amount = float(pos['contracts'])
                self.exchange.create_market_order(self.symbol, close_side, amount, params={'reduceOnly': True})
                self.logger.info(f"Closed {pos['side'].upper()} position.")

                self.trade_history.append({
                    'time': get_timestamp(),
                    'type': f"CLOSE {pos['side'].upper()}",
                    'price': self.current_price,
                    'amount': amount,
                    'status': 'CLOSED'
                })
            self.update_balance()
            return True
        except Exception as e:
            self.logger.error(f"Error during position closure: {e}")
            return False

    def bot_cycle(self):
        """Main loop iteration."""
        if not self.update_market_data(): return
        self.update_positions()
        self.update_balance()

        if self.is_running and not self.df.empty:
            last_timestamp = self.df.iloc[-1]['timestamp']

            # Only trade if this candle hasn't been traded yet
            if self.last_signal_time != last_timestamp:
                signal = self._check_signals()
                if signal == 'LONG':
                    if self.open_position('buy'):
                        self.last_signal_time = last_timestamp
                elif signal == 'SHORT':
                    if self.open_position('sell'):
                        self.last_signal_time = last_timestamp

    def _check_signals(self):
        """Strategy logic."""
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
        self.logger.info("Bot Engine Started.")

    def stop(self):
        self.is_running = False
        self.logger.info("Bot Engine Stopped.")
