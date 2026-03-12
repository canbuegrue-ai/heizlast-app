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
    # Wir laden den Key und versuchen sofort eine Test-Verbindung
    MEIN_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=MEIN_API_KEY)
except:
    MEIN_API_KEY = ""

st.set_page_config(layout="wide", page_title="KfW Heizlast-Assistent")

# --- 2. SESSION STATE ---
if 'raeume' not in st.session_state: st.session_state['raeume'] = []
if 'ki_flaeche' not in st.session_state: st.session_state['ki_flaeche'] = 0.0

# --- 3. PDF FUNKTION ---
def erstelle_kfw_pdf(projekt_daten, raum_liste):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width_a4, height_a4 = A4
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height_a4 - 50, "KfW-Heizlastprotokoll & Hydraulischer Abgleich")
    p.setFont("Helvetica", 10)
    p.drawString(50, height_a4 - 70, f"Projekt: {projekt_daten['name']} | Ort: {projekt_daten['plz']}")
    p.drawString(50, height_a4 - 85, f"Norm-Außentemperatur: {projekt_daten['t_aussen']} Grad Celsius")
    
    y = height_a4 - 130
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Raum")
    p.drawString(150, y, "Flaeche (m2)")
    p.drawString(220, y, "Soll-Temp (C)")
    p.drawString(320, y, "Heizlast (W)")
    p.line(50, y-5, 550, y-5)
    y -= 25
    
    gesamtsumme = 0
    p.setFont("Helvetica", 10)
    for r in raum_liste:
        p.drawString(50, y, str(r['Raum']))
        p.drawString(150, y, str(r['Fläche']))
        p.drawString(220, y, str(r['T_Soll']))
        p.drawString(320, y, str(int(r['Heizlast'])))
        gesamtsumme += r['Heizlast']
        y -= 20
    
    p.line(50, y, 550, y)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(320, y-20, f"Gesamt: {int(gesamtsumme)} Watt")
    p.showPage()
    p.save()
    return buffer.getvalue()

# --- 4. HAUPT-APP ---
st.title("🏠 KfW-Heizlast-Protokoll Pro")

col_a, col_b, col_c = st.columns(3)
with col_a:
    projekt_name = st.text_input("Bauvorhaben / Kunde", "Müller - Neubau")
with col_b:
    plz = st.text_input("PLZ des Objekts", "12345")
with col_c:
    t_aussen = st.number_input("Norm-Außentemperatur (Grad)", value=-12)

st.divider()

hochgeladene_datei = st.file_uploader("Grundriss hochladen", type=["pdf", "jpg", "png", "jpeg"])
bild = None
if hochgeladene_datei:
    if hochgeladene_datei.name.lower().endswith("pdf"):
        doc = fitz.open(stream=hochgeladene_datei.read(), filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=100)
        bild = Image.open(io.BytesIO(pix.tobytes("png")))
    else:
        bild = Image.open(hochgeladene_datei)
    
    # NEU: 'width' statt 'use_container_width' für 2026er Standard
    st.image(bild, caption="Plan-Vorschau", width="stretch")

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    raum_name = st.selectbox("Raumtyp", ["Wohnen", "Küche", "Bad", "Schlafen", "Kind", "Flur", "WC"])
    t_soll = {"Wohnen": 20, "Küche": 20, "Bad": 24, "Schlafen": 18, "Kind": 20, "Flur": 15, "WC": 20}[raum_name]
    
    if st.button("🔍 KI: Fläche messen"):
        if bild and MEIN_API_KEY:
            try:
                # Wir probieren das stabilste 1.5-Flash Modell
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"Guck dir den Plan an. Wie groß ist der Raum '{raum_name}' in m2? Antworte nur mit der Zahl."
                res = model.generate_content([prompt, bild])
                
                # Zahl extrahieren
                import re
                zahlen = re.findall(r"[-+]?\d*\.\d+|\d+", res.text)
                if zahlen:
                    st.session_state['ki_flaeche'] = float(zahlen[0].replace(",", "."))
                    st.success(f"KI erkannt: {st.session_state['ki_flaeche']} m2")
                else:
                    st.warning("KI konnte keine Zahl im Plan finden.")
            except Exception as e:
                # Falls ein echter Fehler kommt (z.B. Region-Lock), zeigen wir ihn kurz an
                st.error("KI-Schnittstelle antwortet nicht. Bitte Fläche manuell tippen.")
                print(f"DEBUG: {e}") # Erscheint in deinen Logs

    flaeche = st.number_input("Raumfläche (m2)", value=float(st.session_state['ki_flaeche']), step=0.1)
    hoehe = st.number_input("Raumhöhe (m)", value=2.5)
    u_wert = st.number_input("U-Wert (W/m2K)", value=0.35)

    delta_t = t_soll - t_aussen
    heizlast = round(((flaeche * 1.2) * u_wert * delta_t) + (flaeche * hoehe * 0.17 * delta_t), 0)
    st.info(f"Last: {int(heizlast)} Watt")
    
    if st.button("💾 Raum speichern"):
        st.session_state['raeume'].append({"Raum": raum_name, "Fläche": flaeche, "T_Soll": t_soll, "Heizlast": heizlast})
        st.rerun()

with col2:
    if st.session_state['raeume']:
        df = pd.DataFrame(st.session_state['raeume'])
        st.dataframe(df, width="stretch")
        
        pdf_data = erstelle_kfw_pdf({"name": projekt_name, "plz": plz, "t_aussen": t_aussen}, st.session_state['raeume'])
        st.download_button("📄 KfW-PDF Herunterladen", data=pdf_data, file_name="Heizlast.pdf", mime="application/pdf")
        
        if st.button("🗑️ Liste leeren"):
            st.session_state['raeume'] = []
            st.rerun()
