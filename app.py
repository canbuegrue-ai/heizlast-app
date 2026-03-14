import streamlit as st
from PIL import Image
from google import genai
import fitz  
import io    
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --- 1. KONFIGURATION ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
client = genai.Client(api_key=api_key) if api_key else None

st.set_page_config(layout="wide", page_title="KfW Heizlast-Assistent 2026")

if 'raeume' not in st.session_state: st.session_state['raeume'] = []
if 'ki_flaeche' not in st.session_state: st.session_state['ki_flaeche'] = 0.0

# --- 2. PDF FUNKTION ---
def erstelle_kfw_pdf(projekt, raum_liste):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    h = A4[1]
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, h - 50, "KfW-Heizlastprotokoll (Verfahren B)")
    p.setFont("Helvetica", 10)
    p.drawString(50, h - 70, f"Projekt: {projekt['name']} | PLZ: {projekt['plz']} | Außentemp: {projekt['t_aussen']}°C")
    y = h - 120
    p.drawString(50, y, "Raum | Flaeche | Soll-Temp | Heizlast")
    p.line(50, y-5, 550, y-5)
    y -= 25
    summe = 0
    for r in raum_liste:
        p.drawString(50, y, f"{r['Raum']} | {r['Fläche']}m2 | {r['T_Soll']}°C | {int(r['Heizlast'])}W")
        summe += r['Heizlast']
        y -= 20
    p.line(50, y, 550, y)
    p.drawString(350, y-20, f"Gesamtlast: {int(summe)} Watt")
    p.showPage()
    p.save()
    return buffer.getvalue()

# --- 3. UI ---
st.title("🏠 KfW-Heizlast-Assistent (New Generation)")

col_a, col_b, col_c = st.columns(3)
with col_a: p_name = st.text_input("Kunde", "Müller")
with col_b: p_plz = st.text_input("PLZ", "12345")
with col_c: p_temp = st.number_input("Norm-Außentemp. (°C)", value=-12)

st.divider()

file = st.file_uploader("Grundriss hochladen", type=["pdf", "jpg", "png"])
bild = None
if file:
    if file.name.lower().endswith("pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        pix = doc.load_page(0).get_pixmap(dpi=100)
        bild = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        bild = Image.open(file)
    st.image(bild, caption="Plan-Vorschau", width=800)

st.divider()

c1, c2 = st.columns([1, 2])
with c1:
    r_name = st.selectbox("Raum", ["Wohnen", "Küche", "Bad", "Schlafen", "Flur"])
    t_soll = {"Wohnen": 20, "Küche": 20, "Bad": 24, "Schlafen": 18, "Flur": 15}[r_name]
    
    if st.button("🔍 KI: Fläche messen"):
        if client and bild:
            try:
                # Das neue Modell-Format für 2026
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[f"Wie groß ist der Raum '{r_name}' in m2? Antworte nur mit der Zahl.", bild]
                )
                import re
                zahlen = re.findall(r"\d+\.?\d*", response.text)
                if zahlen:
                    st.session_state['ki_flaeche'] = float(zahlen[0])
                    st.success(f"Erkannt: {st.session_state['ki_flaeche']} m2")
            except Exception as e:
                st.error(f"KI-Fehler: {e}")
    
    fl = st.number_input("Fläche (m2)", value=float(st.session_state['ki_flaeche']), step=0.1)
    u_w = st.number_input("U-Wert (W/m2K)", value=0.35)
    
    # KfW-Berechnung
    h_last = round(((fl * 1.2) * u_w * (t_soll - p_temp)) + (fl * 2.5 * 0.17 * (t_soll - p_temp)), 0)
    st.info(f"Last: {int(h_last)} W")
    
    if st.button("💾 Speichern"):
        st.session_state['raeume'].append({"Raum": r_name, "Fläche": fl, "T_Soll": t_soll, "Heizlast": h_last})
        st.rerun()

with c2:
    if st.session_state['raeume']:
        df = pd.DataFrame(st.session_state['raeume'])
        st.dataframe(df, width=600)
        pdf = erstelle_kfw_pdf({"name": p_name, "plz": p_plz, "t_aussen": p_temp}, st.session_state['raeume'])
        st.download_button("📄 PDF Download", pdf, "Heizlast.pdf", "application/pdf")
        if st.button("🗑️ Leeren"):
            st.session_state['raeume'] = []; st.rerun()
