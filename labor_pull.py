import pandas as pd
import psycopg2
import time
from datetime import datetime

# --- DB CONNECTION ---

# --- CREATE TABLE IF NOT EXISTS ---
cur.execute('''
    CREATE TABLE IF NOT EXISTS labor_market_data (
        id SERIAL PRIMARY KEY,
        occupation VARCHAR(255),
        industry VARCHAR(255),
        employment_count INT,
        wage_data NUMERIC(15,2),
        skill_level VARCHAR(50),
        data_year INT
    );
''')
conn.commit()

# --- EXTRACT ---
print('Extracting BLS data...')
try:
    df = pd.read_csv('https://www.bls.gov/oes/data/marc2021.csv')
except Exception as e:
    print(f"Error downloading CSV: {str(e)}")
    df = pd.DataFrame()

# --- TRANSFORM ---
print('Transforming data...')
try:
    # Map SOC codes to skill levels (example logic)
    skill_mapping = {
        'SOC Code 11-1021.00': 'High Skill',
        'SOC Code 13-1021.00': 'Middle Skill',
        'SOC Code 45-3011.00': 'Low Skill'
    }

    df['skill_level'] = df['SOC Code'].map(skill_mapping).fillna('Unknown')
    df = df[[' Occupation', 'Industry', 'Total', 'Wage', 'SOC Code']], df.rename(columns={
                ' Occupation': 'occupation',
                'Industry': 'industry',
                'Total': 'employment_count',
                'Wage': 'wage_data',
                'SOC Code': 'skill_level'
            })
    df['data_year'] = 2021  # Set year based on dataset
except Exception as e:
    print(f"Transformation error: {str(e)}")
    df = pd.DataFrame()

# --- LOAD ---
print('Loading data...')
try:
    # Check for duplicates
    cur.execute("""
        SELECT 1 FROM labor_market_data 
        WHERE occupation = %s AND industry = %s 
        AND data_year = %s
    """, (df['occupation'][0], df['industry'][0], df['data_year'][0]))
    if cur.fetchone():
        print("Skipping duplicates...")
    else:
        df.to_sql('labor_market_data', conn, if_exists='append', index=False)
    conn.commit()
except Exception as e:
    print(f"Load error: {str(e)}")
    conn.rollback()
finally:
    cur.close()
    conn.close()
    print('ETL completed at', datetime.now())
