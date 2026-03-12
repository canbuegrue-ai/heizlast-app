import streamlit as st
from PIL import Image
import google.generativeai as genai
import fitz  
import io    
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --- 1. KONFIGURATION & SECRETS ---
try:
    MEIN_API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    MEIN_API_KEY = "AIzaSyDZtWX4sK-SkYPN2Ct0iEHsghoZsJTA394"

st.set_page_config(layout="wide", page_title="KfW Heizlast-Assistent")

# --- 2. SESSION STATE (DAS GEDÄCHTNIS) ---
if 'raeume' not in st.session_state: st.session_state['raeume'] = []
if 'ki_flaeche' not in st.session_state: st.session_state['ki_flaeche'] = 0.0

# --- 3. FUNKTION: PDF PROTOKOLL ERSTELLEN ---
def erstelle_kfw_pdf(projekt_daten, raum_liste):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Header
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "KfW-Heizlastprotokoll & Hydraulischer Abgleich")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 70, f"Projekt: {projekt_daten['name']} | Ort: {projekt_daten['plz']}")
    p.drawString(50, height - 85, f"Norm-Außentemperatur: {projekt_daten['t_aussen']} °C")
    
    # Tabelle Header
    y = height - 130
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Raum")
    p.drawString(150, y, "Fläche (m²)")
    p.drawString(220, y, "Soll-Temp (°C)")
    p.drawString(320, y, "Heizlast (W)")
    p.drawString(420, y, "Spez. Last (W/m²)")
    
    p.line(50, y-5, 550, y-5)
    y -= 25
    
    # Daten
    p.setFont("Helvetica", 10)
    gesamtsumme = 0
    for r in raum_liste:
        p.drawString(50, y, str(r['Raum']))
        p.drawString(150, y, str(r['Fläche']))
        p.drawString(220, y, str(r['T_Soll']))
        p.drawString(320, y, str(r['Heizlast']))
        p.drawString(420, y, str(round(r['Heizlast']/r['Fläche'], 1)))
        gesamtsumme += r['Heizlast']
        y -= 20
        if y < 50: # Neue Seite falls voll
            p.showPage()
            y = height - 50

    p.line(50, y, 550, y)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(320, y-20, f"Gesamt: {gesamtsumme} Watt")
    
    p.showPage()
    p.save()
    return buffer.getvalue()

# --- 4. HAUPT-APP ---
st.title("🏠 KfW-Heizlast-Protokoll Pro")

with st.expander("📖 Anleitung für KfW-Nachweis", expanded=False):
    st.write("""
    Dieses Tool erstellt eine raumweise Heizlastberechnung nach DIN EN 12831 (vereinfacht).
    1. Stammdaten eingeben (PLZ bestimmt Außentemperatur).
    2. Grundriss hochladen.
    3. Räume einzeln erfassen (KI hilft bei der Flächenmessung).
    4. PDF-Protokoll für KfW / Hydraulischen Abgleich exportieren.
    """)

# Stammdaten
col_a, col_b, col_c = st.columns(3)
with col_a:
    projekt_name = st.text_input("Bauvorhaben / Kunde", "Müller - Neubau")
with col_b:
    plz = st.text_input("PLZ des Objekts", "12345")
with col_c:
    t_aussen = st.number_input("Norm-Außentemperatur (°C)", value=-12)

st.divider()

# Upload
hochgeladene_datei = st.file_uploader("Grundriss hochladen (PDF/Bild)", type=["pdf", "jpg", "png", "jpeg"])
bild = None
if hochgeladene_datei:
    if hochgeladene_datei.name.lower().endswith("pdf"):
        doc = fitz.open(stream=hochgeladene_datei.read(), filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=72) # Schnelles Laden
        bild = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        bild = Image.open(hochgeladene_datei)
        bild.thumbnail((1024, 1024))
    st.image(bild, caption="Geladener Plan", use_container_width=True)

st.divider()

# Raumweise Erfassung
st.subheader("🚪 Raumweise Berechnung")
col1, col2 = st.columns([1, 2])

with col1:
    raum_name = st.selectbox("Raumtyp", ["Wohnen", "Küche", "Bad", "Schlafen", "Kind", "Flur", "WC"])
    t_soll = {"Wohnen": 20, "Küche": 20, "Bad": 24, "Schlafen": 18, "Kind": 20, "Flur": 15, "WC": 20}[raum_name]
    
    if st.button("🔍 KI: Fläche messen"):
        if bild and MEIN_API_KEY:
            genai.configure(api_key=MEIN_API_KEY)
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"Suche den Raum '{raum_name}' im Plan. Berechne die Grundfläche in m². Gib NUR die Zahl aus."
            res = model.generate_content([prompt, bild])
            try:
                st.session_state['ki_flaeche'] = float(res.text.strip().replace(",", "."))
            except: st.error("KI konnte Fläche nicht lesen.")
    
    flaeche = st.number_input("Raumfläche (m²)", value=st.session_state['ki_flaeche'])
    hoehe = st.number_input("Raumhöhe (m)", value=2.5)
    u_wert = st.number_input("Mittlerer U-Wert Bauteile (W/m²K)", value=0.35, help="Durchschnitt aller Außenwände/Fenster")

    # Berechnung nach Norm
    volumen = flaeche * hoehe
    delta_t = t_soll - t_aussen
    # Q_trans = Fläche_Hüllflächen * U * delta_t (vereinfacht: Fläche_Raum * 1.2 Korrektur für Hülle)
    q_trans = (flaeche * 1.2) * u_wert * delta_t 
    q_lueft = volumen * 0.5 * 0.34 * delta_t # 0.5-facher Luftwechsel
    heizlast_raum = round(q_trans + q_lueft, 0)
    
    st.info(f"Ergebnis: {heizlast_raum} Watt")
    
    if st.button("💾 Raum speichern"):
        st.session_state['raeume'].append({
            "Raum": raum_name, "Fläche": flaeche, 
            "T_Soll": t_soll, "Heizlast": heizlast_raum
        })
        st.rerun()

with col2:
    if st.session_state['raeume']:
        df = pd.DataFrame(st.session_state['raeume'])
        st.table(df)
        
        summe = df['Heizlast'].sum()
        st.metric("Gesamtheizlast Gebäude", f"{summe} Watt")
        
        # PDF DOWNLOAD
        projekt_daten = {"name": projekt_name, "plz": plz, "t_aussen": t_aussen}
        pdf_data = erstelle_kfw_pdf(projekt_daten, st.session_state['raeume'])
        
        st.download_button(
            label="📄 KfW-Protokoll (PDF) herunterladen",
            data=pdf_data,
            file_name=f"Heizlast_{projekt_name}.pdf",
            mime="application/pdf"
        )
        
        if st.button("🗑️ Liste leeren"):
            st.session_state['raeume'] = []
            st.rerun()
