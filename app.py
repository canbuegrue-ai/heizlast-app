import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

# --- KfW KONSTANTEN ---
RAUMTEMP_DEFAULT = {"Wohnen": 20, "Bad": 24, "Schlafen": 18, "Küche": 20, "Flur": 15}

# 1. Standort / Außentemperatur (KfW Anforderung)
st.subheader("📍 Projekt-Stammdaten")
col_plz, col_temp = st.columns(2)
with col_plz:
    plz = st.text_input("Postleitzahl des Objekts", "12345")
with col_temp:
    t_aussen = st.number_input("Norm-Außentemperatur (°C)", value=-12)

st.divider()

# 2. Raum-Eingabe (KfW konform)
st.subheader("🚪 Raumweise Erfassung")
nutzung = st.selectbox("Raumnutzung", list(RAUMTEMP_DEFAULT.keys()))
t_innen = RAUMTEMP_DEFAULT[nutzung]

col_r1, col_r2, col_r3 = st.columns(3)
with col_r1:
    r_breite = st.number_input("Raumbreite (m)", value=4.0)
with col_r2:
    r_laenge = st.number_input("Raumlänge (m)", value=5.0)
with col_r3:
    r_hoehe = st.number_input("Raumhöhe (m)", value=2.5)

raum_flaeche = r_breite * r_laenge
raum_volumen = raum_flaeche * r_hoehe

# 3. Bauteile des Raums
st.write("🧱 **Bauteile gegen Außenluft / Unbeheizt**")
# Hier könnte man eine Liste von Wänden hinzufügen
u_wand = st.number_input("U-Wert Außenwand (W/m²K)", value=0.3)
a_wand = st.number_input("Netto-Wandfläche (m²)", value=10.0)

# Berechnung Transmission + Lüftung
delta_t = t_innen - t_aussen
q_transmission = a_wand * u_wand * delta_t
q_lueftung = 0.5 * 0.34 * raum_volumen * delta_t # 0.5facher Luftwechsel
gesamt_heizlast = round(q_transmission + q_lueftung, 0)

st.metric("Heizlast für diesen Raum", f"{gesamt_heizlast} Watt")

if st.button("💾 Raum zum KfW-Protokoll hinzufügen"):
    st.session_state['raeume'].append({
        "Raum": nutzung,
        "Fläche": raum_flaeche,
        "Heizlast": gesamt_heizlast,
        "Temp_Innen": t_innen
    })
    st.success("Raum gespeichert!")

# 4. PDF Export (Das Dokument für die KfW)
if len(st.session_state['raeume']) > 0:
    st.divider()
    if st.button("📄 KfW-Protokoll als PDF erstellen"):
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer)
        p.drawString(100, 800, f"Heizlastberechnung & Hydraulischer Abgleich - PLZ: {plz}")
        p.drawString(100, 780, "---------------------------------------------------------")
        y = 750
        for r in st.session_state['raeume']:
            p.drawString(100, y, f"Raum: {r['Raum']} | {r['Fläche']}m² | Soll: {r['Temp_Innen']}°C | Last: {r['Heizlast']} W")
            y -= 20
        p.showPage()
        p.save()
        st.download_button("📥 PDF Herunterladen", data=buffer.getvalue(), file_name="KfW_Protokoll.pdf", mime="application/pdf")
