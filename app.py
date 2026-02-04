import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from fpdf import FPDF
import unicodedata

# --- 1. KONFIGURACE A KONSTANTY (ROK 2025) ---
st.set_page_config(page_title="Daňový Guru 7.0", page_icon="👨‍👩‍👧‍👦", layout="wide")

CONST = {
    "ROK": 2025,
    "SLEVA_POPLATNIK": 30840,
    "SLEVA_MANZEL": 24840,        # Sleva na manželku/manžela
    "SLEVA_DITE_1": 15204,        # 1. dítě
    "SLEVA_DITE_2": 22320,        # 2. dítě
    "SLEVA_DITE_3": 27840,        # 3. a další dítě
    "MIN_SOC_MESICNE": 4759,
    "MIN_ZDRAV_MESICNE": 3161,
    "PASMO_1_PAUSAL_DAN": 8716,
    "PASMO_2_PAUSAL_DAN": 16745,
    "PASMO_3_PAUSAL_DAN": 27139,
    "LIMIT_23_PROCENT": 1582812,
    "STROJ_SOC_POJ": 2110416
}

SOUBOR_DAT = "moje_dane_2025_v7.json"

# --- 2. INIT SESSION STATE ---
def init_state():
    defaults = {
        "prijmy": 1200000, 
        "realne_vydaje": 500000, 
        "zalohy_soc": CONST["MIN_SOC_MESICNE"] * 12, 
        "zalohy_zdrav": CONST["MIN_ZDRAV_MESICNE"] * 12,
        # Nové položky pro v7.0
        "pocet_deti": 0,
        "manzel_sleva": False,
        "odpocet_hypoteka": 0,
        "odpocet_penze": 0,
        "odpocet_dary": 0
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_state()

# --- 3. UKLÁDÁNÍ A NAČÍTÁNÍ ---
def ulozit_data():
    keys = ["prijmy", "realne_vydaje", "zalohy_soc", "zalohy_zdrav", 
            "pocet_deti", "manzel_sleva", "odpocet_hypoteka", "odpocet_penze", "odpocet_dary"]
    data = {k: st.session_state[k] for k in keys}
    with open(SOUBOR_DAT, "w") as f:
        json.dump(data, f)
    st.toast("✅ Data uložena!", icon="💾")

def nacist_data():
    if os.path.exists(SOUBOR_DAT):
        with open(SOUBOR_DAT, "r") as f:
            data = json.load(f)
            for k, v in data.items():
                st.session_state[k] = v
        st.toast("📂 Data načtena!", icon="📂")
    else:
        st.error("Soubor neexistuje.")

# --- 4. POMOCNÉ FUNKCE ---
def odstran_diakritiku(text):
    if not isinstance(text, str): text = str(text)
    normalized = unicodedata.normalize('NFD', text)
    return "".join([c for c in normalized if unicodedata.category(c) != 'Mn'])

def spocitat_slevu_na_deti(pocet):
    celkem = 0
    if pocet >= 1: celkem += CONST["SLEVA_DITE_1"]
    if pocet >= 2: celkem += CONST["SLEVA_DITE_2"]
    if pocet >= 3: celkem += (pocet - 2) * CONST["SLEVA_DITE_3"]
    return celkem

# --- 5. LOGIKA VÝPOČTU ---
def vypocet_komplet(prijmy, vydaje, is_pausal_dan=False, pasmo_pausal_dan=0):
    # A. Paušální daň (jednoduché)
    if is_pausal_dan:
        if pasmo_pausal_dan == 1: mesicni = CONST["PASMO_1_PAUSAL_DAN"]
        elif pasmo_pausal_dan == 2: mesicni = CONST["PASMO_2_PAUSAL_DAN"]
        else: mesicni = CONST["PASMO_3_PAUSAL_DAN"]
        celkem_rok = mesicni * 12
        return {
            "typ": f"Paušální daň (Pásmo {pasmo_pausal_dan})",
            "dan_vysledna": 0, "dan_bonus": 0, "soc": 0, "zdrav": 0,
            "celkem_stat": celkem_rok,
            "cisty_zisk": prijmy - celkem_rok,
            "vydaje_uplatnene": 0,
            "message": "V paušálním režimu nelze uplatnit slevy na děti ani hypotéku!"
        }

    # B. Standardní režim
    zisk = prijmy - vydaje
    
    # 1. Odpočty od základu daně (Hypotéka, Dary...)
    nezdanitelne_casti = st.session_state.odpocet_hypoteka + st.session_state.odpocet_penze + st.session_state.odpocet_dary
    zaklad_dane = max(0, zisk - nezdanitelne_casti)
    
    # 2. Výpočet hrubé daně
    if zaklad_dane > CONST["LIMIT_23_PROCENT"]:
        zaklad_15 = CONST["LIMIT_23_PROCENT"]
        zaklad_23 = zaklad_dane - CONST["LIMIT_23_PROCENT"]
        dan_hruba = (zaklad_15 * 0.15) + (zaklad_23 * 0.23)
    else:
        dan_hruba = zaklad_dane * 0.15
        
    # 3. Slevy na dani (Poplatník, Manžel/ka) - jdou jen do nuly
    slevy_zakladni = CONST["SLEVA_POPLATNIK"]
    if st.session_state.manzel_sleva:
        slevy_zakladni += CONST["SLEVA_MANZEL"]
        
    dan_po_zakladnich_slevach = max(0, dan_hruba - slevy_zakladni)
    
    # 4. Slevy na děti (Daňový bonus) - může jít do mínusu (stát vrací)
    sleva_deti = spocitat_slevu_na_deti(st.session_state.pocet_deti)
    dan_po_detech = dan_po_zakladnich_slevach - sleva_deti
    
    dan_vysledna = max(0, dan_po_detech) # Co zaplatím
    dan_bonus = 0
    if dan_po_detech < 0:
        dan_bonus = abs(dan_po_detech) # Co mi stát vrátí (max do výše limitu, ten zjednodušíme)

    # 5. Pojištění
    vymerovaci_zaklad = zisk * 0.55
    vm_soc = min(vymerovaci_zaklad, CONST["STROJ_SOC_POJ"])
    soc = max(vm_soc * 0.292, CONST["MIN_SOC_MESICNE"] * 12)
    zdrav = max(vymerovaci_zaklad * 0.135, CONST["MIN_ZDRAV_MESICNE"] * 12)
    
    # Celkem cashflow (daň - bonus + soc + zdrav)
    celkem_stat = dan_vysledna - dan_bonus + soc + zdrav
    
    return {
        "typ": "Standardní zdanění",
        "dan_vysledna": dan_vysledna,
        "dan_bonus": dan_bonus,
        "soc": soc,
        "zdrav": zdrav,
        "celkem_stat": celkem_stat,
        "cisty_zisk": prijmy - vydaje - celkem_stat,
        "vydaje_uplatnene": vydaje,
        "nezdanitelne_casti": nezdanitelne_casti,
        "sleva_deti": sleva_deti
    }

def get_pausal_rezim_pasmo(prijmy):
    if prijmy <= 1000000: return 1
    elif prijmy <= 1500000: return 2
    elif prijmy <= 2000000: return 3
    return None

# --- 6. PDF EXPORT (Rozšířený) ---
def create_pdf(res, prijmy):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    pdf.cell(0, 10, odstran_diakritiku(f"Danovy Report {CONST['ROK']} - Detailni"), ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    
    pdf.cell(0, 8, odstran_diakritiku(f"Typ: {res['typ']}"), ln=True)
    pdf.cell(0, 8, f"Prijmy: {prijmy:,.0f} CZK", ln=True)
    pdf.cell(0, 8, f"Vydaje: {res['vydaje_uplatnene']:,.0f} CZK", ln=True)
    
    if "nezdanitelne_casti" in res and res["nezdanitelne_casti"] > 0:
         pdf.cell(0, 8, f"Odpocet od zakladu (hypo, penze...): -{res['nezdanitelne_casti']:,.0f} CZK", ln=True)

    pdf.line(10, 60, 200, 60)
    pdf.ln(5)
    
    if "soc" in res and res["soc"] > 0:
        pdf.cell(0, 8, f"Socialni pojisteni: {res['soc']:,.0f} CZK", ln=True)
        pdf.cell(0, 8, f"Zdravotni pojisteni: {res['zdrav']:,.0f} CZK", ln=True)
        pdf.ln(5)
        pdf.cell(0, 8, f"Dan z prijmu (vypoctena): {res['dan_vysledna']:,.0f} CZK", ln=True)
        if res['dan_bonus'] > 0:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 8, f"DANOVY BONUS (stat vraci): +{res['dan_bonus']:,.0f} CZK", ln=True)
            pdf.set_text_color(0, 0, 0)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 15, f"CELKOVE SALDO UHRAD: {res['celkem_stat']:,.0f} CZK", ln=True)
    
    return pdf.output(dest='S').encode('latin-1')

# --- 7. UI APLIKACE ---
st.title(f"👨‍👩‍👧‍👦 Daňový Guru 7.0 (Rodinná edice)")

# Lišta
c1, c2, c3 = st.columns([1, 1, 4])
c1.button("💾 Uložit data", on_click=ulozit_data)
c2.button("📂 Načíst data", on_click=nacist_data)
st.divider()

# --- VSTUPY ---
col_in1, col_in2 = st.columns(2)

with col_in1:
    st.subheader("1. Podnikání")
    st.number_input("Roční příjmy (Kč)", step=10000, key="prijmy")
    st.number_input("Reálné výdaje (Kč)", step=5000, key="realne_vydaje")
    
    with st.expander("💳 Zálohy (pro výpočet nedoplatku)"):
        st.number_input("Zaplaceno na Soc.", key="zalohy_soc")
        st.number_input("Zaplaceno na Zdrav.", key="zalohy_zdrav")

with col_in2:
    st.subheader("2. Rodina a Odpočty")
    st.info("Toto sníží daň jen u Standardního režimu (ne u Paušální daně).")
    
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.number_input("Počet dětí", min_value=0, max_value=10, key="pocet_deti")
        st.checkbox("Sleva na manžela/ku?", key="manzel_sleva", help="Jen pokud má vlastní příjmy pod 68 000 Kč ročně.")
    
    with col_r2:
        st.number_input("Úroky z hypotéky", key="odpocet_hypoteka")
        st.number_input("Penzijní/Životní poj.", key="odpocet_penze")
        st.number_input("Dary (charita, krev...)", key="odpocet_dary")

# --- VÝPOČTY ---
prijmy_val = st.session_state.prijmy
realne_vydaje_val = st.session_state.realne_vydaje

# Varianty
vydaje_60 = min(prijmy_val * 0.6, 1200000)
res_pausal_60 = vypocet_komplet(prijmy_val, vydaje_60)
res_pausal_60["typ"] = "Paušální výdaje 60%"

res_real = vypocet_komplet(prijmy_val, realne_vydaje_val)
res_real["typ"] = "Reálné výdaje"

pasmo = get_pausal_rezim_pasmo(prijmy_val)
res_rezim = None
if pasmo:
    res_rezim = vypocet_komplet(prijmy_val, 0, is_pausal_dan=True, pasmo_pausal_dan=pasmo)

# Vyhodnocení
variants = [res_pausal_60, res_real]
if res_rezim: variants.append(res_rezim)
winner = min(variants, key=lambda x: x['celkem_stat'])

st.divider()

# --- VÝSLEDKY ---
col_res1, col_res2 = st.columns([2, 1])

with col_res1:
    st.subheader(f"🏆 Vítěz: {winner['typ']}")
    
    # Check pro daňový bonus
    if "dan_bonus" in winner and winner["dan_bonus"] > 0:
        st.balloons()
        st.success(f"🎉 Pozor! Stát ti vrátí **{winner['dan_bonus']:,.0f} Kč** na daňovém bonusu!")
        st.write(f"Celkové saldo (Pojištění minus Bonus): **{winner['celkem_stat']:,.0f} Kč**")
    else:
        st.write(f"Celkem státu zaplatíš: **{winner['celkem_stat']:,.0f} Kč**")

    # Tabulka
    df = pd.DataFrame(variants).set_index("typ")[["celkem_stat", "cisty_zisk"]]
    st.dataframe(df.style.format("{:,.0f} Kč").highlight_min(subset=["celkem_stat"], color="lightgreen"), use_container_width=True)

    if "message" in winner:
        st.warning(f"⚠️ {winner['message']}")

with col_res2:
    st.subheader("Grafika")
    fig = px.bar(pd.DataFrame(variants), x="typ", y="celkem_stat", title="Kolik zaplatíš státu")
    st.plotly_chart(fig, use_container_width=True)
    
    # PDF
    pdf_data = create_pdf(winner, st.session_state.prijmy)
    st.download_button("📄 PDF Report", data=pdf_data, file_name="danovy_report.pdf", mime="application/pdf")
