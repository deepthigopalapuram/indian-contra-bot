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

# Expanded Indian Stock Watchlist (NSE Tickers)
NSE_WATCHLIST = [
    "TATAMOTORS.NS", "TATASTEEL.NS", "ZEEL.NS", "UPL.NS", "BIOCON.NS", 
    "EXIDEIND.NS", "BANDHANBNK.NS", "IPCALAB.NS", "WHIRLPOOL.NS", 
    "CROMPTON.NS", "LAURUSLABS.NS", "HEROMOTOCO.NS", "RELIANCE.NS", "INFY.NS"
]

# ==========================================
# 2. TELEGRAM NOTIFICATION FUNCTION
# ==========================================
def send_telegram_alert(message):
    """Sends formatted alert messages to your Telegram Group/Chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing. Skipping notification.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Telegram alert sent successfully!")
        else:
            print(f"Telegram API Error: {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

# ==========================================
# 3. FUNDAMENTAL FILTER (Piotroski Score)
# ==========================================
def calculate_piotroski_f_score(ticker_obj):
    """Calculates Piotroski F-Score (0-9) to filter out value traps."""
    try:
        bs = ticker_obj.balance_sheet
        is_ = ticker_obj.financials
        cf = ticker_obj.cashflow
        
        score = 0
        if bs.empty or is_.empty or cf.empty:
            return 5 # Return neutral score if data is incomplete

        # 1. Positive Net Income
        net_income = is_.loc['Net Income'].iloc[0] if 'Net Income' in is_.index else 0
        if net_income > 0: score += 1
            
        # 2. Positive Operating Cash Flow
        ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
        if ocf > 0: score += 1
            
        # 3. Quality of Earnings (OCF > Net Income)
        if ocf > net_income: score += 1
            
        # 4. Debt Reduction
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
        return 5 # Default neutral score

# ==========================================
# 4. HIGH-SPEED SCANNER & VECTORIZED CALCULATIONS
# ==========================================
def run_high_volume_contra_scanner():
    print("🚀 Starting High-Speed Batch Scan for Indian Equities...")

    # STEP 1: BATCH INGESTION (Download all stock data in ONE API CALL)
    batch_data = yf.download(
        tickers=NSE_WATCHLIST, 
        period="1y", 
        group_by="ticker", 
        threads=True, 
        progress=False
    )
    
    qualified_stocks = []

    # STEP 2: VECTORIZED CALCULATIONS PER STOCK
    for symbol in NSE_WATCHLIST:
        try:
            # Extract DataFrame for individual stock
            if len(NSE_WATCHLIST) > 1:
                df = batch_data[symbol].dropna()
            else:
                df = batch_data.dropna()

            if df.empty or len(df) < 100:
                continue

            # Vectorized Indicators
            df["SMA_200"] = df["Close"].rolling(window=200).mean()
            
            # Vectorized RSI (14-day)
            delta = df["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df["RSI"] = 100 - (100 / (1 + rs))

            # Current Real-Time Metrics
            cmp = round(df["Close"].iloc[-1], 2)
            high_52w = df["Close"].max()
            drawdown = ((high_52w - cmp) / high_52w) * 100
            latest_rsi = round(df["RSI"].iloc[-1], 2) if not pd.isna(df["RSI"].iloc[-1]) else 50.0

            # CONTRA FILTER CONDITION:
            # Stock dropped >= 20% from 52-week high AND RSI <= 45 (Oversold/Consolidation)
            if drawdown >= 20.0 and latest_rsi <= 45.0:
                
                # Fundamental Check (Individual call only for qualified candidates)
                stock_obj = yf.Ticker(symbol)
                f_score = calculate_piotroski_f_score(stock_obj)

                # Avoid Value Traps (Require Piotroski Score >= 5)
                if f_score >= 5:
                    clean_symbol = symbol.replace(".NS", "")
                    target_1 = round(cmp * 1.20, 2)  # Target 1: +20% gain
                    target_2 = round(cmp * 1.35, 2)  # Target 2: +35% gain
                    stop_loss = round(cmp * 0.90, 2) # Stop Loss: -10%

                    # Log candidate into Supabase DB
                    db_entry = {
                        "ticker": clean_symbol,
                        "entry_price": cmp,
                        "target_1": target_1,
                        "target_2": target_2,
                        "stop_loss": stop_loss,
                        "status": "HOLDING"
                    }
                    supabase.table("contra_portfolio").insert(db_entry).execute()

                    # Format Telegram Alert
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
                    print(f"✅ QUALIFIED & SENT TO TELEGRAM: {clean_symbol}")

        except Exception as e:
            print(f"Error processing {symbol}: {e}")

    if not qualified_stocks:
        print("ℹ️ Scan completed. No new contra candidates met the criteria today.")

# ==========================================
# 5. EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    run_high_volume_contra_scanner()
