import os
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from supabase import create_client

# ==========================================
# 1. ENVIRONMENT VARIABLES & CONNECTIONS
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Indian Stock Watchlist (NSE Tickers)
NSE_WATCHLIST = [
    "TATAMOTORS.NS", "TATASTEEL.NS", "ZEEL.NS", "UPL.NS", "BIOCON.NS", 
    "EXIDEIND.NS", "BANDHANBNK.NS", "IPCALAB.NS", "WHIRLPOOL.NS", 
    "CROMPTON.NS", "LAURUSLABS.NS", "HEROMOTOCO.NS", "RELIANCE.NS", "INFY.NS"
]

# Set standard browser user-agent for yfinance requests
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# ==========================================
# 2. TELEGRAM NOTIFICATION ENGINE
# ==========================================
def send_telegram_alert(message):
    """Sends a formatted Markdown alert to your Telegram chat/group."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram environment variables missing. Skipping alert dispatch.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("📱 Telegram alert sent successfully!")
        else:
            print(f"❌ Telegram API Error ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

# ==========================================
# 3. FUNDAMENTAL SAFETY FILTER (Piotroski Score)
# ==========================================
def calculate_piotroski_f_score(ticker_obj):
    """Calculates Piotroski F-Score (0-9) to filter out value traps."""
    try:
        bs = ticker_obj.balance_sheet
        is_ = ticker_obj.financials
        cf = ticker_obj.cashflow
        
        score = 0
        if bs.empty or is_.empty or cf.empty:
            return 5  # Neutral score if data is incomplete

        # 1. Positive Net Income
        net_income = is_.loc['Net Income'].iloc[0] if 'Net Income' in is_.index else 0
        if net_income > 0: score += 1
            
        # 2. Positive Operating Cash Flow
        ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
        if ocf > 0: score += 1
            
        # 3. Quality of Earnings (OCF > Net Income)
        if ocf > net_income: score += 1
            
        # 4. Long-Term Debt Reduction
        if 'Long Term Debt' in bs.index and len(bs.loc['Long Term Debt']) > 1:
            if bs.loc['Long Term Debt'].iloc[0] <= bs.loc['Long Term Debt'].iloc[1]:
                score += 1
        else:
            score += 1

        # 5. Higher Current Ratio
        if 'Current Assets' in bs.index and 'Current Liabilities' in bs.index:
            cr_curr = bs.loc['Current Assets'].iloc[0] / bs.loc['Current Liabilities'].iloc[0]
            cr_prev = bs.loc['Current Assets'].iloc[1] / bs.loc['Current Liabilities'].iloc[1]
            if cr_curr > cr_prev: score += 1

        return score
    except Exception:
        return 5

# ==========================================
# 4. ROBUST STOCK SCANNER
# ==========================================
def run_high_volume_contra_scanner():
    print("🚀 Starting Scan for Indian Equities...")
    qualified_stocks = []

    for symbol in NSE_WATCHLIST:
        try:
            # Fetch data per ticker using explicit session
            stock_obj = yf.Ticker(symbol, session=session)
            df = stock_obj.history(period="1y")

            if df.empty or len(df) < 100:
                print(f"⚠️ No data retrieved for {symbol}")
                continue

            # Indicators
            df["SMA_200"] = df["Close"].rolling(window=200).mean()
            
            # 14-Day RSI
            delta = df["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df["RSI"] = 100 - (100 / (1 + rs))

            cmp = round(float(df["Close"].iloc[-1]), 2)
            high_52w = float(df["Close"].max())
            drawdown = ((high_52w - cmp) / high_52w) * 100
            latest_rsi = round(float(df["RSI"].iloc[-1]), 2) if not pd.isna(df["RSI"].iloc[-1]) else 50.0

            # CONTRA FILTER: Drop >= 20% from 52W High AND RSI <= 45
            if drawdown >= 20.0 and latest_rsi <= 45.0:
                f_score = calculate_piotroski_f_score(stock_obj)

                if f_score >= 5:
                    clean_symbol = symbol.replace(".NS", "")
                    target_1 = round(cmp * 1.20, 2)
                    target_2 = round(cmp * 1.35, 2)
                    stop_loss = round(cmp * 0.90, 2)

                    # Insert into Supabase
                    db_entry = {
                        "ticker": clean_symbol,
                        "entry_price": cmp,
                        "target_1": target_1,
                        "target_2": target_2,
                        "stop_loss": stop_loss,
                        "status": "HOLDING"
                    }
                    supabase.table("contra_portfolio").insert(db_entry).execute()

                    # Send Telegram Notification
                    alert_msg = (
                        f"🚨 *NEW CONTRA OPPORTUNITY DETECTED*\n\n"
                        f"📈 *Stock:* `{clean_symbol}`\n"
                        f"💵 *CMP:* ₹{cmp}\n"
                        f"📉 *52W Drawdown:* -{round(drawdown, 1)}%\n"
                        f"📊 *Piotroski Score:* {f_score}/9\n\n"
                        f"🎯 *Target 1 (Book 50%):* ₹{target_1} (+20%)\n"
                        f"🎯 *Target 2 (Exit All):* ₹{target_2} (+35%)\n"
                        f"🛡️ *Stop Loss:* ₹{stop_loss}"
                    )
                    
                    send_telegram_alert(alert_msg)
                    qualified_stocks.append(clean_symbol)
                    print(f"✅ QUALIFIED & LOGGED: {clean_symbol}")

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

    if not qualified_stocks:
        print("ℹ️ Scan completed. No new contra candidates met the criteria today.")

# ==========================================
# 5. EXECUTION
# ==========================================
if __name__ == "__main__":
    run_high_volume_contra_scanner()
