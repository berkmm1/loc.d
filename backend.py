from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import threading
import time
import os
from bot import BingXBot
from utils import calculate_indicators

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global bot instance
bot = BingXBot(sandbox=True)

class TradeAction(BaseModel):
    side: str

class ConfigUpdate(BaseModel):
    leverage: int
    risk_percent: float
    rsi_period: int
    ema_period: int

@app.get("/", response_class=HTMLResponse)
def get_index():
    with open("index.html", "r") as f:
        return f.read()

@app.get("/status")
def get_status():
    bot.bot_cycle()
    return {
        "price": bot.current_price,
        "change24h": bot.price_change_24h,
        "balance": bot.balance,
        "is_running": bot.is_running,
        "positions": bot.positions,
        "history": bot.trade_history[-10:]
    }

@app.post("/trade")
def execute_trade(action: TradeAction):
    success = bot.open_position(action.side)
    if not success:
        raise HTTPException(status_code=400, detail="Trade failed")
    return {"status": "success"}

@app.post("/close")
def close_all():
    bot.close_position()
    return {"status": "success"}

@app.post("/start")
def start_bot():
    bot.start()
    return {"status": "started"}

@app.post("/stop")
def stop_bot():
    bot.stop()
    return {"status": "stopped"}

def run_bot_background():
    while True:
        try:
            if bot.is_running:
                bot.bot_cycle()
        except Exception as e:
            print(f"Bot error: {e}")
        time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=run_bot_background, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
