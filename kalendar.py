import streamlit as st
import arrow
import re
import unicodedata
import requests
from ics import Calendar

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Kalkulačka Děti (Online)", layout="centered")

st.title("👨‍👩‍👦‍👦 Kalkulačka péče o děti")

# --- NAČTENÍ URL Z TAJNÝCH PROMĚNNÝCH (SECRETS) ---
try:
    CALENDAR_URL = st.secrets["CALENDAR_URL"]
except Exception:
    # Fallback pro lokální testování, pokud nemáš nastavené secrets
    st.error("Nenalezen klíč CALENDAR_URL v Secrets.")
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
    
    # --- LEPŠÍ VÝBĚR MĚSÍCŮ ---
    st.write("**Výběr měsíců:**")
    
    all_months = {
        "Leden": 1, "Únor": 2, "Březen": 3, "Duben": 4, 
        "Květen": 5, "Červen": 6, "Červenec": 7, "Srpen": 8,
        "Září": 9, "Říjen": 10, "Listopad": 11, "Prosinec": 12
    }

    # Tlačítka pro hromadnou akci
    c_all, c_none = st.columns(2)
    if c_all.button("Vybrat vše"):
        for m in all_months.keys():
            st.session_state[f"cb_{m}"] = True
    if c_none.button("Zrušit vše"):
        for m in all_months.keys():
            st.session_state[f"cb_{m}"] = False

    # Mřížka checkboxů 3x4
    selected_month_names = []
    cols = st.columns(3)
    for i, month_name in enumerate(all_months.keys()):
        with cols[i % 3]:
            # Inicializace stavu checkboxu, pokud neexistuje (defaultně True)
            if f"cb_{month_name}" not in st.session_state:
                st.session_state[f"cb_{month_name}"] = True
            
            if st.checkbox(month_name, key=f"cb_{month_name}"):
                selected_month_names.append(month_name)

    # Příprava konfigurace vybraných měsíců
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

def get_weighted_days(start, end):
    total_weighted_days = 0.0
    current = start
    while current < end:
        next_midnight = current.shift(days=1).floor('day')
        segment_end = min(end, next_midnight)
        duration = (segment_end - current).total_seconds() / 86400.0
        if current.weekday() >= 5: 
            total_weighted_days += duration * weight_weekend
        else:
            total_weighted_days += duration * weight_weekday
        current = segment_end
    return total_weighted_days

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

# Filtrace událostí (P vs V)
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

# Výpočet po měsících
results = []
total_p = 0.0
total_v = 0.0

progress_bar = st.progress(0)
total_steps = len(months_config)

for idx, (m_name, m_month) in enumerate(months_config):
    m_start = arrow.get(year_select, m_month, 1)
    m_end = m_start.shift(months=1)

    def get_clipped_intervals(events, bounds_start, bounds_end):
        intervals = []
        for e in events:
            s = max(e.begin, bounds_start)
            e_end = min(e.end, bounds_end)
            if s < e_end:
                intervals.append((s, e_end))
        return intervals

    p_intervals = get_clipped_intervals(events_p_all, m_start, m_end)
    v_intervals = get_clipped_intervals(events_v_all, m_start, m_end)

    points = set([m_start, m_end])
    for s, e in p_intervals + v_intervals:
        points.add(s); points.add(e)
    sorted_points = sorted(list(points))

    p_w_days = 0.0
    v_w_days = 0.0

    def is_active(t, intervals):
        for s, e in intervals:
            if s <= t < e: return True
        return False

    for i in range(len(sorted_points) - 1):
        t1 = sorted_points[i]
        t2 = sorted_points[i+1]
        segment_w_days = get_weighted_days(t1, t2)
        if segment_w_days <= 0: continue
        midpoint = t1 + (t2 - t1) / 2
        p_active = is_active(midpoint, p_intervals)
        v_active = is_active(midpoint, v_intervals)

        if p_active and v_active:
            p_w_days += segment_w_days * 0.5
            v_w_days += segment_w_days * 0.5
        elif p_active:
            p_w_days += segment_w_days
        elif v_active:
            v_w_days += segment_w_days
    
    total_p += p_w_days
    total_v += v_w_days
    results.append({
        "Měsíc": m_name, 
        "Petr": round(p_w_days, 2), 
        "Veronika": round(v_w_days, 2)
    })
    progress_bar.progress((idx + 1) / total_steps)

progress_bar.empty()

# --- VÝSTUP ---
st.divider()
st.subheader(f"Výsledky pro rok {year_select}")

# Tabulka s výsledky
st.dataframe(
    results, 
    use_container_width=True,
    column_config={
        "Petr": st.column_config.NumberColumn(format="%.2f"),
        "Veronika": st.column_config.NumberColumn(format="%.2f"),
    }
)

# Celkové metriky
col_p, col_v = st.columns(2)
col_p.metric("Celkem Petr", f"{total_p:.2f}")
col_v.metric("Celkem Veronika", f"{total_v:.2f}")
