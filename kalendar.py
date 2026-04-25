import streamlit as st
import arrow
import re
import unicodedata
import requests
from ics import Calendar

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Děti (Online Google Kalendář)", layout="wide")

st.title("👨‍👩‍👦‍👦 Jáchymek a Vilémek")

# --- NASTAVENÍ KOEFICIENTŮ (NAPEVNO) ---
WEIGHT_WEEKEND = 1.5
WEIGHT_WEEKDAY = 1.0

# --- NAČTENÍ URL Z TAJNÝCH PROMĚNNÝCH (SECRETS) ---
try:
    CALENDAR_URL = st.secrets["CALENDAR_URL"]
except Exception:
    st.error("Nenalezen klíč CALENDAR_URL v Secrets. Prosím nastavte jej v administraci Streamlit Cloud.")
    st.stop()

# --- SIDEBAR (NASTAVENÍ) ---
with st.sidebar:
    st.header("Nastavení")
    
    if st.button("🔄 Obnovit data z kalendáře"):
        st.cache_data.clear()

    st.divider()
    
    year_select = st.number_input("Rok", value=2026, step=1)
    
    st.divider()
    
    st.write("**Výběr měsíců:**")
    all_months = {
        "Leden": 1, "Únor": 2, "Březen": 3, "Duben": 4, 
        "Květen": 5, "Červen": 6, "Červenec": 7, "Srpen": 8,
        "Září": 9, "Říjen": 10, "Listopad": 11, "Prosinec": 12
    }

    c_all, c_none = st.columns(2)
    if c_all.button("Vybrat vše"):
        for m in all_months.keys():
            st.session_state[f"cb_{m}"] = True
    if c_none.button("Zrušit vše"):
        for m in all_months.keys():
            st.session_state[f"cb_{m}"] = False

    selected_month_names = []
    cols = st.columns(3)
    for i, month_name in enumerate(all_months.keys()):
        with cols[i % 3]:
            if f"cb_{month_name}" not in st.session_state:
                st.session_state[f"cb_{month_name}"] = True
            
            if st.checkbox(month_name, key=f"cb_{month_name}"):
                selected_month_names.append(month_name)

    months_config = []
    for name, num in all_months.items():
        if name in selected_month_names:
            months_config.append((name, num))

# --- POMOCNÉ FUNKCE ---

def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize('NFD', text)
    result = "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])
    return result.lower()

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
    st.warning("Vyberte prosím alespoň jeden měsíc v levém panelu.")
    st.stop()

with st.spinner('Stahuji aktuální kalendář z Google...'):
    ics_text = get_calendar_text(CALENDAR_URL)

if ics_text is None:
    st.error("Nepodařilo se stáhnout kalendář. Zkontrolujte URL adresu v Secrets.")
    st.stop()

try:
    c = Calendar(ics_text)
except Exception as e:
    st.error(f"Chyba při parsování kalendáře: {e}")
    st.stop()

# Filtrace událostí (P vs V) pomocí regulárních výrazů
pattern_p = re.compile(r"\bp\.?\s+ma\s+deti")
pattern_v = re.compile(r"\bv\.?\s+ma\s+deti")

# Nové vzory pro lékaře a školu (pokrývá varianty jako "p. u lekare", "p u doktora", "p. skola" atd.)
pattern_p_lekar = re.compile(r"\bp(etr)?\.?\s*(u\s+)?(lekar|doktor|zubar)")
pattern_v_lekar = re.compile(r"\bv(eronika|erca)?\.?\s*(u\s+)?(lekar|doktor|zubar)")
pattern_p_skola = re.compile(r"\bp(etr)?\.?\s*(skol|vyuka)")
pattern_v_skola = re.compile(r"\bv(eronika|erca)?\.?\s*(skol|vyuka)")

events_p_all = []
events_v_all = []
events_p_lekar_all = []
events_v_lekar_all = []
events_p_skola_all = []
events_v_skola_all = []

for event in c.events:
    clean = normalize_text(event.name)
    
    # Rozdělení dětí
    if pattern_p.search(clean):
        events_p_all.append(event)
    elif pattern_v.search(clean):
        events_v_all.append(event)
        
    # Nezávislé vyhledávání lékaře a školy (bez elif, aby se nezablokovalo při nečekaných kombinacích)
    if pattern_p_lekar.search(clean): events_p_lekar_all.append(event)
    if pattern_v_lekar.search(clean): events_v_lekar_all.append(event)
    if pattern_p_skola.search(clean): events_p_skola_all.append(event)
    if pattern_v_skola.search(clean): events_v_skola_all.append(event)

# Výpočet po měsících a dnech
results = []
total_p_weight = 0.0
total_v_weight = 0.0
total_p_weekends = 0.0
total_v_weekends = 0.0

# Počítadla pro nové statistiky
total_p_lekar = 0
total_v_lekar = 0
total_p_skola = 0
total_v_skola = 0

progress_bar = st.progress(0)
total_steps = len(months_config)

for idx, (m_name, m_month) in enumerate(months_config):
    m_start = arrow.get(year_select, m_month, 1)
    m_end = m_start.shift(months=1)

    # Přičtení počtu událostí pro daný měsíc (vyhodnocuje se jen podle začátku události)
    total_p_lekar += sum(1 for e in events_p_lekar_all if m_start <= e.begin < m_end)
    total_v_lekar += sum(1 for e in events_v_lekar_all if m_start <= e.begin < m_end)
    total_p_skola += sum(1 for e in events_p_skola_all if m_start <= e.begin < m_end)
    total_v_skola += sum(1 for e in events_v_skola_all if m_start <= e.begin < m_end)

    p_w_sum = 0.0
    v_w_sum = 0.0
    p_we_count = 0.0
    v_we_count = 0.0

    current_day = m_start
    while current_day < m_end:
        day_start = current_day.floor('day')
        day_end = current_day.ceil('day')
        
        is_weekend = current_day.weekday() >= 5
        day_weight = WEIGHT_WEEKEND if is_weekend else WEIGHT_WEEKDAY
        
        p_active = False
        v_active = False
        
        for e in events_p_all:
            if e.begin < day_end and e.end > day_start:
                p_active = True
                break
        
        for e in events_v_all:
            if e.begin < day_end and e.end > day_start:
                v_active = True
                break
        
        if p_active and v_active:
            p_w_sum += day_weight * 0.5
            v_w_sum += day_weight * 0.5
            if is_weekend:
                p_we_count += 0.5
                v_we_count += 0.5
        elif p_active:
            p_w_sum += day_weight
            if is_weekend:
                p_we_count += 1.0
        elif v_active:
            v_w_sum += day_weight
            if is_weekend:
                v_we_count += 1.0
            
        current_day = current_day.shift(days=1)

    total_p_weight += p_w_sum
    total_v_weight += v_w_sum
    total_p_weekends += p_we_count
    total_v_weekends += v_we_count

    results.append({
        "Měsíc": m_name, 
        "Petr": round(p_w_sum, 2), 
        "Veronika": round(v_w_sum, 2),
        "Petr (víkendy)": round(p_we_count, 1),
        "Veronika (víkendy)": round(v_we_count, 1)
    })
    progress_bar.progress((idx + 1) / total_steps)

progress_bar.empty()

# --- VÝSTUP ---
st.divider()
st.subheader(f"Přehled pro rok {year_select}")

# Tabulka s výsledky
st.dataframe(
    results, 
    use_container_width=True,
    column_config={
        "Petr": st.column_config.NumberColumn("Petr", format="%.2f"),
        "Veronika": st.column_config.NumberColumn("Veronika", format="%.2f"),
        "Petr (víkendy)": st.column_config.NumberColumn("Petr (víkendy)", format="%.1f d"),
        "Veronika (víkendy)": st.column_config.NumberColumn("Veronika (víkendy)", format="%.1f d"),
    }
)

# Celkové metriky - Péče o děti
st.markdown("### Celkové souhrny")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Petr", f"{total_p_weight:.2f}")
col2.metric("Veronika", f"{total_v_weight:.2f}")
col3.metric("Víkendy Petr", f"{total_p_weekends:.1f} d")
col4.metric("Víkendy Veronika", f"{total_v_weekends:.1f} d")

# Celkové metriky - Lékař a Škola
st.markdown("### Lékaři a škola")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Lékař Petr", f"{total_p_lekar}×")
c2.metric("Lékař Veronika", f"{total_v_lekar}×")
c3.metric("Škola Petr", f"{total_p_skola}×")
c4.metric("Škola Veronika", f"{total_v_skola}×")
