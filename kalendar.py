import streamlit as st
import arrow
import re
import unicodedata
import requests
from ics import Calendar
import pandas as pd # <-- Nový import pro grafy a stylování

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Děti (Online Google Kalendář)", page_icon="👨‍👩‍👦‍👦", layout="wide")

st.title("👨‍👩‍👦‍👦 Jáchymek a Vilémek: Hlídací Dashboard")

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
    st.header("⚙️ Nastavení")
    
    if st.button("🔄 Obnovit data z kalendáře", use_container_width=True):
        st.cache_data.clear()

    st.divider()
    
    year_select = st.number_input("📅 Rok", value=2026, step=1)
    
    st.divider()
    
    # Skrytí výběru měsíců do "expanderu" pro čistší sidebar
    with st.expander("📆 Výběr měsíců", expanded=True):
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
        cols = st.columns(2) # Změněno na 2 sloupce pro lepší čitelnost
        for i, month_name in enumerate(all_months.keys()):
            with cols[i % 2]:
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
    st.warning("👈 Vyberte prosím alespoň jeden měsíc v levém panelu.")
    st.stop()

with st.spinner('⏳ Stahuji aktuální kalendář z Google...'):
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

# Výpočet
results = []
total_p_weight = 0.0
total_v_weight = 0.0
total_p_weekends = 0.0
total_v_weekends = 0.0

progress_bar = st.progress(0, text="Zpracovávám kalendář...")
total_steps = len(months_config)

for idx, (m_name, m_month) in enumerate(months_config):
    m_start = arrow.get(year_select, m_month, 1)
    m_end = m_start.shift(months=1)

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
        
        # Logika
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
    progress_bar.progress((idx + 1) / total_steps, text=f"Zpracován měsíc: {m_name}")

progress_bar.empty()

# Převedení výsledků do Pandas DataFrame pro lepší vizualizace
df = pd.DataFrame(results)

# --- VÝSTUP (Vizuálně upravený) ---

# 1. Celkové metriky (Dány nahoru pro okamžitý přehled)
st.markdown(f"### 🏆 Celkový souhrn za rok {year_select}")

# Výpočet rozdílu pro vizuální zobrazení, kdo "vede"
diff_weight = total_p_weight - total_v_weight
diff_weekend = total_p_weekends - total_v_weekends

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("🔵 Celkem: Petr", f"{total_p_weight:.1f}", delta=f"{diff_weight:.1f} vs Ver." if diff_weight != 0 else None, delta_color="normal")
with col2:
    st.metric("🟣 Celkem: Veronika", f"{total_v_weight:.1f}", delta=f"{-diff_weight:.1f} vs Petr" if diff_weight != 0 else None, delta_color="normal")
with col3:
    st.metric("🏕️ Víkendy: Petr", f"{total_p_weekends:.1f} d", delta=f"{diff_weekend:.1f} d vs Ver." if diff_weekend != 0 else None)
with col4:
    st.metric("🏕️ Víkendy: Veronika", f"{total_v_weekends:.1f} d", delta=f"{-diff_weekend:.1f} d vs Petr" if diff_weekend != 0 else None)

st.divider()

# 2. Grafy v záložkách (Tabs)
tab1, tab2 = st.tabs(["📊 Celkové zatížení (vč. koeficientů)", "🏕️ Čisté víkendy"])

with tab1:
    st.bar_chart(df.set_index("Měsíc")[["Petr", "Veronika"]], color=["#1E88E5", "#D81B60"]) # Modrá vs Růžovo-červená

with tab2:
    st.bar_chart(df.set_index("Měsíc")[["Petr (víkendy)", "Veronika (víkendy)"]], color=["#1E88E5", "#D81B60"])

st.divider()

# 3. Vylepšená tabulka
st.markdown("### 📋 Detailní rozpis po měsících")

# Stylování DataFrame (Teplotní mapa na pozadí buněk pro rychlou vizuální orientaci)
styled_df = df.style.background_gradient(subset=["Petr", "Veronika"], cmap="Blues").format(precision=1)

st.dataframe(
    styled_df, 
    use_container_width=True,
    height=400,
    column_config={
        "Měsíc": st.column_config.TextColumn("Měsíc", width="medium"),
        "Petr": st.column_config.NumberColumn("Petr (body)", format="%.1f"),
        "Veronika": st.column_config.NumberColumn("Veronika (body)", format="%.1f"),
        "Petr (víkendy)": st.column_config.NumberColumn("Petr (víkendy)", format="%.1f dnů"),
        "Veronika (víkendy)": st.column_config.NumberColumn("Veronika (víkendy)", format="%.1f dnů"),
    }
)
