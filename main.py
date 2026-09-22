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

supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ==========================================
# 2. FETCH ENTIRE NSE & BSE TICKER UNIVERSE
# ==========================================
def get_full_indian_market_universe():
    """Fetches all equity tickers listed on NSE dynamically."""
    nse_symbols = set()
    
    # 1. Fetch Official All NSE Listed Equity Master List
    try:
        nse_url = "https://archives.nseindia.com/content/EQUITY_L.csv"
        headers = {'User-Agent': 'Mozilla/5.0'}
        df_nse = pd.read_csv(nse_url, storage_options=headers)
        
        # Filter active EQ series
        df_eq = df_nse[df_nse[' SERIES'].str.strip() == 'EQ'] if ' SERIES' in df_nse.columns else df_nse
        for sym in df_eq['SYMBOL'].dropna().unique():
            nse_symbols.add(f"{sym.strip().upper()}.NS")
        print(f"✅ Downloaded {len(nse_symbols)} active NSE equities.")
    except Exception as e:
        print(f"⚠️ Could not pull complete NSE CSV ({e}). Using NIFTY 500 fallback.")
        try:
            fallback_url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
            df_f = pd.read_csv(fallback_url)
            for sym in df_f['Symbol'].dropna().unique():
                nse_symbols.add(f"{sym.strip().upper()}.NS")
        except Exception:
            pass

    tickers = list(nse_symbols)
    print(f"🌐 Total Market Universe: {len(tickers)} stocks queued for analysis.")
    return tickers

# ==========================================
# 3. WEBPAGE DASHBOARD GENERATOR
# ==========================================
def generate_html_dashboard(all_stocks, qualified_stocks):
    """Generates an HTML report for GitHub Pages."""
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

    # Display Top 200 discounted stocks in the summary table
    watchlist_rows = ""
    for s in all_stocks[:200]:
        status_badge = '<span class="badge badge-success">BUY CANDIDATE</span>' if s['is_qualified'] else '<span class="badge badge-secondary">WATCH</span>'
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
    <title>All-India Stock Contra Screener</title>
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
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: #334155;
            margin: 0;
            padding: 20px;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{
            background: var(--primary);
            color: white;
            padding: 20px 25px;
            border-radius: 10px;
            margin-bottom: 25px;
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
        .stat-card .label {{ font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
        .stat-card .value {{ font-size: 22px; font-weight: bold; color: var(--primary); margin-top: 5px; }}
        .card {{
            background: var(--card-bg);
            border-radius: 10px;
            border: 1px solid var(--border);
            padding: 20px;
            margin-bottom: 25px;
        }}
        .card-title {{ font-size: 18px; font-weight: 700; margin-bottom: 15px; color: var(--primary); }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ background-color: #f1f5f9; color: #475569; font-weight: 600; }}
        tr:hover {{ background-color: #f8fafc; }}
        .symbol {{ color: var(--accent); }}
        .text-danger {{ color: var(--danger); font-weight: 600; }}
        .text-sl {{ color: #b91c1c; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
        .badge-success {{ background: #dcfce7; color: #15803d; }}
        .badge-secondary {{ background: #f1f5f9; color: #64748b; }}
        .badge-fscore {{ background: #dbeafe; color: #1d4ed8; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 All-India Stock Market Contra Screener</h1>
            <p>Last Full Market Scan Updated: <strong>{updated_time}</strong></p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Stocks Scanned</div>
                <div class="value">{len(all_stocks)} Stocks</div>
            </div>
            <div class="stat-card">
                <div class="label">Qualified Signals</div>
                <div class="value" style="color: var(--success);">{len(qualified_stocks)} Qualified</div>
            </div>
        </div>

        <!-- SECTION 1: QUALIFIED BUY OPPORTUNITIES -->
        <div class="card">
            <div class="card-title">🚨 Qualified Contra Opportunities (All Market)</div>
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
                    <tbody>{qualified_rows}</tbody>
                </table>
            </div>
        </div>

        <!-- SECTION 2: TOP DISCOUNTED WATCHLIST -->
        <div class="card">
            <div class="card-title">📋 Top 200 Discounted Stocks (Watchlist Metrics)</div>
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
                    <tbody>{watchlist_rows}</tbody>
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
    """Executes fundamentals check ONLY on technically pre-filtered candidates."""
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
# 5. CHUNKED BATCH SCANNER ENGINE
# ==========================================
def run_optimized_scanner():
    start_time = time.time()
    tickers = get_full_indian_market_universe()
    
    # Chunk universe into batches of 250 tickers to prevent payload limits
    chunk_size = 250
    ticker_chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    
    all_processed_stocks = []
    technical_qualifiers = []

    print(f"🚀 Processing {len(tickers)} stocks across {len(ticker_chunks)} parallelized batch downloads...")

    for idx, chunk in enumerate(ticker_chunks, 1):
        try:
            print(f"📥 Batch {idx}/{len(ticker_chunks)}: Downloading {len(chunk)} tickers...")
            batch_data = yf.download(
                tickers=chunk, 
                period="1y", 
                group_by="ticker", 
                threads=True, 
                progress=False,
                auto_adjust=True,
                ignore_tz=True
            )

            for symbol in chunk:
                try:
                    if isinstance(batch_data.columns, pd.MultiIndex):
                        if symbol not in batch_data.columns.levels[0]:
                            continue
                        df = batch_data[symbol].dropna()
                    else:
                        df = batch_data.dropna()

                    if df.empty or len(df) < 50:
                        continue

                    # Fast RSI Calculation
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
                    
                    stock_record = {
                        "symbol": symbol,
                        "clean_symbol": clean_symbol,
                        "cmp": cmp,
                        "drawdown": drawdown,
                        "rsi": latest_rsi,
                        "is_qualified": False
                    }

                    # CONTRA FILTER: Drawdown >= 20% & RSI <= 45
                    if drawdown >= 20.0 and latest_rsi <= 45.0:
                        stock_record["is_qualified"] = True
                        technical_qualifiers.append(stock_record)

                    all_processed_stocks.append(stock_record)

                except Exception:
                    continue

        except Exception as e:
            print(f"❌ Batch {idx} failed: {e}")

    # Process qualified candidates fundamentals using parallel ThreadPool
    final_qualified = []
    if technical_qualifiers:
        print(f"\n🔍 {len(technical_qualifiers)} candidates passed technical filters out of full market. Evaluating Piotroski scores...")
        
        def process_candidate(candidate):
            f_score = get_piotroski_score_safe(candidate["symbol"])
            if f_score >= 5:
                cmp = candidate["cmp"]
                target_1 = round(cmp * 1.20, 2)
                target_2 = round(cmp * 1.35, 2)
                stop_loss = round(cmp * 0.90, 2)

                if supabase:
                    try:
                        db_entry = {
                            "ticker": candidate["clean_symbol"],
                            "entry_price": cmp,
                            "target_1": target_1,
                            "target_2": target_2,
                            "stop_loss": stop_loss,
                            "status": "HOLDING"
                        }
                        supabase.table("contra_portfolio").insert(db_entry).execute()
                    except Exception as db_e:
                        print(f"Database error logging {candidate['clean_symbol']}: {db_e}")
                
                candidate["f_score"] = f_score
                candidate["target_1"] = target_1
                candidate["target_2"] = target_2
                candidate["stop_loss"] = stop_loss
                final_qualified.append(candidate)
                print(f"✅ QUALIFIED & LOGGED: {candidate['clean_symbol']}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(process_candidate, technical_qualifiers)

    # Generate Dashboard Output
    generate_html_dashboard(all_processed_stocks, final_qualified)

    total_time = round(time.time() - start_time, 2)
    print(f"\n✨ Full market scan completed in {total_time} seconds across {len(all_processed_stocks)} stocks.")

# ==========================================
# 6. EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    run_optimized_scanner()
