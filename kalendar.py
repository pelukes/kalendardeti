import streamlit as st
import arrow
import re
import unicodedata
import requests
from ics import Calendar

# --- KONFIGURACE ---
st.set_page_config(page_title="Kalkulačka Děti (Online)", layout="centered")

st.title("👨‍👩‍👦‍👦 Kalkulačka péče o děti")

# --- NAČTENÍ URL Z TAJNÝCH PROMĚNNÝCH (SECRETS) ---
# Pokud není URL v secrets, použijeme tu tvou natvrdo (jen pro testování, nedávat na veřejný GitHub!)
try:
    CALENDAR_URL = st.secrets["CALENDAR_URL"]
except:
    # Zde je fallback, ale POZOR: Pokud toto dáš na GitHub, uvidí to všichni.
    # Doporučuji nechat prázdné nebo použít secrets.

# --- SIDEBAR ---
with st.sidebar:
    st.header("Nastavení")
    # Tlačítko pro vynucení aktualizace (kdyby cache držela stará data)
    if st.button("🔄 Obnovit data z kalendáře"):
        st.cache_data.clear()

    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        weight_weekend = st.number_input("Koef. Víkend", value=1.5, step=0.1)
    with col2:
        weight_weekday = st.number_input("Koef. Všední", value=1.0, step=0.1)
    
    year_select = st.number_input("Rok", value=2026, step=1)
    
    st.divider()
    all_months = {
        "Leden": 1, "Únor": 2, "Březen": 3, "Duben": 4, 
        "Květen": 5, "Červen": 6, "Červenec": 7, "Srpen": 8,
        "Září": 9, "Říjen": 10, "Listopad": 11, "Prosinec": 12
    }
    st.write("Vybrané měsíce:")
    selected_month_names = st.multiselect(
        "Měsíce", 
        options=list(all_months.keys()),
        default=list(all_months.keys()),
        label_visibility="collapsed"
    )
    months_config = []
    for name in all_months:
        if name in selected_month_names:
            months_config.append((name, all_months[name]))

# --- FUNKCE ---
def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize('NFD', text)
    result = "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])
    return result.lower()

@st.cache_data(ttl=900) # Cache na 15 minut
def load_calendar_from_url(url):
    try:
        response = requests.get(url)
        response.raise_for_status() # Vyhodí chybu, pokud je status != 200
        return Calendar(response.text)
    except Exception as e:
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

# 1. Stažení kalendáře
with st.spinner('Stahuji aktuální kalendář z Google...'):
    c = load_calendar_from_url(CALENDAR_URL)

if c is None:
    st.error("Nepodařilo se stáhnout kalendář. Zkontrolujte URL adresu.")
    st.stop()
else:
    st.success("Kalendář úspěšně načten!")

# 2. Zbytek logiky (stejný jako dříve)
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
        "P. (vážené dny)": round(p_w_days, 2), 
        "V. (vážené dny)": round(v_w_days, 2)
    })
    if total_steps > 0:
        progress_bar.progress((idx + 1) / total_steps)

progress_bar.empty()

st.divider()
st.subheader(f"Výsledky pro rok {year_select}")
results.append({
    "Měsíc": "CELKEM", 
    "P. (vážené dny)": round(total_p, 2), 
    "V. (vážené dny)": round(total_v, 2)
})

st.dataframe(
    results, 
    use_container_width=True,
    column_config={
        "Měsíc": st.column_config.TextColumn("Měsíc", width="medium"),
        "P. (vážené dny)": st.column_config.NumberColumn("Petr (váženo)", format="%.2f"),
        "V. (vážené dny)": st.column_config.NumberColumn("Verča (váženo)", format="%.2f"),
    }
)

col1, col2 = st.columns(2)
col1.metric("Celkem P.", f"{total_p:.2f}")
col2.metric("Celkem V.", f"{total_v:.2f}")
