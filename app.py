import streamlit as st
from PIL import Image
import google.generativeai as genai
import fitz  
import io    

# --- 1. DEIN API-KEY ---
MEIN_API_KEY = st.secrets["GEMINI_API_KEY"]

st.set_page_config(layout="wide") # Macht die App schön breit
st.title("Meine Profi-Heizlast-App 🏠🤖")
# --- NEU: KURZE BESCHREIBUNG ---
with st.expander("📖 Kurzanleitung: So nutzt du die App", expanded=False):
    st.markdown("""
    **Willkommen beim KI-Heizlast-Assistenten!** Dieses Tool hilft dir, aus alten Grundrissen schnell technische Daten für die Heizungsplanung zu gewinnen.
    
    * **⚡ Schnelle Gebäude-Schätzung:** Ideal für den Ersttermin. Die KI schätzt die Wohnfläche des gesamten Stockwerks und gibt dir eine grobe Heizlast in kW aus.
    * **🔍 Detailliert (Raum-für-Raum):** Hier kannst du gezielt einzelne Räume analysieren lassen. Die KI misst Wandlängen und Fensterbreiten. Du kannst jeden Raum speichern und so eine Liste für das ganze Gebäude erstellen.
    
    *Hinweis: Da die KI "schätzt", solltest du die Werte im Detail-Modus kurz prüfen, bevor du sie speicherst.*
    """)
# --- 2. DAS GEDÄCHTNIS DER APP ---
if 'ki_wandflaeche' not in st.session_state: st.session_state['ki_wandflaeche'] = 0.0
if 'ki_fensterflaeche' not in st.session_state: st.session_state['ki_fensterflaeche'] = 0.0
if 'ki_gesamtflaeche' not in st.session_state: st.session_state['ki_gesamtflaeche'] = 0.0
if 'raeume' not in st.session_state: st.session_state['raeume'] = []

# --- 3. BILD/PDF UPLOAD (Speed-Tuning 🚀) ---
st.header("1. Grundriss hochladen")
hochgeladene_datei = st.file_uploader("Wähle eine Datei (PDF, JPG, PNG)", type=["pdf", "jpg", "png", "jpeg"])

bild = None
if hochgeladene_datei is not None:
    dateiendung = hochgeladene_datei.name.split('.')[-1].lower()
    if dateiendung == "pdf":
        pdf_dokument = fitz.open(stream=hochgeladene_datei.read(), filetype="pdf")
        erste_seite = pdf_dokument.load_page(0)
        # TUNING 1: Auflösung (DPI) von 150 auf 72 halbiert. Das Bild wird viel kleiner!
        pixel_bild = erste_seite.get_pixmap(dpi=72)
        bild = Image.open(io.BytesIO(pixel_bild.tobytes("png")))
    else:
        bild = Image.open(hochgeladene_datei)
        # TUNING 2: Wenn du ein Handyfoto hochlädst, dampfen wir es hier maximal ein
        bild.thumbnail((1024, 1024)) 
    
    with st.expander("Grundriss ein/ausblenden", expanded=True):
        st.image(bild, use_container_width=True)

st.divider()

# --- 4. DIE ZWEI REITER (TABS) ---
tab_schnell, tab_detail = st.tabs(["⚡ Schnelle Gebäude-Schätzung", "🔍 Detailliert (Raum-für-Raum)"])

# ==========================================
# REITER 1: SCHNELLE SCHÄTZUNG
# ==========================================
with tab_schnell:
    st.subheader("Überschlägige Heizlast (Hüllflächenverfahren vereinfacht)")
    
    if bild is not None:
        if st.button("✨ KI: Gesamte Wohnfläche schätzen"):
            try:
                genai.configure(api_key=MEIN_API_KEY)
                modell = genai.GenerativeModel('gemini-2.5-flash') 
                with st.spinner("Gemini berechnet die Gesamtfläche..."):
                    befehl = """
                    Du bist ein Architekt. Analysiere diesen Grundriss. 
                    Schätze die gesamte Wohnfläche dieses Stockwerks in Quadratmetern. 
                    GIB AUSSCHLIESSLICH EINE EINZIGE ZAHL AUS. Keine Einheiten, kein Text.
                    Beispiel: 85.5
                    """
                    antwort = modell.generate_content([befehl, bild])
                    sauberer_text = antwort.text.strip().replace(",", ".")
                    st.session_state['ki_gesamtflaeche'] = float(sauberer_text)
                st.success("Wohnfläche erfolgreich geschätzt!")
            except Exception as fehler:
                st.error(f"Fehler: {fehler}")

    # Datenbank für spezifische Heizlast (Watt pro m²) nach Baujahr
    spez_heizlast_db = {
        "Bis 1977 (ungedämmt)": 150,
        "1978 - 1983 (1. WSchVO)": 100,
        "1984 - 1994 (2. WSchVO)": 85,
        "1995 - 2001 (3. WSchVO)": 65,
        "Ab 2002 (EnEV)": 45
    }
    
    col1, col2 = st.columns(2)
    with col1:
        baujahr_schnell = st.selectbox("Baualtersklasse des Hauses:", list(spez_heizlast_db.keys()))
        watt_pro_qm = spez_heizlast_db[baujahr_schnell]
    with col2:
        gesamtflaeche = st.number_input("Wohnfläche gesamt (in m²)", value=st.session_state['ki_gesamtflaeche'])

    # Die einfache Mathematik für das ganze Haus: Fläche * Watt/m²
    schnelle_heizlast = gesamtflaeche * watt_pro_qm
    
    st.info(f"Der angesetzte Wert liegt bei {watt_pro_qm} W/m².")
    st.error(f"🔥 **Überschlägige Gebäude-Heizlast: {round(schnelle_heizlast / 1000, 2)} kW** ({round(schnelle_heizlast, 0)} Watt)")


# ==========================================
# REITER 2: DETAILLIERT (RAUM-FÜR-RAUM)
# ==========================================
with tab_detail:
    st.subheader("Detaillierte Berechnung (Transmissionswärmeverlust)")
    
    if bild is not None:
        if st.button("✨ KI: Außenwand & Fenster für einen Raum messen"):
            try:
                genai.configure(api_key=MEIN_API_KEY)
                modell = genai.GenerativeModel('gemini-2.5-flash') 
                with st.spinner("Gemini sucht die Wände..."):
                    befehl = """
                    Suche den größten Wohnraum in diesem Grundriss. 
                    Lies die LÄNGE der Außenwand ab und schätze die BREITE der Fenster in Metern.
                    GIB AUSSCHLIESSLICH ZWEI ZAHLEN AUS, getrennt durch ein Semikolon. KEIN TEXT.
                    Beispiel: 6.5;2.1
                    """
                    antwort = modell.generate_content([befehl, bild])
                    sauberer_text = antwort.text.strip().replace(",", ".")
                    ergebnis = sauberer_text.split(";")
                    st.session_state['ki_wandflaeche'] = float(ergebnis[0])
                    st.session_state['ki_fensterflaeche'] = float(ergebnis[1])
                st.success("Werte für den Raum eingetragen!")
            except Exception as fehler:
                st.error(f"Fehler: {fehler}")

    u_wert_db = {
        "Bis 1977": {"wand": 1.4, "fenster": 3.0},
        "1978 - 1983": {"wand": 1.0, "fenster": 2.8},
        "Ab 2002 (EnEV)": {"wand": 0.3, "fenster": 1.3}
    }
    baujahr_detail = st.selectbox("U-Werte nach Baujahr:", list(u_wert_db.keys()))
    u_wand_auto = u_wert_db[baujahr_detail]["wand"]
    u_fenster_auto = u_wert_db[baujahr_detail]["fenster"]

    raum_name = st.text_input("Name des Raumes:", value="Zimmer 3")

    col3, col4 = st.columns(2)
    with col3:
        wandlaenge = st.number_input("Länge der Außenwand (in m)", value=st.session_state['ki_wandflaeche'])
        raumhoehe = st.number_input("Raumhöhe (in m)", value=2.50)
    with col4:
        fensterbreite = st.number_input("Breite der Fenster (in m)", value=st.session_state['ki_fensterflaeche'])
        fensterhoehe = st.number_input("Fensterhöhe (in m)", value=1.30)

    # Mathematik für den Raum
    temp_diff = 20 - (-10) # 20°C innen, -10°C außen
    wand_brutto = wandlaenge * raumhoehe
    fensterflaeche = fensterbreite * fensterhoehe
    netto_wand = wand_brutto - fensterflaeche

    verlust_wand = netto_wand * u_wand_auto * temp_diff
    verlust_fenster = fensterflaeche * u_fenster_auto * temp_diff
    gesamt_verlust = round(verlust_wand + verlust_fenster, 2)

    if st.button("💾 Diesen Raum speichern"):
        st.session_state['raeume'].append({
            "Raum": raum_name,
            "Wand (m)": wandlaenge,
            "Fenster (m²)": round(fensterflaeche, 2),
            "Heizlast (W)": gesamt_verlust
        })
        st.success("Gespeichert!")

    # Tabelle anzeigen
    if len(st.session_state['raeume']) > 0:
        import pandas as pd # Importieren wir hier kurz für die Tabelle
        df = pd.DataFrame(st.session_state['raeume'])
        st.dataframe(df, use_container_width=True)
        
        gesamtheizlast = sum(raum["Heizlast (W)"] for raum in st.session_state['raeume'])
        st.error(f"🔥 **Summe der erfassten Räume: {round(gesamtheizlast, 2)} Watt**")

        # --- NEU: DOWNLOAD BUTTON ---
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Liste als Excel/CSV herunterladen",
            data=csv,
            file_name=f"Heizlast_{raum_name}.csv",
            mime='text/csv',
        )

        if st.button("🗑️ Liste leeren"):
            st.session_state['raeume'] = []
            st.rerun()

