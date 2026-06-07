import requests
import psycopg2
import time

# --- DB CONNECTION ---


# --- TARGET COMPANIES (name, ticker, CIK) ---
companies = [
    ("Apple",     "AAPL",  "320193"),
    ("Microsoft", "MSFT",  "789019"),
    ("Google",    "GOOGL", "1652044"),
    ("Amazon",    "AMZN",  "1018724"),
    ("Meta",      "META",  "1326801"),
    ("Netflix",   "NFLX",  "1065280"),
    ("Salesforce","CRM",   "1108524"),
    ("AT&T",      "T",     "732717"),
    ("Verizon",   "VZ",    "732712"),
    ("NVIDIA",    "NVDA",  "1045810"),
]

HEADERS = {"User-Agent": "evesapple research@evesapple.com"}

def get_revenue_history(cik):
    """Pull annual revenue from EDGAR XBRL API"""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"  Failed: {r.status_code}")
        return []
    
    facts = r.json().get("facts", {}).get("us-gaap", {})
    
    # Revenue can live under different tags depending on company
    revenue_tags = [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ]
    
    for tag in revenue_tags:
        if tag in facts:
            units = facts[tag].get("units", {}).get("USD", [])
            # Filter for annual (10-K) filings only
            annual = [
                entry for entry in units
                if entry.get("form") == "10-K" and entry.get("fp") == "FY"
            ]
            if annual:
                return annual
    return []

def get_company_info(cik):
    """Pull company metadata from EDGAR submissions"""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return {}
    return r.json()

# --- CREATE REVENUE HISTORY TABLE IF NOT EXISTS ---
cur.execute("""
    CREATE TABLE IF NOT EXISTS revenue_history (
        id SERIAL PRIMARY KEY,
        company_name VARCHAR(150),
        ticker VARCHAR(10),
        cik VARCHAR(20),
        fiscal_year INT,
        revenue_usd NUMERIC(20,2),
        filing_date DATE,
        form_type VARCHAR(10)
    );
""")
conn.commit()

# --- PULL AND INSERT ---
for name, ticker, cik in companies:
    print(f"\nPulling {name} ({ticker})...")
    
    revenues = get_revenue_history(cik)
    
    if not revenues:
        print(f"  No revenue data found for {name}")
        continue
    
    inserted = 0
    for entry in revenues:
        year = entry.get("end", "")[:4]  # e.g. "2023-09-30" -> "2023"
        revenue = entry.get("val")
        filed = entry.get("filed")
        
        if not year or not revenue:
            continue
        
        # Avoid duplicates
        cur.execute("""
            SELECT 1 FROM revenue_history 
            WHERE ticker = %s AND fiscal_year = %s
        """, (ticker, int(year)))
        
        if cur.fetchone():
            continue
            
        cur.execute("""
            INSERT INTO revenue_history 
                (company_name, ticker, cik, fiscal_year, revenue_usd, filing_date, form_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, ticker, cik, int(year), revenue, filed, "10-K"))
        inserted += 1
    
    conn.commit()
    print(f"  Inserted {inserted} years of revenue data")
    time.sleep(0.15)  # respect EDGAR rate limit

cur.close()
conn.close()
print("\nDone. Check your revenue_history table in DBeaver.")
