import streamlit as st
from PIL import Image
from google import genai
import fitz  
import io    
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --- 1. KONFIGURATION & API ---
# Der Key kommt aus den Streamlit Secrets (Tresor)
api_key = st.secrets.get("GEMINI_API_KEY", "")

# Initialisierung des neuen Google GenAI Clients
client = genai.Client(api_key=api_key) if api_key else None

st.set_page_config(layout="wide", page_title="KfW Heizlast-Assistent 2026")

# Speicher für die Räume
if 'raeume' not in st.session_state: st.session_state['raeume'] = []
if 'ki_flaeche' not in st.session_state: st.session_state['ki_flaeche'] = 0.0

# --- 2. PDF FUNKTION (FÜR KFW NACHWEIS) ---
def erstelle_kfw_pdf(projekt, raum_liste):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    h = A4[1]
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, h - 50, "KfW-Heizlastprotokoll (Verfahren B)")
    p.setFont("Helvetica", 10)
    p.drawString(50, h - 70, f"Projekt: {projekt['name']} | PLZ: {projekt['plz']} | Norm-Außentemp: {projekt['t_aussen']}°C")
    
    y = h - 120
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Raum")
    p.drawString(180, y, "Fläche")
    p.drawString(260, y, "Soll-Temp")
    p.drawString(350, y, "Heizlast (W)")
    p.line(50, y-5, 550, y-5)
    
    y -= 25
    summe = 0
    p.setFont("Helvetica", 10)
    for r in raum_liste:
        p.drawString(50, y, f"{r['Raum']}")
        p.drawString(180, y, f"{r['Fläche']} m²")
        p.drawString(260, y, f"{r['T_Soll']} °C")
        p.drawString(350, y, f"{int(r['Heizlast'])} W")
        summe += r['Heizlast']
        y -= 20
        if y < 50: p.showPage(); y = h - 50

    p.line(50, y, 550, y)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(300, y-25, f"Gesamte Gebäudeheizlast: {int(summe)} Watt")
    
    p.showPage()
    p.save()
    return buffer.getvalue()

# --- 3. BENUTZEROBERFLÄCHE ---
st.title("🏠 KfW-Heizlast-Tool (Gemini 3 Edition)")

col_a, col_b, col_c = st.columns(3)
with col_a: p_name = st.text_input("Kunde / Projekt", "Müller")
with col_b: p_plz = st.text_input("PLZ Objekt", "12345")
with col_c: p_temp = st.number_input("Norm-Außentemp. (°C)", value=-12)

st.divider()

# Plan Upload
file = st.file_uploader("Grundriss hochladen", type=["pdf", "jpg", "png", "jpeg"])
bild = None
if file:
    if file.name.lower().endswith("pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        pix = doc.load_page(0).get_pixmap(dpi=150)
        bild = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        bild = Image.open(file)
    st.image(bild, caption="Plan-Vorschau", width=800)

st.divider()

# Erfassung
c1, c2 = st.columns([1, 2])
with c1:
    st.subheader("Raum-Details")
    r_name = st.selectbox("Raumtyp", ["Wohnen", "Küche", "Bad", "Schlafen", "Kind", "Flur", "WC"])
    t_soll = {"Wohnen": 20, "Küche": 20, "Bad": 24, "Schlafen": 18, "Kind": 20, "Flur": 15, "WC": 20}[r_name]
    
    if st.button("🔍 KI: Fläche messen"):
        if client and bild:
            with st.spinner("Gemini 3 analysiert den Plan..."):
                try:
                    # Hier nutzen wir das Modell aus deinem Dashboard
                    response = client.models.generate_content(
                        model='gemini-3-flash',
                        contents=[f"Analysiere diesen Grundriss. Wie groß ist der Raum '{r_name}' in m²? Gib nur die nackte Zahl aus.", bild]
                    )
                    # Zahl aus dem Text extrahieren
                    import re
                    zahlen = re.findall(r"\d+\.?\d*", response.text)
                    if zahlen:
                        st.session_state['ki_flaeche'] = float(zahlen[0])
                        st.success(f"KI hat {st.session_state['ki_flaeche']} m² gefunden.")
                    else:
                        st.warning("KI konnte keine eindeutige Zahl lesen.")
                except Exception as e:
                    st.error(f"Schnittstellen-Fehler: {e}")
        else:
            st.error("Bitte API-Key in Secrets hinterlegen und Plan hochladen.")

    fl = st.number_input("Fläche (m²)", value=float(st.session_state['ki_flaeche']), step=0.1)
    u_w = st.number_input("U-Wert Wand (W/m²K)", value=0.35, help="Standard Neubau/Saniert ca. 0.3-0.4")
    
    # Vereinfachte Berechnung nach KfW-Standard (Transmission + Lüftung)
    # Formel: (Fläche * 1.2 * U * DeltaT) + (Volumen * 0.5 * 0.34 * DeltaT)
    delta_t = t_soll - p_temp
    h_last = round(((fl * 1.2) * u_w * delta_t) + (fl * 2.5 * 0.17 * delta_t), 0)
    
    st.metric("Heizlast für diesen Raum", f"{int(h_last)} W")
    
    if st.button("💾 Raum speichern"):
        st.session_state['raeume'].append({"Raum": r_name, "Fläche": fl, "T_Soll": t_soll, "Heizlast": h_last})
        st.success(f"{r_name} hinzugefügt.")
        st.rerun()

with c2:
    st.subheader("Zusammenfassung / Export")
    if st.session_state['raeume']:
        df = pd.DataFrame(st.session_state['raeume'])
        st.table(df)
        
        summe = df['Heizlast'].sum()
        st.error(f"### Gesamt-Heizlast: {int(summe)} Watt")
        
        # PDF Erzeugung
        pdf_file = erstelle_kfw_pdf({"name": p_name, "plz": p_plz, "t_aussen": p_temp}, st.session_state['raeume'])
        st.download_button(
            label="📄 KfW-Protokoll als PDF herunterladen",
            data=pdf_file,
            file_name=f"Heizlast_{p_name}.pdf",
            mime="application/pdf"
        )
        
        if st.button("🗑️ Liste leeren"):
            st.session_state['raeume'] = []
            st.rerun()
