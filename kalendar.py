import streamlit as st
import arrow
import re
import unicodedata
import requests
from ics import Calendar

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Děti (Online Google Kalendář)", layout="centered")

st.title("👨‍👩‍👦‍👦 Jáchymek a Vilémek")

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
    
    # Koeficienty
    col1, col2 = st.columns(2)
    with col1:
        weight_weekend = st.number_input("Koef. Víkend", value=1.5, step=0.1)
    with col2:
        weight_weekday = st.number_input("Koef. Všední", value=1.0, step=0.1)
    
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

events_p_all = []
events_v_all = []

for event in c.events:
    clean = normalize_text(event.name)
    if pattern_p.search(clean):
        events_p_all.append(event)
    elif pattern_v.search(clean):
        events_v_all.append(event)

# Výpočet po měsících a dnech
results = []
total_p = 0.0
total_v = 0.0

for idx, (m_name, m_month) in enumerate(months_config):
    m_start = arrow.get(year_select, m_month, 1)
    m_end = m_start.shift(months=1)

    p_w_days = 0.0
    v_w_days = 0.0
    p_weekend_count = 0.0  # Nový čítač pro víkendy
    v_weekend_count = 0.0  # Nový čítač pro víkendy

    current_day = m_start
    while current_day < m_end:
        day_start = current_day.floor('day')
        day_end = current_day.ceil('day')
        
        is_weekend = current_day.weekday() >= 5
        day_weight = weight_weekend if is_weekend else weight_weekday
        
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
        
        # Logika rozdělení
        if p_active and v_active:
            p_w_days += day_weight * 0.5
            v_w_days += day_weight * 0.5
            if is_weekend:
                p_weekend_count += 0.5
                v_weekend_count += 0.5
        elif p_active:
            p_w_days += day_weight
            if is_weekend:
                p_weekend_count += 1.0
        elif v_active:
            v_w_days += day_weight
            if is_weekend:
                v_weekend_count += 1.0
            
        current_day = current_day.shift(days=1)

    total_p += p_w_days
    total_v += v_w_days
    results.append({
        "Měsíc": m_name, 
        "Petr (body)": round(p_w_days, 2), 
        "Veronika (body)": round(v_w_days, 2),
        "Petr (víkendy)": round(p_weekend_count, 1),
        "Veronika (víkendy)": round(v_weekend_count, 1)
    })
    progress_bar.progress((idx + 1) / total_steps)

progress_bar.empty()

# --- VÝSTUP (UPRAVENÝ) ---
st.divider()
st.subheader(f"Výsledky pro rok {year_select}")

st.dataframe(
    results, 
    use_container_width=True,
    column_config={
        "Petr (body)": st.column_config.NumberColumn(format="%.2f"),
        "Veronika (body)": st.column_config.NumberColumn(format="%.2f"),
        "Petr (víkendy)": st.column_config.NumberColumn(format="%.1f d"),
        "Veronika (víkendy)": st.column_config.NumberColumn(format="%.1f d"),
    })

# Celkové metriky
col_p, col_v = st.columns(2)
col_p.metric("Celkem Petr", f"{total_p:.2f}")
col_v.metric("Celkem Veronika", f"{total_v:.2f}")

st.info("💡 Pokud jsou oba rodiče v kalendáři ve stejný den, váha dne se dělí 50/50.")



