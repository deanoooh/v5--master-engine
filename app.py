import streamlit as st
import pandas as pd
import sqlite3
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Initialize SQLite Database
DB_FILE = "master_engine.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_date TEXT,
            race_time TEXT,
            course TEXT,
            distance TEXT,
            going TEXT,
            tier TEXT,
            horse_name TEXT,
            odds TEXT,
            decimal_odds REAL,
            stake_type TEXT,
            stake_amount REAL,
            result TEXT DEFAULT 'Pending',
            return_amount REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Odds Conversion Helper
def frac_to_dec(frac_str):
    try:
        if not frac_str or frac_str == 'N/A':
            return 2.0
        if 'f' in frac_str.lower():
            frac_str = re.sub(r'[a-zA-Z]', '', frac_str).strip()
        if '/' in frac_str:
            num, den = map(float, frac_str.split('/'))
            return (num / den) + 1.0
        return float(frac_str) + 1.0
    except:
        return 2.0

# v5.26.4 Automated Staking Logic Rule Engine
def get_staking_rule(tier, decimal_odds, active_runners):
    # Rule: < 8 runners forces Win-Only across all tiers
    if active_runners < 8:
        return "Win-Only", 1.00
    
    if tier == "PRIMARY":
        if decimal_odds < 3.00:  # < 2/1
            return "Win-Only", 1.00
        return "0.50 E/W", 1.00
    elif tier == "SECONDARY":
        if decimal_odds < 5.00:  # < 4/1
            return "Win-Only", 1.00
        return "0.50 E/W", 1.00
    elif tier == "CHAOS":
        if decimal_odds < 7.00:  # < 6/1
            return "Win-Only", 1.00
        return "0.50 E/W", 1.00
    return "0.50 E/W", 1.00

# Sporting Life Customized Scraper
def parse_sporting_life_racecard(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            return None, f"HTTP Error {response.status_code}: Unable to reach Sporting Life."
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Meta Info Extraction
        header_text = soup.find('h1')
        title = header_text.text.strip() if header_text else "Sporting Life Race"
        
        # Course / Time Parse
        time_match = re.search(r'(\d{2}:\d{2})', title)
        race_time = time_match.group(1) if time_match else "14:00"
        
        # Extract Runners
        runners = []
        runner_nodes = soup.select('div[class*="HorseName"], div[class*="runner"], tr[class*="runner"]')
        
        if not runner_nodes:
            # Fallback for alternative Sporting Life DOM layout
            runner_nodes = soup.find_all('section', class_=re.compile(r'Runner|runner'))

        # Fallback text parsing if class names change dynamically
        for card in soup.find_all(['div', 'li'], class_=re.compile(r'RunnerCard|runner-card|Selection')):
            name_elem = card.find(class_=re.compile(r'Name|horse-name'))
            odds_elem = card.find(class_=re.compile(r'Odds|price'))
            
            if name_elem:
                horse_name = name_elem.text.strip()
                odds = odds_elem.text.strip() if odds_elem else "SP"
                is_nr = "non-runner" in card.text.lower() or "withdrawn" in card.text.lower()
                
                if not is_nr:
                    runners.append({'horse': horse_name, 'odds': odds})

        # Generic DOM Fallback if specific classes match empty
        if not runners:
            rows = soup.find_all('tr')
            for row in rows:
                text = row.text.strip()
                if text and not ("non-runner" in text.lower()):
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    if len(lines) >= 2:
                        runners.append({'horse': lines[0], 'odds': lines[-1]})

        metadata = {
            'title': title,
            'race_time': race_time,
            'active_runners': len(runners) if runners else 8
        }
        
        return metadata, runners
    except Exception as e:
        return None, f"Parsing Error: {str(e)}"

# UI Layout
st.set_page_config(page_title="v5.26.4 Master Engine", layout="wide")
st.title("🏇 v5.26.4 Master Engine Dashboard")

tabs = st.tabs(["📥 Racecard Processing", "📊 P&L & Long-Term Audit", "⚙️ Database Management"])

with tabs[0]:
    st.header("Sporting Life Racecard Scraper")
    
    race_url = st.text_input("Paste Sporting Life Racecard URL:", placeholder="https://www.sportinglife.com/racing/racecards/...")
    
    if race_url and st.button("Fetch & Parse Racecard", type="primary"):
        with st.spinner("Scraping Sporting Life data..."):
            meta, runners = parse_sporting_life_racecard(race_url)
            
            if meta:
                st.session_state['parsed_meta'] = meta
                st.session_state['parsed_runners'] = runners
                st.success(f"Parsed {len(runners)} active runners successfully!")
            else:
                st.error(runners)

    if 'parsed_meta' in st.session_state:
        st.markdown("---")
        st.subheader("Automated Staking & Selections Engine")
        
        meta = st.session_state['parsed_meta']
        runners = st.session_state['parsed_runners']
        
        col1, col2, col3 = st.columns(3)
        with col1:
            race_date = st.date_input("Race Date", datetime.now())
            race_time = st.text_input("Race Time", meta.get('race_time', '14:00'))
            course = st.text_input("Course", meta.get('title', 'Goodwood').split()[0])
        with col2:
            going = st.text_input("Going", "Good")
            distance = st.text_input("Distance", "1m")
            active_runners = st.number_input("Active Runners (Excl. NR)", min_value=1, max_value=40, value=meta.get('active_runners', 8))
        with col3:
            st.info(f"Field Size Mode: {'⚠️ Win-Only (< 8)' if active_runners < 8 else '✅ Standard E/W Eligible'}")

        st.markdown("---")
        st.markdown("### Selections Assignment")
        
        runner_names = [r['horse'] for r in runners] if runners else []
        runner_dict = {r['horse']: r['odds'] for r in runners} if runners else {}

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### PRIMARY Tier")
            p_name = st.selectbox("Select Primary Horse", [""] + runner_names, key="p_sel")
            p_odds_default = runner_dict.get(p_name, "2/1") if p_name else ""
            p_odds = st.text_input("Primary Odds", value=p_odds_default, key="p_odds")
            if p_name and p_odds:
                p_dec = frac_to_dec(p_odds)
                p_rule, p_stake = get_staking_rule("PRIMARY", p_dec, active_runners)
                st.caption(f"Rule Applied: **{p_rule}** | Stake: **£{p_stake:.2f}**")
                
        with c2:
            st.markdown("#### SECONDARY Tier")
            s_name = st.selectbox("Select Secondary Horse", [""] + runner_names, key="s_sel")
            s_odds_default = runner_dict.get(s_name, "4/1") if s_name else ""
            s_odds = st.text_input("Secondary Odds", value=s_odds_default, key="s_odds")
            if s_name and s_odds:
                s_dec = frac_to_dec(s_odds)
                s_rule, s_stake = get_staking_rule("SECONDARY", s_dec, active_runners)
                st.caption(f"Rule Applied: **{s_rule}** | Stake: **£{s_stake:.2f}**")

        with c3:
            st.markdown("#### CHAOS Tier")
            ch_name = st.selectbox("Select Chaos Horse", [""] + runner_names, key="ch_sel")
            ch_odds_default = runner_dict.get(ch_name, "8/1") if ch_name else ""
            ch_odds = st.text_input("Chaos Odds", value=ch_odds_default, key="ch_odds")
            if ch_name and ch_odds:
                ch_dec = frac_to_dec(ch_odds)
                ch_rule, ch_stake = get_staking_rule("CHAOS", ch_dec, active_runners)
                st.caption(f"Rule Applied: **{ch_rule}** | Stake: **£{ch_stake:.2f}**")

        if st.button("Save Selections to P&L Database", type="primary"):
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            entries = [
                ("PRIMARY", p_name, p_odds),
                ("SECONDARY", s_name, s_odds),
                ("CHAOS", ch_name, ch_odds)
            ]
            
            for tier, name, odds in entries:
                if name and odds:
                    dec = frac_to_dec(odds)
                    rule, stake = get_staking_rule(tier, dec, active_runners)
                    c.execute('''
                        INSERT INTO selections 
                        (race_date, race_time, course, distance, going, tier, horse_name, odds, decimal_odds, stake_type, stake_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (str(race_date), race_time, course, distance, going, tier, name, odds, dec, rule, stake))
            
            conn.commit()
            conn.close()
            st.success("Selections successfully logged to P&L database!")

with tabs[1]:
    st.header("P&L & Long-Term Performance Audit")
    
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM selections", conn)
    conn.close()
    
    if not df.empty:
        st.subheader("Pending Selections Settlement")
        pending_df = df[df['result'] == 'Pending']
        
        if not pending_df.empty:
            for idx, row in pending_df.iterrows():
                col_a, col_b, col_c = st.columns([3, 2, 2])
                with col_a:
                    st.write(f"**{row['race_date']} {row['race_time']} {row['course']}** - {row['tier']}: **{row['horse_name']}** ({row['odds']})")
                with col_b:
                    res = st.selectbox("Result", ["Pending", "Win ✅", "Place 🅿️", "Unplaced ❌", "Non-Runner 🚫"], key=f"res_{row['id']}")
                with col_c:
                    ret = st.number_input("Return (£)", min_value=0.0, step=0.1, key=f"ret_{row['id']}")
                    if st.button("Settle", key=f"btn_{row['id']}"):
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE selections SET result = ?, return_amount = ? WHERE id = ?", (res, ret, row['id']))
                        conn.commit()
                        conn.close()
                        st.rerun()
        else:
            st.info("No pending selections to settle.")
        
        st.markdown("---")
        st.subheader("Overall Financial Metrics")
        
        settled_df = df[df['result'] != 'Pending'].copy()
        if not settled_df.empty:
            total_outlay = settled_df['stake_amount'].sum()
            total_returns = settled_df['return_amount'].sum()
            net_pnl = total_returns - total_outlay
            roi = (net_pnl / total_outlay * 100) if total_outlay > 0 else 0.0
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Outlay", f"£{total_outlay:.2f}")
            m2.metric("Total Returns", f"£{total_returns:.2f}")
            m3.metric("Net Profit/Loss", f"£{net_pnl:.2f}", delta=f"{net_pnl:.2f}")
            m4.metric("ROI %", f"{roi:.2f}%", delta=f"{roi:.2f}%")
            
            st.markdown("---")
            st.subheader("Tier Breakdown")
            tier_df = settled_df.groupby('tier').agg(
                Bets=('id', 'count'),
                Outlay=('stake_amount', 'sum'),
                Returns=('return_amount', 'sum')
            ).reset_index()
            tier_df['Net P&L (£)'] = tier_df['Returns'] - tier_df['Outlay']
            tier_df['ROI %'] = (tier_df['Net P&L (£)'] / tier_df['Outlay']) * 100
            st.dataframe(tier_df.style.format({'Outlay': '£{:.2f}', 'Returns': '£{:.2f}', 'Net P&L (£)': '£{:.2f}', 'ROI %': '{:.2f}%'}))
            
            st.markdown("---")
            st.subheader("Daily Rolling Audit")
            daily_df = settled_df.groupby('race_date').agg(
                Outlay=('stake_amount', 'sum'),
                Returns=('return_amount', 'sum')
            ).reset_index()
            daily_df['Daily Net (£)'] = daily_df['Returns'] - daily_df['Outlay']
            daily_df['Cumulative P&L (£)'] = daily_df['Daily Net (£)'].cumsum()
            st.dataframe(daily_df.style.format({'Outlay': '£{:.2f}', 'Returns': '£{:.2f}', 'Daily Net (£)': '£{:.2f}', 'Cumulative P&L (£)': '£{:.2f}'}))
    else:
        st.info("No selections stored in database yet.")

with tabs[2]:
    st.header("Database Records")
    conn = sqlite3.connect(DB_FILE)
    full_df = pd.read_sql_query("SELECT * FROM selections ORDER BY id DESC", conn)
    conn.close()
    st.dataframe(full_df)
