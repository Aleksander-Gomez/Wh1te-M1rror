import psycopg2
import yfinance as yf
import time



tickers = [
    ("AAPL",  "Apple"),
    ("MSFT",  "Microsoft"),
    ("GOOGL", "Google"),
    ("AMZN",  "Amazon"),
    ("META",  "Meta"),
    ("NFLX",  "Netflix"),
    ("CRM",   "Salesforce"),
    ("T",     "AT&T"),
    ("VZ",    "Verizon"),
    ("NVDA",  "NVIDIA"),
    ("ADBE",  "Adobe"),
    ("SPOT",  "Spotify"),
]

print("Pulling market cap via yfinance...\n")

for ticker, name in tickers:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        market_cap = info.get("marketCap")

        if market_cap:
            billions = round(market_cap / 1_000_000_000, 2)
            print(f"  {ticker} ({name}): ${billions}B")

            cur.execute("""
                UPDATE company
                SET market_cap_usd = %s
                WHERE ticker = %s
            """, (market_cap, ticker))
            conn.commit()
        else:
            print(f"  {ticker}: marketCap field empty in response")

    except Exception as e:
        print(f"  {ticker}: error — {e}")

    time.sleep(0.3)

print("\nDone. Check company table in DBeaver.")
cur.close()
conn.close()
