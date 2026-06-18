import streamlit as st
import arrow
import re
import unicodedata
import requests
from ics import Calendar

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Děti (Online Google Kalendář)", layout="wide")

st.title("👨‍👩‍👦‍👦 Jáchymek a Vilémek")

# --- NASTAVENÍ KOEFICIENTŮ ---
WEIGHT_WEEKEND = 1.5
WEIGHT_WEEKDAY = 1.0

# --- NAČTENÍ URL Z TAJNÝCH PROMĚNNÝCH ---
try:
    CALENDAR_URL = st.secrets["CALENDAR_URL"]
except Exception:
    st.error("Nenalezen klíč CALENDAR_URL v Secrets.")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("Nastavení")
    if st.button("🔄 Obnovit data z kalendáře"):
        st.cache_data.clear()
    st.divider()
    year_select = st.number_input("Rok", value=2026, step=1)
    st.divider()
    
    all_months = {
        "Leden": 1, "Únor": 2, "Březen": 3, "Duben": 4, 
        "Květen": 5, "Červen": 6, "Červenec": 7, "Srpen": 8,
        "Září": 9, "Říjen": 10, "Listopad": 11, "Prosinec": 12
    }
    
    selected_month_names = []
    for month_name in all_months.keys():
        if f"cb_{month_name}" not in st.session_state:
            st.session_state[f"cb_{month_name}"] = True
        if st.checkbox(month_name, key=f"cb_{month_name}"):
            selected_month_names.append(month_name)

    months_config = [(name, num) for name, num in all_months.items() if name in selected_month_names]

# --- POMOCNÉ FUNKCE ---

def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize('NFD', text)
    result = "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])
    return result.lower()

def extract_count(text):
    """Hledá vzor typu '3x' nebo '3 x' v názvu události."""
    match = re.search(r"(\d+)\s*x\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else 1

@st.cache_data(ttl=900)
def get_calendar_text(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except Exception:
        return None

# --- HLAVNÍ LOGIKA ---

if not months_config:
    st.warning("Vyberte prosím alespoň jeden měsíc.")
    st.stop()

ics_text = get_calendar_text(CALENDAR_URL)
if not ics_text:
    st.error("Nepodařilo se stáhnout kalendář.")
    st.stop()

c = Calendar(ics_text)

# Regexy pro třídění
pattern_p = re.compile(r"\bp\.?\s+ma\s+deti")
pattern_v = re.compile(r"\bv\.?\s+ma\s+deti")
pattern_p_lekar = re.compile(r"\bp(etr)?\.?\s*(u\s+)?(lekar|doktor|zubar)")
pattern_v_lekar = re.compile(r"\bv(eronika|erca)?\.?\s*(u\s+)?(lekar|doktor|zubar)")
pattern_p_skola = re.compile(r"\bp(etr)?\.?\s*(skol|vyuka)")
pattern_v_skola = re.compile(r"\bv(eronika|erca)?\.?\s*(skol|vyuka)")

events_p, events_v = [], []
events_p_lekar, events_v_lekar = [], []
events_p_skola, events_v_skola = [], []

for event in c.events:
    clean = normalize_text(event.name)
    if pattern_p.search(clean): events_p.append(event)
    elif pattern_v.search(clean): events_v.append(event)
    
    if pattern_p_lekar.search(clean): events_p_lekar.append(event)
    if pattern_v_lekar.search(clean): events_v_lekar.append(event)
    if pattern_p_skola.search(clean): events_p_skola.append(event)
    if pattern_v_skola.search(clean): events_v_skola.append(event)

results = []
total_p_weight, total_v_weight = 0.0, 0.0
total_p_weekends, total_v_weekends = 0.0, 0.0
t_p_lekar, t_v_lekar, t_p_skola, t_v_skola = 0, 0, 0, 0

for m_name, m_month in months_config:
    m_start = arrow.get(year_select, m_month, 1)
    m_end = m_start.shift(months=1)

    # Statistika lékař/škola s násobičem
    t_p_lekar += sum(extract_count(e.name) for e in events_p_lekar if m_start <= e.begin < m_end)
    t_v_lekar += sum(extract_count(e.name) for e in events_v_lekar if m_start <= e.begin < m_end)
    t_p_skola += sum(extract_count(e.name) for e in events_p_skola if m_start <= e.begin < m_end)
    t_v_skola += sum(extract_count(e.name) for e in events_v_skola if m_start <= e.begin < m_end)

    # Výpočet péče o děti
    p_w, v_w = 0.0, 0.0
    p_we, v_we = 0.0, 0.0
    curr = m_start
    while curr < m_end:
        is_we = curr.weekday() >= 5
        weight = WEIGHT_WEEKEND if is_we else WEIGHT_WEEKDAY
        d_end = curr.shift(days=1)
        
        p_act = any(e.begin < d_end and e.end > curr for e in events_p)
        v_act = any(e.begin < d_end and e.end > curr for e in events_v)
        
        if p_act and v_act:
            p_w += weight * 0.5; v_w += weight * 0.5
            if is_we: p_we += 0.5; v_we += 0.5
        elif p_act:
            p_w += weight
            if is_we: p_we += 1.0
        elif v_act:
            v_w += weight
            if is_we: v_we += 1.0
        curr = curr.shift(days=1)

    total_p_weight += p_w; total_v_weight += v_w
    total_p_weekends += p_we; total_v_weekends += v_we
    results.append({"Měsíc": m_name, "Petr": round(p_w, 2), "Veronika": round(v_w, 2)})

# --- VÝSTUP ---
st.subheader(f"Přehled pro rok {year_select}")
st.dataframe(results, use_container_width=True)

st.markdown("### Celkové souhrny")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Petr (celkem)", f"{total_p_weight:.2f}")
c2.metric("Veronika (celkem)", f"{total_v_weight:.2f}")
c3.metric("Víkendy Petr", f"{total_p_weekends:.1f}")
c4.metric("Víkendy Veronika", f"{total_v_weekends:.1f}")

st.markdown("### Lékaři a škola")
l1, l2, s1, s2 = st.columns(4)
l1.metric("Lékař Petr", f"{t_p_lekar}×")
l2.metric("Lékař Veronika", f"{t_v_lekar}×")
s1.metric("Škola Petr", f"{t_p_skola}×")
s2.metric("Škola Veronika", f"{t_v_skola}×")
