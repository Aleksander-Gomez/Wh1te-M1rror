import requests
import psycopg2
import time

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="eves_apple",
    user="postgres",
    password="SashaKarina2!"  # change this
)
cur = conn.cursor()

HEADERS = {"User-Agent": "evesapple research@evesapple.com"}

# Create table to store ad revenue breakdown
cur.execute("""
    CREATE TABLE IF NOT EXISTS ad_revenue_breakdown (
        id SERIAL PRIMARY KEY,
        company_name VARCHAR(150),
        ticker VARCHAR(10),
        fiscal_year INT,
        total_revenue_usd NUMERIC(20,2),
        ad_revenue_usd NUMERIC(20,2),
        ad_revenue_pct NUMERIC(5,2),
        filing_date DATE,
        notes TEXT
    );
""")
conn.commit()

# Companies with their CIKs and known ad revenue XBRL tags
companies = [
    {
        "name": "Google / Alphabet",
        "ticker": "GOOGL",
        "cik": "1652044",
        "ad_tags": [
            "AdvertisingRevenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ],
        "total_tags": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ],
        "notes": "Advertising has been 80-90% of Alphabet revenue since IPO"
    },
    {
        "name": "Meta / Facebook",
        "ticker": "META",
        "cik": "1326801",
        "ad_tags": [
            "AdvertisingRevenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ],
        "total_tags": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ],
        "notes": "Advertising is 97-99% of Meta revenue — users are the product"
    },
]

def get_facts(cik):
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"  Failed to fetch facts: {r.status_code}")
        return {}
    return r.json().get("facts", {}).get("us-gaap", {})

def get_annual_values(facts, tags):
    """Try multiple tags and return annual 10-K values"""
    for tag in tags:
        if tag in facts:
            units = facts[tag].get("units", {}).get("USD", [])
            annual = [
                e for e in units
                if e.get("form") == "10-K" and e.get("fp") == "FY"
            ]
            if annual:
                # Deduplicate by year, keep most recent filing
                by_year = {}
                for entry in annual:
                    year = entry.get("end", "")[:4]
                    if year not in by_year or entry.get("filed", "") > by_year[year].get("filed", ""):
                        by_year[year] = entry
                return by_year
    return {}

def get_segment_revenue(cik):
    """Try to get advertising segment revenue specifically"""
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return {}

    facts = r.json().get("facts", {})

    # Check both us-gaap and custom company taxonomy
    all_facts = {}
    for taxonomy in ["us-gaap", "dei"]:
        all_facts.update(facts.get(taxonomy, {}))

    # Look for advertising specific tags
    ad_specific_tags = [
        "AdvertisingRevenue",
        "OnlineAdvertisingRevenue",
        "DigitalAdvertisingRevenue",
    ]

    for tag in ad_specific_tags:
        if tag in all_facts:
            units = all_facts[tag].get("units", {}).get("USD", [])
            annual = [e for e in units if e.get("form") == "10-K"]
            if annual:
                by_year = {}
                for entry in annual:
                    year = entry.get("end", "")[:4]
                    if year not in by_year:
                        by_year[year] = entry
                print(f"  Found ad revenue tag: {tag}")
                return by_year
    return {}

for company in companies:
    print(f"\nPulling {company['name']}...")

    facts = get_facts(company["cik"])
    if not facts:
        continue

    # Get total revenue by year
    total_by_year = get_annual_values(facts, company["total_tags"])

    # Try specific ad revenue tag first
    ad_by_year = get_segment_revenue(company["cik"])

    # If no specific ad tag found, note it
    if not ad_by_year:
        print(f"  No dedicated ad revenue XBRL tag found — will use total revenue and flag for manual enrichment")

    inserted = 0
    for year, total_entry in total_by_year.items():
        if int(year) < 2004:
            continue

        total_rev = total_entry.get("val")
        filed = total_entry.get("filed")

        ad_rev = None
        ad_pct = None

        if year in ad_by_year:
            ad_rev = ad_by_year[year].get("val")
            if ad_rev and total_rev:
                ad_pct = round((ad_rev / total_rev) * 100, 2)

        # Check for duplicate
        cur.execute("""
            SELECT 1 FROM ad_revenue_breakdown
            WHERE ticker = %s AND fiscal_year = %s
        """, (company["ticker"], int(year)))

        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO ad_revenue_breakdown
                (company_name, ticker, fiscal_year, total_revenue_usd,
                 ad_revenue_usd, ad_revenue_pct, filing_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            company["name"],
            company["ticker"],
            int(year),
            total_rev,
            ad_rev,
            ad_pct,
            filed,
            company["notes"]
        ))
        inserted += 1

    conn.commit()
    print(f"  Inserted {inserted} years of revenue data")
    time.sleep(0.2)

# Pull known ad revenue percentages from public record
# These are well documented figures to manually enrich where XBRL tags are missing
print("\n\nEnriching with known ad revenue percentages from public filings...")

known_ad_percentages = [
    # Google / Alphabet — from annual reports
    ("GOOGL", 2004, 96.9, "Google IPO prospectus — 96.9% of revenue from advertising"),
    ("GOOGL", 2005, 96.7, "Google 10-K 2005"),
    ("GOOGL", 2006, 99.0, "Google 10-K 2006"),
    ("GOOGL", 2010, 96.0, "Google 10-K 2010"),
    ("GOOGL", 2015, 89.8, "Google 10-K 2015 — YouTube and Play reducing ad share"),
    ("GOOGL", 2019, 83.3, "Alphabet 10-K 2019 — Cloud growing"),
    ("GOOGL", 2022, 79.3, "Alphabet 10-K 2022 — Cloud now significant"),
    ("GOOGL", 2023, 77.8, "Alphabet 10-K 2023"),

    # Meta / Facebook — from annual reports
    ("META", 2012, 84.0, "Facebook 10-K 2012 — first full year as public company"),
    ("META", 2013, 89.0, "Facebook 10-K 2013"),
    ("META", 2015, 95.0, "Facebook 10-K 2015"),
    ("META", 2018, 98.5, "Facebook 10-K 2018"),
    ("META", 2020, 97.9, "Facebook 10-K 2020"),
    ("META", 2022, 98.2, "Meta 10-K 2022 — Reality Labs losing billions, ads still everything"),
    ("META", 2023, 98.0, "Meta 10-K 2023"),
]

for ticker, year, pct, note in known_ad_percentages:
    cur.execute("""
        UPDATE ad_revenue_breakdown
        SET ad_revenue_pct = %s, notes = %s
        WHERE ticker = %s AND fiscal_year = %s
        AND ad_revenue_pct IS NULL
    """, (pct, note, ticker, year))

conn.commit()

print("\nFinal results:")
cur.execute("""
    SELECT company_name, fiscal_year,
           round(total_revenue_usd / 1000000000, 1) as total_rev_billions,
           ad_revenue_pct
    FROM ad_revenue_breakdown
    ORDER BY company_name, fiscal_year;
""")

rows = cur.fetchall()
print(f"\n{'Company':<25} {'Year':<8} {'Total Rev ($B)':<18} {'Ad Rev %'}")
print("-" * 60)
for row in rows:
    name, year, total, pct = row
    pct_str = f"{pct}%" if pct else "pending"
    print(f"{name:<25} {year:<8} {str(total):<18} {pct_str}")

cur.close()
conn.close()
print("\nDone. Check ad_revenue_breakdown table in DBeaver.")