from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import threading
import time
import os
from bot import BingXBot

# Initializing FastAPI app
app = FastAPI(title="Vertex Terminal API")

# Setting up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from Environment
DATABASE_URL = os.getenv('DATABASE_URL')
# Sandbox mode defaults to True for safety unless specified
SANDBOX_MODE = os.getenv('SANDBOX_MODE', 'True').lower() == 'true'

# Global Bot Instance
bot = BingXBot(sandbox=SANDBOX_MODE, db_url=DATABASE_URL)

class TradeAction(BaseModel):
    side: str # 'buy' or 'sell'

@app.get("/", response_class=HTMLResponse)
def get_index():
    """Serves the main trading terminal UI."""
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Terminal UI file not found."

@app.get("/status")
def get_status():
    """Returns the current bot status, price, and history."""
    # Ensure data is fresh
    bot.bot_cycle()
    return {
        "price": bot.current_price,
        "change24h": bot.price_change_24h,
        "balance": bot.balance,
        "is_running": bot.is_running,
        "positions": bot.positions,
        "history": bot.get_trade_history(15), # Increased limit for better UX
        "sandbox": bot.sandbox
    }

@app.get("/chart")
def get_chart_data():
    """Returns historical OHLCV data for the chart."""
    if bot.df.empty:
        bot.update_market_data()
    return bot.df.tail(100).to_dict(orient="records")

@app.post("/trade")
def execute_trade(action: TradeAction):
    """Manually executes a market order."""
    if action.side not in ['buy', 'sell']:
        raise HTTPException(status_code=400, detail="Invalid trade side")
    success = bot.open_position(action.side)
    if not success:
        raise HTTPException(status_code=400, detail="Trade execution failed")
    return {"status": "success", "side": action.side}

@app.post("/close")
def close_all():
    """Liquidates all open positions for the symbol."""
    success = bot.close_position()
    return {"status": "success" if success else "no_positions"}

@app.post("/start")
def start_bot():
    """Starts the automated trading engine."""
    bot.start()
    return {"status": "started"}

@app.post("/stop")
def stop_bot():
    """Stops the automated trading engine."""
    bot.stop()
    return {"status": "stopped"}

def run_bot_background():
    """Background loop to ensure the bot keeps running signals."""
    while True:
        try:
            if bot.is_running:
                bot.bot_cycle()
        except Exception as e:
            print(f"Background Bot Loop Error: {e}")
        time.sleep(10) # 10 seconds resolution for checking signals

if __name__ == "__main__":
    # Start the engine thread
    engine_thread = threading.Thread(target=run_bot_background, daemon=True)
    engine_thread.start()

    # Use port from environment (Render default is often 10000 or 8080)
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
