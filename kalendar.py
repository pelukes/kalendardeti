import streamlit as st
import arrow
import re
import unicodedata
from ics import Calendar
from io import StringIO

# --- KONFIGURACE ---
st.set_page_config(page_title="Kalkulačka Děti", layout="centered")

st.title("👨‍👩‍👦‍👦 Kalkulačka péče o děti")
st.write("Nahraj ICS soubor a aplikace spočítá dny s váženým koeficientem. Dny péče jsou identifikovány podle klíčových slov *P. má děti* a *V. má děti*")

# --- SIDEBAR (NASTAVENÍ) ---
with st.sidebar:
    st.header("Nastavení")
    
    # Koeficienty
    col1, col2 = st.columns(2)
    with col1:
        weight_weekend = st.number_input("Koef. Víkend", value=1.5, step=0.1)
    with col2:
        weight_weekday = st.number_input("Koef. Všední", value=1.0, step=0.1)
    
    # Výběr roku
    year_select = st.number_input("Rok", value=2026, step=1)
    
    st.divider()
    
    # Definice všech měsíců
    all_months = {
        "Leden": 1, "Únor": 2, "Březen": 3, "Duben": 4, 
        "Květen": 5, "Červen": 6, "Červenec": 7, "Srpen": 8,
        "Září": 9, "Říjen": 10, "Listopad": 11, "Prosinec": 12
    }
    
    # Výběr měsíců - DEFAULTNĚ VŠECHNY
    st.write("Vybrané měsíce:")
    selected_month_names = st.multiselect(
        "Měsíce", 
        options=list(all_months.keys()),
        default=list(all_months.keys()), # Zde je změna: vybere všechny klíče slovníku
        label_visibility="collapsed"
    )
    
    # Seřadit vybrané měsíce podle kalendáře (aby nebyly na přeskáčku podle klikání)
    months_config = []
    for name in all_months:
        if name in selected_month_names:
            months_config.append((name, all_months[name]))

# --- POMOCNÉ FUNKCE ---
def normalize_text(text):
    if not text: return ""
    normalized = unicodedata.normalize('NFD', text)
    result = "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])
    return result.lower()

def get_weighted_days(start, end):
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
uploaded_file = st.file_uploader("Vyber soubor .ics", type="ics")

if uploaded_file is not None:
    # Streamlit vrací bytes, musíme dekódovat
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    try:
        c = Calendar(stringio.read())
    except Exception as e:
        st.error(f"Chyba při čtení souboru: {e}")
        st.stop()
    
    # Regexy pro hledání (P vs V)
    pattern_p = re.compile(r"\bp\.?\s+ma\s+deti")
    pattern_v = re.compile(r"\bv\.?\s+ma\s+deti")

    events_p_all = []
    events_v_all = []

    # Filtrace událostí z kalendáře
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

    # Progress bar (pro efekt, kdyby to trvalo dlouho)
    progress_bar = st.progress(0)
    total_steps = len(months_config)

    for idx, (m_name, m_month) in enumerate(months_config):
        m_start = arrow.get(year_select, m_month, 1)
        m_end = m_start.shift(months=1)

        # Funkce pro oříznutí intervalů jen na aktuální měsíc
        def get_clipped_intervals(events, bounds_start, bounds_end):
            intervals = []
            for e in events:
                # Ošetření: arrow vs ics.begin
                s = max(e.begin, bounds_start)
                e_end = min(e.end, bounds_end)
                if s < e_end:
                    intervals.append((s, e_end))
            return intervals

        p_intervals = get_clipped_intervals(events_p_all, m_start, m_end)
        v_intervals = get_clipped_intervals(events_v_all, m_start, m_end)

        # Získání bodů zlomu pro přesný výpočet
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

        # Iterace přes segmenty v rámci měsíce
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
        
        # Aktualizace progress baru
        if total_steps > 0:
            progress_bar.progress((idx + 1) / total_steps)

    progress_bar.empty() # Skrýt progress bar po dokončení

    # --- ZOBRAZENÍ VÝSLEDKŮ ---
    st.divider()
    st.subheader(f"Výsledky pro rok {year_select}")
    
    # Přidání řádku Celkem
    results.append({
        "Měsíc": "CELKEM", 
        "P. (vážené dny)": round(total_p, 2), 
        "V. (vážené dny)": round(total_v, 2)
    })
    
    # Vykreslení interaktivní tabulky s formátováním
    st.dataframe(
        results, 
        use_container_width=True,
        column_config={
            "Měsíc": st.column_config.TextColumn("Měsíc", width="medium"),
            "P. (vážené dny)": st.column_config.NumberColumn("Petr (váženo)", format="%.2f"),
            "V. (vážené dny)": st.column_config.NumberColumn("Veronika (váženo)", format="%.2f"),
        }
    )

    # Rychlý přehled metrikami
    col1, col2 = st.columns(2)
    col1.metric("Celkem P.", f"{total_p:.2f}")
    col2.metric("Celkem V.", f"{total_v:.2f}")

