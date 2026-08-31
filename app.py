import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
from datetime import datetime

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

# Horse Name Cleaner
def clean_horse_name(raw_name):
    if not raw_name:
        return ""
    name = str(raw_name).strip()
    
    country_suffix = ""
    country_match = re.search(r'\s*\([A-Z]{2,3}\)$', name)
    if country_match:
        country_suffix = country_match.group(0)
        name = name[:country_match.start()].strip()
        
    name = re.sub(r'[pvhbetcPVHBETC]?\d+$', '', name).strip()
    name = re.sub(r'[\s\-\(]+[pvhbetcPVHBETC]\)?$', '', name).strip()
    
    return name + country_suffix

# Sporting Life Scraper Function
def parse_sporting_life_racecard(url):
    if not url or not url.strip():
        return None, "Empty URL"
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.sportinglife.com/'
    }
    
    try:
        time_str = ""
        course = "Unknown"
        
        # 1. Parse time from URL patterns (e.g. /1645/ or /16-45/ or /16:45/)
        url_time = re.search(r'/([0-2][0-9])[:\-]?([0-5][0-9])(?:/|$)', url)
        if url_time:
            time_str = f"{url_time.group(1)}:{url_time.group(2)}"

        race_id_match = re.search(r'/racecard/(\d+)', url)
        
        if race_id_match:
            race_id = race_id_match.group(1)
            api_url = f"https://www.sportinglife.com/api/ux/racing/racecards/{race_id}"
            api_res = requests.get(api_url, headers=headers, timeout=10)
            
            if api_res.status_code == 200:
                data = api_res.json()
                race_info = data.get('racecard', data)
                if isinstance(race_info, dict) and 'race' in race_info:
                    race_info = race_info['race']
                    
                course = race_info.get('course_name', race_info.get('meeting_name', 'Unknown'))
                
                # 2. Convert API time fields if URL check was empty
                if not time_str:
                    # Check for ISO date string e.g. "2026-08-31T16:45:00.000Z"
                    date_val = race_info.get('date') or race_info.get('start_date') or race_info.get('race_date')
                    if date_val:
                        t_match = re.search(r'T(\d{2}:\d{2})', str(date_val))
                        if t_match:
                            time_str = t_match.group(1)

                    # Check for UNIX timestamp integer e.g. 1725119100
                    if not time_str:
                        timestamp = race_info.get('time_stamp') or race_info.get('timestamp') or race_info.get('time')
                        if isinstance(timestamp, (int, float)) and timestamp > 1000000000:
                            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M')

                runners = []
                rides = race_info.get('rides', race_info.get('ride', []))
                for r in rides:
                    is_nr = r.get('is_non_runner', False) or r.get('status') == 'NON_RUNNER'
                    if not is_nr:
                        horse_obj = r.get('horse', {})
                        raw_name = horse_obj.get('name') if isinstance(horse_obj, dict) else r.get('horse_name', r.get('name'))
                        
                        if raw_name:
                            clean_name = clean_horse_name(raw_name)
                            odds = r.get('current_odds', r.get('sp_odds', 'SP'))
                            if not odds or odds == '':
                                odds = 'SP'
                            
                            if clean_name and clean_name not in [x['horse'] for x in runners]:
                                runners.append({'horse': clean_name, 'odds': str(odds)})
                
                if not time_str:
                    time_str = "14:00"

                meta = {
                    'title': f"{course} {time_str}",
                    'course': course,
                    'race_time': time_str,
                    'active_runners': len(runners)
                }
                return meta, runners

        # 3. HTML Scraping Fallback
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        parts = url.split('/')
        for idx, p in enumerate(parts):
            if p == 'racecards' and idx + 2 < len(parts):
                course = parts[idx + 2].capitalize()
                break
        
        if not time_str:
            page_title = soup.title.string if soup.title else ""
            time_match = re.search(r'\b([0-2]?[0-9]:[0-5][0-9])\b', page_title)
            if time_match:
                time_str = time_match.group(1)
            else:
                time_str = "14:00"

        runners = []
        horse_elements = soup.find_all(class_=re.compile(r'HorseName|runner-name', re.I))
        for el in horse_elements:
            raw_text = el.get_text(strip=True)
            if raw_text and len(raw_text) > 2:
                clean_name = clean_horse_name(raw_text)
                if clean_name not in [x['horse'] for x in runners]:
                    if not any(x in clean_name.lower() for x in ['club', 'ltd', 'racing', 'stakes', 'maiden']):
                        runners.append({'horse': clean_name, 'odds': 'SP'})

        meta = {'title': f"{course} {time_str}", 'course': course, 'race_time': time_str, 'active_runners': len(runners)}
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
        urls.append(st.text_input("Race 1 URL:", key="url1"))
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
            
            # Format runner choices with odds + Add NO BET option
            formatted_choices = ["🔴 NO BET"] + [f"{r['horse']} ({r['odds']})" for r in runners]
            
            with st.expander(f"📍 Race {r_num}: {meta.get('course')} — {meta.get('active_runners')} Runners", expanded=True):
                
                # Time Input Field for full manual control / quick adjustment
                col_t1, col_t2 = st.columns([1, 2])
                with col_t1:
                    race_time_val = st.text_input(f"R{r_num} Time", value=meta.get('race_time', '14:00'), key=f"time_{r_num}")
                with col_t2:
                    is_ew = meta.get('active_runners', 0) >= 8
                    if is_ew:
                        st.info("Field Size: ✅ Standard E/W Eligible (8+ Runners)")
                    else:
                        st.warning("Field Size: ⚠️ Win-Only Enforced (< 8 Runners)")

                if runners:
                    p_idx = 1 if len(formatted_choices) > 1 else 0
                    s_idx = 2 if len(formatted_choices) > 2 else 0
                    c_idx = 3 if len(formatted_choices) > 3 else 0

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.selectbox(f"R{r_num} PRIMARY", options=formatted_choices, index=p_idx, key=f"p_{r_num}")
                    with c2:
                        st.selectbox(f"R{r_num} SECONDARY", options=formatted_choices, index=s_idx, key=f"s_{r_num}")
                    with c3:
                        st.selectbox(f"R{r_num} CHAOS", options=formatted_choices, index=c_idx, key=f"c_{r_num}")
                else:
                    st.error("No active runners parsed for this race.")

        if st.button("Save All Selections to Database"):
            conn = sqlite3.connect('engine_database.db')
            c = conn.cursor()
            for race_data in st.session_state['processed_races']:
                r_num = race_data['race_num']
                meta = race_data['meta']
                r_time = st.session_state.get(f"time_{r_num}", meta.get('race_time'))
                p_val = st.session_state.get(f"p_{r_num}")
                s_val = st.session_state.get(f"s_{r_num}")
                c_val = st.session_state.get(f"c_{r_num}")
                
                c.execute('''
                    INSERT INTO race_selections (race_date, race_time, course, primary_horse, secondary_horse, chaos_horse, active_runners, ew_eligible)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', ('2026-08-31', r_time, meta.get('course'), p_val, s_val, c_val, meta.get('active_runners'), 1 if meta.get('active_runners', 0) >= 8 else 0))
            
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
