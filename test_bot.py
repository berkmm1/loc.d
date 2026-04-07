import unittest
import pandas as pd
from utils import calculate_indicators
from bot import BingXBot

class TestTradingBot(unittest.TestCase):
    def test_indicator_calculation(self):
        data = {
            'close': [100 + i for i in range(100)]
        }
        df = pd.DataFrame(data)
        df = calculate_indicators(df, rsi_period=14, ema_period=50)

        self.assertIn('RSI', df.columns)
        self.assertIn('EMA', df.columns)
        self.assertFalse(df['RSI'].isnull().all())
        self.assertFalse(df['EMA'].isnull().all())

    def test_bot_initialization(self):
        # Mocking API keys for initialization test
        bot = BingXBot(api_key='test', api_secret='test', sandbox=True)
        self.assertEqual(bot.symbol, 'BTC/USDT:USDT')
        self.assertTrue(bot.sandbox)

if __name__ == '__main__':
    unittest.main()
