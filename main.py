
import os
import requests
import yfinance as yf
from supabase import create_client

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# List of Indian stocks to screen
NSE_TICKERS = ["TATAMOTORS.NS", "TATASTEEL.NS", "ZEEL.NS", "UPL.NS", "BIOCON.NS", "EXIDEIND.NS"]

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def process_contra_stocks():
    for symbol in NSE_TICKERS:
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="1y")
            if hist.empty or len(hist) < 200:
                continue

            cmp = round(hist['Close'].iloc[-1], 2)
            high_52w = hist['Close'].max()
            drawdown = ((high_52w - cmp) / high_52w) * 100

            # Condition: Stock is beaten down by >= 25% from 52-week high
            if drawdown >= 25.0:
                t1 = round(cmp * 1.20, 2)  # Target 1: 20% gain
                t2 = round(cmp * 1.35, 2)  # Target 2: 35% gain
                sl = round(cmp * 0.90, 2)  # Stop loss: 10%

                clean_symbol = symbol.replace(".NS", "")

                # Log to Supabase Database
                data = {
                    "ticker": clean_symbol,
                    "entry_price": cmp,
                    "target_1": t1,
                    "target_2": t2,
                    "stop_loss": sl
                }
                supabase.table("contra_portfolio").insert(data).execute()

                # Send Alert
                alert_msg = (
                    f"🚨 *NEW CONTRA STOCK DETECTED*\n\n"
                    f"*Stock:* {clean_symbol}\n"
                    f"*CMP:* ₹{cmp}\n"
                    f"*Drawdown:* {round(drawdown, 1)}%\n\n"
                    f"🎯 *Target 1 (Book 50%):* ₹{t1}\n"
                    f"🎯 *Target 2 (Exit All):* ₹{t2}\n"
                    f"🛡️ *Stop Loss:* ₹{sl}"
                )
                send_telegram_alert(alert_msg)

        except Exception as e:
            print(f"Error processing {symbol}: {e}")

if __name__ == "__main__":
    process_contra_stocks()
