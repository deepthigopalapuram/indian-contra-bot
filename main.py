import os
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from supabase import create_client

# Try importing nselib for direct NSE data retrieval
try:
    from nselib import capital_market
    USE_NSELIB = True
except ImportError:
    USE_NSELIB = False

# ==========================================
# 1. ENVIRONMENT VARIABLES & CONNECTIONS
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Stock Symbols (Clean NSE Symbols)
NSE_SYMBOLS = [
    "TATAMOTORS", "TATASTEEL", "ZEEL", "UPL", "BIOCON", 
    "EXIDEIND", "BANDHANBNK", "IPCALAB", "WHIRLPOOL", 
    "CROMPTON", "LAURUSLABS", "HEROMOTOCO", "RELIANCE", "INFY"
]

# Standard Headers for direct NSE HTTP requests
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

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
# 3. DIRECT NSE / FALLBACK DATA FETCHERS
# ==========================================
def get_historical_data_nse(symbol):
    """
    Primary: Fetches historical data directly via nselib or Yahoo Finance fallback.
    """
    # 1. Try Direct Yahoo Ticker History
    try:
        yf_symbol = f"{symbol}.NS"
        stock_obj = yf.Ticker(yf_symbol)
        df = stock_obj.history(period="1y")
        if not df.empty and len(df) >= 100:
            return df, stock_obj
    except Exception as e:
        print(f"⚠️ Yahoo Finance failed for {symbol}: {e}")

    # 2. Fallback: Direct NSE Lib if Yahoo is blocked
    if USE_NSELIB:
        try:
            # Fetch last 365 days from NSE
            data = capital_market.price_volume_and_deliverable_position_data(symbol=symbol, period='1Y')
            if not data.empty:
                df = data[['ClosePrice', 'HighPrice', 'LowPrice']].copy()
                df.rename(columns={'ClosePrice': 'Close', 'HighPrice': 'High', 'LowPrice': 'Low'}, inplace=True)
                df['Close'] = pd.to_numeric(df['Close'].str.replace(',', ''), errors='coerce')
                df = df.dropna()
                return df, None
        except Exception as e:
            print(f"⚠️ NSE Direct fetch failed for {symbol}: {e}")

    return None, None

def calculate_piotroski_f_score(ticker_obj):
    """Calculates Piotroski F-Score safely with fallbacks."""
    if ticker_obj is None:
        return 5  # Return neutral score if fundamentals engine is bypassed

    try:
        bs = ticker_obj.balance_sheet
        is_ = ticker_obj.financials
        cf = ticker_obj.cashflow
        
        score = 0
        if bs is None or is_ is None or cf is None or bs.empty or is_.empty or cf.empty:
            return 5

        net_income = is_.loc['Net Income'].iloc[0] if 'Net Income' in is_.index else 0
        if net_income > 0: score += 1
            
        ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
        if ocf > 0: score += 1
            
        if ocf > net_income: score += 1
            
        if 'Long Term Debt' in bs.index and len(bs.loc['Long Term Debt']) > 1:
            if bs.loc['Long Term Debt'].iloc[0] <= bs.loc['Long Term Debt'].iloc[1]:
                score += 1
        else:
            score += 1

        if 'Current Assets' in bs.index and 'Current Liabilities' in bs.index:
            cr_curr = bs.loc['Current Assets'].iloc[0] / bs.loc['Current Liabilities'].iloc[0]
            cr_prev = bs.loc['Current Assets'].iloc[1] / bs.loc['Current Liabilities'].iloc[1]
            if cr_curr > cr_prev: score += 1

        return score
    except Exception:
        return 5  # Fallback score if Yahoo blocks quoteSummary

# ==========================================
# 4. MAIN SCANNING ENGINE
# ==========================================
def run_high_volume_contra_scanner():
    print("🚀 Starting Hybrid NSE/Yahoo Contra Scan for Indian Equities...")
    qualified_stocks = []

    for symbol in NSE_SYMBOLS:
        try:
            df, stock_obj = get_historical_data_nse(symbol)

            if df is None or df.empty or len(df) < 100:
                print(f"❌ Could not retrieve valid data for {symbol} from any provider.")
                continue

            # Compute Technical Indicators
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

            print(f"📊 Processed {symbol} | CMP: ₹{cmp} | Drawdown: -{round(drawdown, 1)}% | RSI: {latest_rsi}")

            # CONTRA FILTER: Drop >= 20% from 52W High AND RSI <= 45
            if drawdown >= 20.0 and latest_rsi <= 45.0:
                f_score = calculate_piotroski_f_score(stock_obj)

                if f_score >= 5:
                    target_1 = round(cmp * 1.20, 2)
                    target_2 = round(cmp * 1.35, 2)
                    stop_loss = round(cmp * 0.90, 2)

                    # Save record to Supabase
                    db_entry = {
                        "ticker": symbol,
                        "entry_price": cmp,
                        "target_1": target_1,
                        "target_2": target_2,
                        "stop_loss": stop_loss,
                        "status": "HOLDING"
                    }
                    supabase.table("contra_portfolio").insert(db_entry).execute()

                    # Send Telegram Alert
                    alert_msg = (
                        f"🚨 *NEW CONTRA OPPORTUNITY DETECTED*\n\n"
                        f"📈 *Stock:* `{symbol}`\n"
                        f"💵 *CMP:* ₹{cmp}\n"
                        f"📉 *52W Drawdown:* -{round(drawdown, 1)}%\n"
                        f"📊 *Piotroski Score:* {f_score}/9\n\n"
                        f"🎯 *Target 1 (Book 50%):* ₹{target_1} (+20%)\n"
                        f"🎯 *Target 2 (Exit All):* ₹{target_2} (+35%)\n"
                        f"🛡️ *Stop Loss:* ₹{stop_loss}"
                    )
                    
                    send_telegram_alert(alert_msg)
                    qualified_stocks.append(symbol)
                    print(f"✅ QUALIFIED & LOGGED: {symbol}")

        except Exception as e:
            print(f"❌ Error processing {symbol}: {e}")

    if not qualified_stocks:
        print("ℹ️ Scan completed. No new contra candidates met the criteria today.")

# ==========================================
# 5. EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    run_high_volume_contra_scanner()
