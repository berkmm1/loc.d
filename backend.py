from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import threading
import time
import os
from bot import BingXBot

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use environmental variable for Neon URL
DATABASE_URL = os.getenv('DATABASE_URL')
bot = BingXBot(sandbox=True, db_url=DATABASE_URL)

class TradeAction(BaseModel):
    side: str

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
        "history": bot.get_trade_history(10) # Now persistent!
    }

@app.get("/chart")
def get_chart_data():
    if bot.df.empty: bot.update_market_data()
    return bot.df.tail(100).to_dict(orient="records")

@app.post("/trade")
def execute_trade(action: TradeAction):
    success = bot.open_position(action.side)
    if not success: raise HTTPException(status_code=400, detail="Trade failed")
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
            if bot.is_running: bot.bot_cycle()
        except: pass
        time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=run_bot_background, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
