import os
import time
import datetime
import concurrent.futures
import pandas as pd
import numpy as np
import yfinance as yf
from supabase import create_client

# ==========================================
# 1. ENVIRONMENT VARIABLES & CONNECTIONS
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. TICKER CLEANUP & DYNAMIC FETCH
# ==========================================
def clean_ticker_symbol(symbol):
    """Ensures valid Yahoo Finance ticker mapping."""
    ticker_map = {
        "TATAMOTORS": "TATAMOTORS.NS",
        "LTIM": "LTIM.NS",
    }
    clean_sym = symbol.strip().upper()
    return ticker_map.get(clean_sym, f"{clean_sym}.NS")

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
        "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", 
        "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "BAJFINANCE", 
        "POWERGRID", "NTPC", "TATASTEEL", "JSWSTEEL", "M&M", "TECHM", "HCLTECH", 
        "TATAMOTORS", "INDUSINDBK", "NESTLEIND"
    ]
    symbols.update(sensex_fallback)
    
    formatted_tickers = [clean_ticker_symbol(sym) for sym in symbols]
    print(f"✅ Target Watchlist: {len(formatted_tickers)} unique NIFTY 50 & SENSEX stocks.")
    return formatted_tickers

# ==========================================
# 3. WEBPAGE DASHBOARD GENERATOR (MONEYCONTROL STYLE)
# ==========================================
def generate_html_dashboard(all_stocks, qualified_stocks):
    """Generates a modern, responsive HTML dashboard for GitHub Pages."""
    updated_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Sort qualified stocks by Piotroski score (descending)
    qualified_stocks.sort(key=lambda x: x.get("f_score", 0), reverse=True)
    
    # Sort all watched stocks by drawdown (descending)
    all_stocks.sort(key=lambda x: x["drawdown"], reverse=True)

    qualified_rows = ""
    if qualified_stocks:
        for q in qualified_stocks:
            qualified_rows += f"""
            <tr>
                <td><strong class="symbol">{q['clean_symbol']}</strong></td>
                <td>₹{q['cmp']}</td>
                <td><span class="text-danger">-{q['drawdown']}%</span></td>
                <td>{q['rsi']}</td>
                <td><span class="badge badge-fscore">{q['f_score']}/9</span></td>
                <td>₹{q['target_1']} / ₹{q['target_2']}</td>
                <td><span class="text-sl">₹{q['stop_loss']}</span></td>
            </tr>
            """
    else:
        qualified_rows = """
        <tr>
            <td colspan="7" class="text-center text-muted">No stock currently meets both technical & fundamental contra criteria.</td>
        </tr>
        """

    watchlist_rows = ""
    for s in all_stocks:
        status_badge = '<span class="badge badge-success">BUY CALL</span>' if s['is_qualified'] else '<span class="badge badge-secondary">WATCH</span>'
        watchlist_rows += f"""
        <tr>
            <td><strong>{s['clean_symbol']}</strong></td>
            <td>₹{s['cmp']}</td>
            <td>-{s['drawdown']}%</td>
            <td>{s['rsi']}</td>
            <td>{status_badge}</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Indian Stock Contra Screener Dashboard</title>
    <style>
        :root {{
            --primary: #1e293b;
            --accent: #2563eb;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --success: #16a34a;
            --danger: #dc2626;
            --border: #e2e8f0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: #334155;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .header {{
            background: var(--primary);
            color: white;
            padding: 20px 25px;
            border-radius: 10px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .header h1 {{
            margin: 0 0 5px 0;
            font-size: 24px;
        }}
        .header p {{
            margin: 0;
            font-size: 13px;
            color: #94a3b8;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }}
        .stat-card {{
            background: var(--card-bg);
            padding: 15px 20px;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        .stat-card .label {{
            font-size: 12px;
            color: #64748b;
            text-transform: uppercase;
            font-weight: 600;
        }}
        .stat-card .value {{
            font-size: 22px;
            font-weight: bold;
            color: var(--primary);
            margin-top: 5px;
        }}
        .card {{
            background: var(--card-bg);
            border-radius: 10px;
            border: 1px solid var(--border);
            padding: 20px;
            margin-bottom: 25px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .card-title {{
            font-size: 18px;
            font-weight: 700;
            margin-top: 0;
            margin-bottom: 15px;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background-color: #f1f5f9;
            color: #475569;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f8fafc;
        }}
        .symbol {{
            color: var(--accent);
        }}
        .text-danger {{
            color: var(--danger);
            font-weight: 600;
        }}
        .text-sl {{
            color: #b91c1c;
        }}
        .text-center {{
            text-align: center;
        }}
        .text-muted {{
            color: #94a3b8;
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }}
        .badge-success {{
            background: #dcfce7;
            color: #15803d;
        }}
        .badge-secondary {{
            background: #f1f5f9;
            color: #64748b;
        }}
        .badge-fscore {{
            background: #dbeafe;
            color: #1d4ed8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 NIFTY 50 & SENSEX Contra Screener</h1>
            <p>Last Market Scan Updated: <strong>{updated_time}</strong></p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Watchlist</div>
                <div class="value">{len(all_stocks)} Stocks</div>
            </div>
            <div class="stat-card">
                <div class="label">Qualified Signals</div>
                <div class="value" style="color: var(--success);">{len(qualified_stocks)} Qualified</div>
            </div>
        </div>

        <!-- SECTION 1: QUALIFIED BUY OPPORTUNITIES -->
        <div class="card">
            <div class="card-title">🚨 Qualified Contra Buy Opportunities</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>CMP</th>
                            <th>Drawdown</th>
                            <th>RSI</th>
                            <th>F-Score</th>
                            <th>Targets (1 & 2)</th>
                            <th>Stop Loss</th>
                        </tr>
                    </thead>
                    <tbody>
                        {qualified_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- SECTION 2: FULL WATCHLIST -->
        <div class="card">
            <div class="card-title">📋 Full Screened Watchlist Metrics</div>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>CMP</th>
                            <th>Drawdown</th>
                            <th>RSI</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {watchlist_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print("✅ Webpage successfully generated as index.html")

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

    # Generate HTML Output for GitHub Pages
    generate_html_dashboard(all_processed_stocks, final_qualified)

    total_time = round(time.time() - start_time, 2)
    print(f"\n✨ Scan completed in {total_time} seconds across all NIFTY & SENSEX stocks.")

# ==========================================
# 6. EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    run_optimized_scanner()
