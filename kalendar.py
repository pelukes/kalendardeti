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
# Aplikace se pokusí najít URL v st.secrets. 
# Pokud tam není (např. při lokálním testování bez secrets.toml), vypíše chybu.
try:
    CALENDAR_URL = st.secrets["CALENDAR_URL"]
except FileNotFoundError:
    st.error("Chybí soubor secrets.toml nebo nastavení Secrets na Streamlit Cloudu.")
    st.info("Přidejte do Secrets klíč: CALENDAR_URL = 'vaše_dlouhá_adresa'")
    st.stop()
except KeyError:
    st.error("V Secrets nebyl nalezen klíč 'CALENDAR_URL'.")
    st.stop()

# --- SIDEBAR (NASTAVENÍ) ---
with st.sidebar:
    st.header("Nastavení")
    
    # Tlačítko pro vynucení aktualizace (vymaže cache)
    if st.button("🔄 Obnovit data z kalendáře"):
        st.cache_data.clear()

    st.divider()
    
    # Koeficienty
    col1, col2 = st.columns(2)
    with col1:
        weight_weekend = st.number_input("Koef. Víkend", value=1.5, step=0.1)
    with col2:
        weight_weekday = st.number_input("Koef. Všední", value=1.0, step=0.1)
    
    # Výběr roku
    year_select = st.number_input("Rok", value=2026, step=1)
    
    st.divider()
    
    # Definice měsíců
    all_months = {
        "Leden": 1, "Únor": 2, "Březen": 3, "Duben": 4, 
        "Květen": 5, "Červen": 6, "Červenec": 7, "Srpen": 8,
        "Září": 9, "Říjen": 10, "Listopad": 11, "Prosinec": 12
    }
    
    # Výběr měsíců - Defaultně všechny
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

# --- POMOCNÉ FUNKCE ---

def normalize_text(text):
    """Odstraní diakritiku a převede na malá písmena."""
    if not text: return ""
    normalized = unicodedata.normalize('NFD', text)
    result = "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])
    return result.lower()

@st.cache_data(ttl=900)  # Cache platná 15 minut
def get_calendar_text(url):
    """
    Stáhne obsah kalendáře jako text.
    Vrací pouze string (text), který Streamlit umí snadno cachovat.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return None

def get_weighted_days(start, end):
    """Vypočítá vážené dny (víkend vs všední den)."""
    total_weighted_days = 0.0
    current = start
    while current < end:
        next_midnight = current.shift(days=1).floor('day')
        segment_end = min(end, next_midnight)
        duration = (segment_end - current).total_seconds() / 86400.0
        
        # 5=Sobota, 6=Neděle
        if current.weekday() >= 5: 
            total_weighted_days += duration * weight_weekend
        else:
            total_weighted_days += duration * weight_weekday
        current = segment_end
    return total_weighted_days

# --- HLAVNÍ LOGIKA ---

# 1. Stažení textu kalendáře (s využitím cache)
with st.spinner('Stahuji aktuální kalendář z Google...'):
    ics_text = get_calendar_text(CALENDAR_URL)

if ics_text is None:
    st.error("Nepodařilo se stáhnout kalendář. Zkontrolujte URL adresu v Secrets.")
    st.stop()

# 2. Vytvoření objektu Calendar (rychlá operace, není třeba cachovat)
try:
    c = Calendar(ics_text)
    st.success("Kalendář úspěšně načten!")
except Exception as e:
    st.error(f"Chyba při parsování kalendáře: {e}")
    st.stop()

# 3. Filtrace událostí
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

# 4. Výpočet statistik
results = []
total_p = 0.0
total_v = 0.0

progress_bar = st.progress(0)
total_steps = len(months_config)

for idx, (m_name, m_month) in enumerate(months_config):
    m_start = arrow.get(year_select, m_month, 1)
    m_end = m_start.shift(months=1)

    # Funkce pro ořezání intervalů
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

    # Body zlomu
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

    # Průchod segmenty
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
        "P.": round(p_w_days, 2), 
        "V.": round(v_w_days, 2)
    })
    
    if total_steps > 0:
        progress_bar.progress((idx + 1) / total_steps)

progress_bar.empty()

# --- ZOBRAZENÍ VÝSLEDKŮ ---
st.divider()
st.subheader(f"Výsledky pro rok {year_select}")

# Přidání součtového řádku
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
        "P. (vážené dny)": st.column_config.NumberColumn("Petr", format="%.2f"),
        "V. (vážené dny)": st.column_config.NumberColumn("Veronika", format="%.2f"),
    }
)

col1, col2 = st.columns(2)
col1.metric("Celkem P.", f"{total_p:.2f}")
col2.metric("Celkem V.", f"{total_v:.2f}")

