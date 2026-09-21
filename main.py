import os
import time
import concurrent.futures
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

# ==========================================
# 2. DYNAMIC & DEDUPLICATED TICKER FETCH
# ==========================================
def get_nifty_and_sensex_tickers():
    """Dynamically fetches NIFTY 50 and SENSEX constituents, returning unique Yahoo Tickers."""
    symbols = set()
    
    # 1. Fetch official NIFTY 50 list
    try:
        url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
        df = pd.read_csv(url)
        symbols.update(df['Symbol'].tolist())
    except Exception as e:
        print(f"⚠️ Could not pull NIFTY 50 CSV ({e}). Using fallback list.")
        symbols.update(["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "TATAMOTORS"])

    # 2. Append Sensex constituents to ensure 100% overlap
    sensex_fallback = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "HINDUNILVR", 
        "ITC", "SBIN", "BHARTIARTL", "LTIM", "KOTAKBANK", "LT", "AXISBANK", 
        "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "BAJFINANCE", 
        "POWERGRID", "NTPC", "TATASTEEL", "JSWSTEEL", "M&M", "TECHM", "HCLTECH", 
        "TATAMOTORS", "INDUSINDBK", "NESTLEIND"
    ]
    symbols.update(sensex_fallback)
    
    formatted_tickers = [f"{sym}.NS" for sym in symbols]
    print(f"✅ Target Watchlist: {len(formatted_tickers)} unique NIFTY 50 & SENSEX stocks.")
    return formatted_tickers

# ==========================================
# 3. TELEGRAM NOTIFICATION ENGINE
# ==========================================
def send_telegram_alert(message):
    """Sends formatted Markdown alert to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing. Skipping notification.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("📱 Telegram summary alert dispatched successfully!")
        else:
            print(f"❌ Telegram Error ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

# ==========================================
# 4. FAST PIOTROSKI SCORE EVALUATOR
# ==========================================
def get_piotroski_score_safe(symbol):
    """Fetches fundamental data concurrently only for technical qualifiers."""
    try:
        stock = yf.Ticker(symbol)
        bs = stock.balance_sheet
        is_ = stock.financials
        cf = stock.cashflow
        
        if bs.empty or is_.empty or cf.empty:
            return 5

        score = 0
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
        return 5

# ==========================================
# 5. HIGH-PERFORMANCE VECTORIZED SCANNER
# ==========================================
def run_optimized_scanner():
    start_time = time.time()
    tickers = get_nifty_and_sensex_tickers()
    
    print("🚀 Downloading batch price history for all stocks in ONE request...")
    batch_data = yf.download(
        tickers=tickers, 
        period="1y", 
        group_by="ticker", 
        threads=True, 
        progress=False,
        auto_adjust=True,
        ignore_tz=True
    )
    
    download_time = round(time.time() - start_time, 2)
    print(f"⚡ Batch download finished in {download_time}s.")

    all_processed_stocks = []
    technical_qualifiers = []

    # Fast in-memory processing loop
    for symbol in tickers:
        try:
            if isinstance(batch_data.columns, pd.MultiIndex):
                if symbol not in batch_data.columns.levels[0]:
                    continue
                df = batch_data[symbol].dropna()
            else:
                df = batch_data.dropna()

            if df.empty or len(df) < 100:
                continue

            # Vectorized RSI Calculation
            delta = df["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df["RSI"] = 100 - (100 / (1 + rs))

            cmp = round(float(df["Close"].iloc[-1]), 2)
            high_52w = float(df["Close"].max())
            drawdown = round(((high_52w - cmp) / high_52w) * 100, 1)
            latest_rsi = round(float(df["RSI"].iloc[-1]), 2) if not pd.isna(df["RSI"].iloc[-1]) else 50.0

            clean_symbol = symbol.replace(".NS", "")
            
            # Record for full summary
            stock_record = {
                "symbol": symbol,
                "clean_symbol": clean_symbol,
                "cmp": cmp,
                "drawdown": drawdown,
                "rsi": latest_rsi,
                "is_qualified": False
            }

            # CONTRA FILTER CONDITION: Drawdown >= 20% & RSI <= 45
            if drawdown >= 20.0 and latest_rsi <= 45.0:
                stock_record["is_qualified"] = True
                technical_qualifiers.append(stock_record)

            all_processed_stocks.append(stock_record)

        except Exception as e:
            print(f"❌ Error computing metrics for {symbol}: {e}")

    # Process qualified candidates using ThreadPoolExecutor for fast fundamental checks
    final_qualified = []
    if technical_qualifiers:
        print(f"\n🔍 {len(technical_qualifiers)} candidates met technical criteria. Checking Piotroski scores...")
        
        def process_candidate(candidate):
            f_score = get_piotroski_score_safe(candidate["symbol"])
            if f_score >= 5:
                cmp = candidate["cmp"]
                target_1 = round(cmp * 1.20, 2)
                target_2 = round(cmp * 1.35, 2)
                stop_loss = round(cmp * 0.90, 2)

                # Supabase Log
                db_entry = {
                    "ticker": candidate["clean_symbol"],
                    "entry_price": cmp,
                    "target_1": target_1,
                    "target_2": target_2,
                    "stop_loss": stop_loss,
                    "status": "HOLDING"
                }
                supabase.table("contra_portfolio").insert(db_entry).execute()
                
                candidate["f_score"] = f_score
                candidate["target_1"] = target_1
                candidate["target_2"] = target_2
                candidate["stop_loss"] = stop_loss
                final_qualified.append(candidate)
                print(f"✅ QUALIFIED & LOGGED: {candidate['clean_symbol']}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(process_candidate, technical_qualifiers)

    # ==========================================
    # BUILD COMPREHENSIVE TELEGRAM ALERT
    # ==========================================
    alert_lines = ["📊 *NIFTY 50 & SENSEX DAILY CONTRA SCREENER*\n"]
    alert_lines.append(f"🔍 *Total Stocks Screened:* `{len(all_processed_stocks)}`")
    alert_lines.append(f"🎯 *Opportunities Found:* `{len(final_qualified)}` \n")

    # SECTION 1: QUALIFIED BUY OPPORTUNITIES (IF ANY)
    if final_qualified:
        alert_lines.append("🚨 *QUALIFIED CONTRA BUY CANDIDATES:*")
        for q in final_qualified:
            alert_lines.append(
                f"• *{q['clean_symbol']}* | CMP: ₹{q['cmp']} | Drawdown: -{q['drawdown']}% | RSI: {q['rsi']} | F-Score: {q['f_score']}/9\n"
                f"  🎯 Targets: ₹{q['target_1']} / ₹{q['target_2']} | 🛡️ SL: ₹{q['stop_loss']}"
            )
        alert_lines.append("\n" + "—"*20 + "\n")

    # SECTION 2: SUMMARY LIST OF ALL SCREENED STOCKS
    alert_lines.append("📋 *FULL SCREENED WATCHLIST METRICS:*")
    
    # Sort stocks by drawdown descending so the most discounted stocks are on top
    all_processed_stocks.sort(key=lambda x: x["drawdown"], reverse=True)

    for item in all_processed_stocks:
        status_tag = "✅" if item["is_qualified"] else "⚪"
        alert_lines.append(
            f"{status_tag} `{item['clean_symbol']:<10}` | CMP: ₹{item['cmp']:<7} | DD: -{item['drawdown']}% | RSI: {item['rsi']}"
        )

    # Join and dispatch Telegram message
    full_message = "\n".join(alert_lines)
    
    # Handle Telegram 4096 character length limit by chunking if necessary
    if len(full_message) > 4000:
        chunks = [full_message[i:i+3900] for i in range(0, len(full_message), 3900)]
        for chunk in chunks:
            send_telegram_alert(chunk)
    else:
        send_telegram_alert(full_message)

    total_time = round(time.time() - start_time, 2)
    print(f"\n✨ Scan completed in {total_time} seconds across all NIFTY & SENSEX stocks.")

# ==========================================
# 6. EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    run_optimized_scanner()
