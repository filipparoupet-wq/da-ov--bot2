import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import datetime
from fpdf import FPDF
import unicodedata

# --- 1. KONFIGURACE A LEGISLATIVA (2025/2026) ---
st.set_page_config(
    page_title="Daňový Guru 2026", 
    page_icon="🏦", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Legislativní konstanty pro rok 2025/2026
CONST = {
    "ROK": 2025,
    "SLEVA_POPLATNIK": 30840,
    "SLEVA_MANZEL": 24840,
    "SLEVA_DITE_1": 15204, "SLEVA_DITE_2": 22320, "SLEVA_DITE_3": 27840,
    "SLEVA_INVALIDITA_1_2": 2520, "SLEVA_INVALIDITA_3": 5040, "SLEVA_ZTP_P": 16140,
    "MIN_SOC_HLAVNI": 4759 * 12, "MIN_ZDRAV_HLAVNI": 3161 * 12,
    "PASMO_1_PAUSAL_DAN": 8716, "PASMO_2_PAUSAL_DAN": 16745, "PASMO_3_PAUSAL_DAN": 27139,
    "LIMIT_DPH": 2000000, "LIMIT_23_PROCENT": 1582812, "STROJ_SOC_POJ": 2110416
}

SOUBOR_DAT = "guru_data_storage.json"

# --- 2. LOGIKA A VÝPOČTY ---
def odstran_diakritiku(text):
    if not isinstance(text, str): text = str(text)
    return "".join([c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn'])

def vypocet_komplet(prijmy, vydaje, config, is_pausal_dan=False):
    # Určení pásma pro paušální daň
    pasmo = 1
    if prijmy > 1500000: pasmo = 3
    elif prijmy > 1000000: pasmo = 2
    
    if is_pausal_dan:
        if prijmy > 2000000: return {"typ": "Paušální režim", "celkem": 9999999, "zisk": 0}
        platba = CONST[f"PASMO_{pasmo}_PAUSAL_DAN"] * 12
        return {"typ": f"Paušální daň (Pásmo {pasmo})", "celkem": platba, "zisk": prijmy - platba, "dan": 0, "soc": 0, "zdrav": 0}
    
    # Standardní výpočet
    zisk = max(0, prijmy - vydaje)
    zaklad = max(0, zisk - (config['odpocty_hypo'] + config['odpocty_penze'] + config['odpocty_dary']))
    
    # Daň
    if zaklad > CONST["LIMIT_23_PROCENT"]:
        dan_h = (CONST["LIMIT_23_PROCENT"] * 0.15 + (zaklad - CONST["LIMIT_23_PROCENT"]) * 0.23)
    else: 
        dan_h = zaklad * 0.15
    
    # Slevy
    slevy = CONST["SLEVA_POPLATNIK"]
    if config['sleva_manzel']: slevy += CONST["SLEVA_MANZEL"]
    if config['invalidita'] == "1. nebo 2. stupeň": slevy += CONST["SLEVA_INVALIDITA_1_2"]
    elif config['invalidita'] == "3. stupeň": slevy += CONST["SLEVA_INVALIDITA_3"]
    elif config['invalidita'] == "ZTP/P": slevy += CONST["SLEVA_ZTP_P"]
    
    dan_po_slevach = max(0, dan_h - slevy)
    
    # Děti
    p = config['pocet_deti']
    sleva_deti = 0
    if p >= 1: sleva_deti += CONST["SLEVA_DITE_1"]
    if p >= 2: sleva_deti += CONST["SLEVA_DITE_2"]
    if p >= 3: sleva_deti += (p-2) * CONST["SLEVA_DITE_3"]
    
    final_dan = dan_po_slevach - sleva_deti # Může být daňový bonus (mínus)
    
    # Pojištění
    vm = min(zisk * 0.55, CONST["STROJ_SOC_POJ"])
    if config['hlavni_cinnost']:
        soc, zdrav = max(vm * 0.292, CONST["MIN_SOC_HLAVNI"]), max(vm * 0.135, CONST["MIN_ZDRAV_HLAVNI"])
    else:
        soc, zdrav = (vm * 0.292 if zisk > 105558 else 0), vm * 0.135
        
    return {
        "typ": "Standardní", 
        "dan": final_dan, 
        "soc": soc, 
        "zdrav": zdrav, 
        "celkem": final_dan + soc + zdrav,
        "zisk": prijmy - vydaje - (final_dan + soc + zdrav)
    }

# --- 3. SESSION STATE & PERSISTENCE ---
if 'data' not in st.session_state:
    if os.path.exists(SOUBOR_DAT):
        with open(SOUBOR_DAT, "r") as f:
            st.session_state.data = json.load(f)
    else:
        st.session_state.data = {
            "faktury": [],
            "vydaje": [],
            "config": {
                "hlavni_cinnost": True, "pocet_deti": 0, "sleva_manzel": False,
                "invalidita": "Žádná", "odpocty_hypo": 0, "odpocty_penze": 0, "odpocty_dary": 0
            },
            "user": {"jmeno": "", "ico": "", "ucet": ""}
        }

def save():
    with open(SOUBOR_DAT, "w") as f:
        json.dump(st.session_state.data, f)

# --- 4. PDF ENGINE ---
def generuj_pdf(faktura, user):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "FAKTURA - DANOVY DOKLAD", ln=True, align='R')
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Cislo: {faktura['cislo']}", ln=True, align='R')
    pdf.line(10, 30, 200, 30)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(90, 10, "DODAVATEL:")
    pdf.cell(90, 10, "ODBERATEL:", ln=True)
    
    pdf.set_font("Arial", size=10)
    y_start = pdf.get_y()
    pdf.multi_cell(90, 5, f"{odstran_diakritiku(user['jmeno'])}\nICO: {user['ico']}\nUcet: {user['ucet']}")
    pdf.set_xy(100, y_start)
    pdf.multi_cell(90, 5, f"{odstran_diakritiku(faktura['klient'])}")
    
    pdf.ln(20)
    pdf.cell(140, 10, "Popis", 1)
    pdf.cell(50, 10, "Castka", 1, ln=True)
    pdf.cell(140, 10, odstran_diakritiku(faktura['popis']), 1)
    pdf.cell(50, 10, f"{faktura['castka']:,} CZK", 1, ln=True)
    
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- 5. UI APP ---
st.title("🏦 Daňový Guru 2026")
st.caption("Profesionální asistent pro OSVČ")

# Sidebar - Nastavení
with st.sidebar:
    st.header("⚙️ Nastavení profilu")
    st.session_state.data["user"]["jmeno"] = st.text_input("Vaše jméno", st.session_state.data["user"]["jmeno"])
    st.session_state.data["user"]["ico"] = st.text_input("IČO", st.session_state.data["user"]["ico"])
    st.session_state.data["user"]["ucet"] = st.text_input("Bankovní účet", st.session_state.data["user"]["ucet"])
    
    st.divider()
    st.header("📑 Daňové parametry")
    c = st.session_state.data["config"]
    c["hlavni_cinnost"] = st.toggle("Hlavní činnost", c["hlavni_cinnost"])
    c["pocet_deti"] = st.number_input("Počet dětí", 0, 10, c["pocet_deti"])
    c["sleva_manzel"] = st.checkbox("Sleva na manželku (příjem do 68k)", c["sleva_manzel"])
    c["invalidita"] = st.selectbox("Invalidita", ["Žádná", "1. nebo 2. stupeň", "3. stupeň", "ZTP/P"], index=0)
    
    if st.button("💾 Uložit vše trvale"):
        save()
        st.success("Data uložena!")

# Výpočty základních metrik
total_prijmy = sum(f['castka'] for f in st.session_state.data["faktury"])
total_vydaje_real = sum(v['castka'] for v in st.session_state.data["vydaje"])

# Optimalizátor (výpočet variant)
res_pausal_60 = vypocet_komplet(total_prijmy, min(total_prijmy * 0.6, 1200000), c)
res_real = vypocet_komplet(total_prijmy, total_vydaje_real, c)
res_fix = vypocet_komplet(total_prijmy, 0, c, is_pausal_dan=True)

vysledky = [
    {"id": "Paušální výdaje 60%", "data": res_pausal_60},
    {"id": "Reálné výdaje", "data": res_real},
    {"id": "Paušální daň", "data": res_fix}
]
vysledky = [v for v in vysledky if v["data"]["celkem"] < 9000000] # Odfiltrování neplatné paušální daně
best = min(vysledky, key=lambda x: x["data"]["celkem"])

# --- DASHBOARD ---
t1, t2, t3, t4 = st.tabs(["📊 Dashboard", "🧾 Příjmy", "💸 Výdaje", "🧠 Optimalizátor"])

with t1:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Obrat", f"{total_prijmy:,.0f} Kč")
    m2.metric("Náklady", f"{total_vydaje_real:,.0f} Kč")
    m3.metric("Odvody (Nejlepší)", f"{best['data']['celkem']:,.0f} Kč", delta_color="inverse")
    m4.metric("Čistý zisk", f"{total_prijmy - total_vydaje_real - best['data']['celkem']:,.0f} Kč")
    
    st.divider()
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("Hlídač limitů")
        # DPH Limit
        dph_perc = min(total_prijmy / 2000000, 1.0)
        st.write(f"**Limit DPH (2 000 000 Kč):** {total_prijmy:,.0f} Kč")
        st.progress(dph_perc)
        if dph_perc > 0.9: st.error("⚠️ Jste těsně pod limitem pro plátcovství DPH!")
        
    with col_right:
        st.subheader("Rozdělení peněz")
        # Graf z nejlepší varianty
        viz_data = pd.DataFrame({
            "Kategorie": ["Zisk", "Odvody", "Výdaje"],
            "Částka": [total_prijmy - total_vydaje_real - best['data']['celkem'], best['data']['celkem'], total_vydaje_real]
        })
        fig = px.pie(viz_data, values="Částka", names="Kategorie", hole=0.5, color_discrete_sequence=px.colors.qualitative.Safe)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=250)
        st.plotly_chart(fig, use_container_width=True)

with t2:
    st.subheader("Evidence příjmů")
    with st.expander("➕ Přidat novou fakturu"):
        with st.form("inv_form", clear_on_submit=True):
            f_k = st.text_input("Odběratel / Klient")
            f_c = st.number_input("Částka v Kč", min_value=0, step=1000)
            f_p = st.text_input("Popis plnění", "Služby / Konzultace")
            if st.form_submit_button("Vystavit a uložit"):
                new_inv = {
                    "id": len(st.session_state.data["faktury"]),
                    "cislo": f"2026{len(st.session_state.data['faktury'])+1:03d}",
                    "klient": f_k, "castka": f_c, "popis": f_p, "datum": str(datetime.date.today())
                }
                st.session_state.data["faktury"].append(new_inv)
                st.rerun()
                
    if st.session_state.data["faktury"]:
        df_inv = pd.DataFrame(st.session_state.data["faktury"])
        st.dataframe(df_inv[["cislo", "klient", "castka", "datum"]], use_container_width=True)
        
        # Akce pro faktury
        sel_inv_idx = st.selectbox("Vyberte fakturu pro akci", range(len(st.session_state.data["faktury"])), format_func=lambda x: st.session_state.data["faktury"][x]["cislo"])
        c_p1, c_p2 = st.columns(2)
        inv_data = st.session_state.data["faktury"][sel_inv_idx]
        pdf_bytes = generuj_pdf(inv_data, st.session_state.data["user"])
        c_p1.download_button("📄 Stáhnout PDF", pdf_bytes, f"faktura_{inv_data['cislo']}.pdf")
        if c_p2.button("🗑️ Smazat fakturu", type="secondary"):
            st.session_state.data["faktury"].pop(sel_inv_idx)
            st.rerun()

with t3:
    st.subheader("Evidence výdajů")
    with st.form("exp_form", clear_on_submit=True):
        e_p = st.text_input("Popis výdaje")
        e_c = st.number_input("Částka", min_value=0)
        if st.form_submit_button("Uložit výdaj"):
            st.session_state.data["vydaje"].append({"popis": e_p, "castka": e_c, "datum": str(datetime.date.today())})
            st.rerun()
    
    if st.session_state.data["vydaje"]:
        st.table(pd.DataFrame(st.session_state.data["vydaje"]))
        if st.button("Vyčistit výdaje"):
            st.session_state.data["vydaje"] = []
            st.rerun()

with t4:
    st.header("🧠 Porovnání daňových režimů")
    st.info(f"Doporučení: Na základě vašeho obratu je nejvýhodnější: **{best['id']}**")
    
    res_cols = st.columns(len(vysledky))
    for idx, v in enumerate(vysledky):
        with res_cols[idx]:
            is_best = v["id"] == best["id"]
            st.subheader(v["id"])
            if is_best: st.success("NEJVÝHODNĚJŠÍ")
            st.metric("Celkové odvody", f"{v['data']['celkem']:,.0f} Kč")
            st.write(f"**Daň:** {v['data'].get('dan', 0):,.0f} Kč")
            st.write(f"**Sociální:** {v['data'].get('soc', 0):,.0f} Kč")
            st.write(f"**Zdravotní:** {v['data'].get('zdrav', 0):,.0f} Kč")
            st.divider()
            st.write(f"**Zůstatek (Čistý):** {v['data']['zisk']:,.0f} Kč")