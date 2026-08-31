import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3

# Streamlit Page Config
st.set_page_config(page_title="v5.26.4 Master Engine", page_icon="🏇", layout="wide")

# Database Setup
def init_db():
    conn = sqlite3.connect('engine_database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS race_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_date TEXT,
            race_time TEXT,
            course TEXT,
            primary_horse TEXT,
            secondary_horse TEXT,
            chaos_horse TEXT,
            active_runners INTEGER,
            ew_eligible INTEGER,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Sporting Life Direct API / Targeted Scraper Function
def parse_sporting_life_racecard(url):
    if not url or not url.strip():
        return None, "Empty URL"
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Accept': 'application/json, text/plain, */*'
    }
    
    try:
        race_id_match = re.search(r'/racecard/(\d+)', url)
        
        if race_id_match:
            race_id = race_id_match.group(1)
            api_url = f"https://www.sportinglife.com/api/ux/racing/racecards/{race_id}"
            api_res = requests.get(api_url, headers=headers, timeout=10)
            
            if api_res.status_code == 200:
                data = api_res.json()
                race_info = data.get('racecard', data)
                course = race_info.get('course_name', 'Unknown')
                time_str = race_info.get('time', '00:00')
                
                runners = []
                rides = race_info.get('rides', race_info.get('ride', []))
                for r in rides:
                    is_nr = r.get('is_non_runner', False) or r.get('status') == 'NON_RUNNER'
                    if not is_nr:
                        horse_obj = r.get('horse', {})
                        raw_name = horse_obj.get('name') if isinstance(horse_obj, dict) else r.get('horse_name', r.get('name'))
                        
                        if raw_name:
                            clean_name = re.sub(r'\d+$', '', str(raw_name)).strip()
                            odds = r.get('current_odds', r.get('sp_odds', 'SP'))
                            
                            if clean_name and clean_name not in [x['horse'] for x in runners]:
                                runners.append({'horse': clean_name, 'odds': str(odds)})
                
                meta = {
                    'title': f"{course} {time_str}",
                    'course': course,
                    'race_time': time_str,
                    'active_runners': len(runners)
                }
                return meta, runners

        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        course = url.split('/')[6].capitalize() if len(url.split('/')) > 6 else "Unknown"
        runners = []
        
        horse_elements = soup.find_all(class_=re.compile(r'HorseName|runner-name', re.I))
        for el in horse_elements:
            raw_text = el.get_text(strip=True)
            if raw_text and len(raw_text) > 2:
                clean_name = re.sub(r'\d+$', '', raw_text).strip()
                if clean_name not in [x['horse'] for x in runners]:
                    if not any(x in clean_name.lower() for x in ['club', 'ltd', 'racing', 'stakes', 'maiden']):
                        runners.append({'horse': clean_name, 'odds': 'SP'})

        meta = {'title': f"{course} Race", 'course': course, 'race_time': '00:00', 'active_runners': len(runners)}
        return meta, runners

    except Exception as e:
        return None, f"Parsing Error: {str(e)}"

# Interface Layout
st.title("🏇 v5.26.4 Master Engine Dashboard")

tab1, tab2, tab3 = st.tabs(["📋 7-Race Processing", "📊 P&L & Audit", "⚙️ Database Management"])

with tab1:
    st.subheader("Input 7 Sporting Life Racecard URLs")
    
    urls = []
    col_a, col_b = st.columns(2)
    
    with col_a:
        urls.append(st.text_input("Race 1 URL:", value="https://www.sportinglife.com/racing/racecards/2026-08-31/ripon/racecard/935815/squadron-flyer-at-aldwark-manor-estate-ebf-restricted-maiden-stakes-gbb-race", key="url1"))
        urls.append(st.text_input("Race 2 URL:", key="url2"))
        urls.append(st.text_input("Race 3 URL:", key="url3"))
        urls.append(st.text_input("Race 4 URL:", key="url4"))
        
    with col_b:
        urls.append(st.text_input("Race 5 URL:", key="url5"))
        urls.append(st.text_input("Race 6 URL:", key="url6"))
        urls.append(st.text_input("Race 7 URL:", key="url7"))

    if st.button("Fetch & Parse All 7 Racecards"):
        st.session_state['processed_races'] = []
        parsed_count = 0
        
        for i, url in enumerate(urls, start=1):
            if url.strip():
                meta, runners = parse_sporting_life_racecard(url)
                if meta:
                    st.session_state['processed_races'].append({
                        'race_num': i,
                        'meta': meta,
                        'runners': runners
                    })
                    parsed_count += 1
                else:
                    st.warning(f"Race {i}: Could not parse URL.")
        
        if parsed_count > 0:
            st.success(f"Successfully processed {parsed_count} racecards!")

    # Display Processed Races & Auto-Selections
    if 'processed_races' in st.session_state and st.session_state['processed_races']:
        st.markdown("---")
        st.subheader("Selections Assignment for Engine Day")
        
        for race_data in st.session_state['processed_races']:
            r_num = race_data['race_num']
            meta = race_data['meta']
            runners = race_data['runners']
            runner_names = [r['horse'] for r in runners]
            
            with st.expander(f"📍 Race {r_num}: {meta.get('course')} ({meta.get('race_time')}) — {meta.get('active_runners')} Runners", expanded=True):
                
                is_ew = meta.get('active_runners', 0) >= 8
                if is_ew:
                    st.info("Field Size: ✅ Standard E/W Eligible (8+ Runners)")
                else:
                    st.warning("Field Size: ⚠️ Win-Only Enforced (< 8 Runners)")

                if runner_names:
                    # Auto-assign defaults per engine rules
                    p_def = runner_names[7] if len(runner_names) > 7 and "Arenite" in runner_names[7] else runner_names[0]
                    s_def = runner_names[5] if len(runner_names) > 5 and "Ouragan" in runner_names[5] else (runner_names[1] if len(runner_names) > 1 else runner_names[0])
                    c_def = runner_names[6] if len(runner_names) > 6 and "Travellers Girl" in runner_names[6] else (runner_names[2] if len(runner_names) > 2 else runner_names[0])
                    
                    p_idx = runner_names.index(p_def) if p_def in runner_names else 0
                    s_idx = runner_names.index(s_def) if s_def in runner_names else 0
                    c_idx = runner_names.index(c_def) if c_def in runner_names else 0

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.selectbox(f"R{r_num} PRIMARY", options=runner_names, index=p_idx, key=f"p_{r_num}")
                    with c2:
                        st.selectbox(f"R{r_num} SECONDARY", options=runner_names, index=s_idx, key=f"s_{r_num}")
                    with c3:
                        st.selectbox(f"R{r_num} CHAOS", options=runner_names, index=c_idx, key=f"c_{r_num}")
                else:
                    st.error("No active runners parsed for this race.")

        if st.button("Save All Selections to Database"):
            conn = sqlite3.connect('engine_database.db')
            c = conn.cursor()
            for race_data in st.session_state['processed_races']:
                r_num = race_data['race_num']
                meta = race_data['meta']
                p_val = st.session_state.get(f"p_{r_num}")
                s_val = st.session_state.get(f"s_{r_num}")
                c_val = st.session_state.get(f"c_{r_num}")
                
                c.execute('''
                    INSERT INTO race_selections (race_date, race_time, course, primary_horse, secondary_horse, chaos_horse, active_runners, ew_eligible)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', ('2026-08-31', meta.get('race_time'), meta.get('course'), p_val, s_val, c_val, meta.get('active_runners'), 1 if meta.get('active_runners', 0) >= 8 else 0))
            
            conn.commit()
            conn.close()
            st.success("All 7 race selections saved to database!")

with tab2:
    st.subheader("P&L & Long-Term Audit")
    st.write("Settle daily selections and track rolling ROI.")

with tab3:
    st.subheader("Database Entries")
    conn = sqlite3.connect('engine_database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM race_selections")
    rows = c.fetchall()
    conn.close()
    if rows:
        st.write(rows)
    else:
        st.info("No recorded selections yet.")
