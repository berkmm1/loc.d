import pandas as pd
import pandas_ta as ta
import logging
import os
from datetime import datetime

# Logging setup: Creates a logger that writes to both file and console
def setup_logger(name, log_file, level=logging.INFO):
    """
    Sets up a logger with the specified name and log file.
    """
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File handler
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if logger is already setup
    if not logger.handlers:
        logger.addHandler(handler)

        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

# Technical Indicators: Uses pandas_ta for calculations
def calculate_indicators(df, rsi_period=14, ema_period=50):
    """
    Calculates RSI and EMA indicators for the given dataframe.
    Expects 'close' column in the dataframe.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # Copy to avoid modifying original dataframe
    df = df.copy()

    # Ensure dataframe has enough data for indicators
    if len(df) < max(rsi_period, ema_period):
        return df

    # RSI Calculation
    df['RSI'] = ta.rsi(df['close'], length=rsi_period)

    # EMA Calculation
    df['EMA'] = ta.ema(df['close'], length=ema_period)

    return df

# Helper to get current timestamp string
def get_timestamp():
    """
    Returns the current time in a readable format.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Helper for currency formatting
def format_currency(value):
    """
    Formats a numeric value as a currency string.
    """
    return f"${value:,.2f}"
