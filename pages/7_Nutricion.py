import streamlit as st
import requests
import json
import base64
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from PIL import Image
from io import BytesIO

# --- ⚙ CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="NutriScan AI - Control de Minerales",
    page_icon="🥑",
    layout="centered"
)

# Estilos CSS para mejorar la legibilidad en móviles
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; font-weight: bold; }
    .metric-card { background-color: #f0f2f6; padding: 20px; border-radius: 15px; text-align: center; margin-bottom: 15px; border: 1px solid #e0e0e0; }
    .advice-box { background-color: #e8f4f8; padding: 15px; border-radius: 10px; border-left: 5px solid #2980b9; margin: 10px 0; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    </style>
""", unsafe_allow_html=True)

# --- 🔑 CONFIGURACIÓN DE API KEY ---
# Intentamos obtenerla de los secretos de Streamlit (nube) o la pedimos en pantalla (local)
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    api_key = st.text_input("🔑 Introduce tu Google API Key para activar la IA:", type="password")

if not api_key:
    st.warning("⚠ Se requiere la clave de API para analizar imágenes y dar consejos.")
    st.stop()

# --- 🧠 MOTOR DE INTELIGENCIA ARTIFICIAL (GEMINI REST) ---

def call_gemini_api(prompt, image=None):
    """
    Función robusta para conectar con Gemini 2.0 Flash vía HTTPS directo.
    Compatible con Python 3.13 al no depender de librerías externas complejas.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    parts = [{"text": prompt}]
    
    if image:
        # Convertimos la imagen a formato que la IA entiende (Base64)
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": img_str
            }
        })

    payload = {"contents": [{"parts": parts}]}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        st.error(f"❌ Error de conexión con Gemini: {str(e)}")
        return None

def analyze_food(image_input):
    """Analiza la imagen para extraer macros y minerales."""
    prompt = """
    Analiza esta imagen como un nutricionista clínico experto. 
    1. Identifica el alimento.
    2. Calcula ración estándar en gramos.
    3. Devuelve calorías, Proteína, Carbohidratos y Grasa.
    4. IMPORTANTE: Devuelve mg de Sodio (sodium), Potasio (potassium), Calcio (calcium) y Magnesio (magnesium).
    
    Responde ÚNICAMENTE con este formato JSON:
    {
      "foodName": "Nombre plato",
      "weight_g": 250,
      "calories": 450,
      "macros": {"protein_g": 20, "carbs_g": 50, "fat_g": 15},
      "minerals": {"sodium_mg": 400, "potassium_mg": 350, "calcium_mg": 100, "magnesium_mg": 40},
      "analysis": "Breve nota sobre el balance de este plato."
    }
    """
    raw_response = call_gemini_api(prompt, image_input)
    if raw_response:
        try:
            # Limpiar posibles marcas de markdown de la IA
            clean_json = raw_response.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except:
            st.error("La IA tuvo un problema de formato. Por favor, intenta de nuevo.")
    return None

# --- 💾 GESTIÓN DE DATOS ---
if 'nutri_history' not in st.session_state:
    st.session_state.nutri_history = []
if 'last_analysis' not in st.session_state:
    st.session_state.last_analysis = None

# --- 📱 INTERFAZ DE USUARIO ---

st.title("🥑 NutriScan AI")
st.write(f"Hola Jose, monitor de nutrición y minerales.")

tabs = st.tabs(["📸 Escáner", "📅 Diario de Hoy", "🧠 Coach IA"])

# TRAYECTO 1: ESCÁNER
with tabs[0]:
    st.subheader("Registrar Alimento")
    metodo = st.radio("Origen de la imagen:", ["Cámara en vivo", "Galería/Archivo"], horizontal=True)
    
    if metodo == "Cámara en vivo":
        foto = st.camera_input("Enfoca tu plato")
    else:
        foto = st.file_uploader("Sube una foto de tu comida", type=['jpg', 'jpeg', 'png'])

    if foto:
        img = Image.open(foto)
        if st.button("🔍 ANALIZAR AHORA", type="primary"):
            with st.spinner("La IA está analizando los componentes..."):
                resultado = analyze_food(img)
                if resultado:
                    st.session_state.last_analysis = resultado
                    st.success("¡Análisis completado!")

    # Mostrar resultados del último análisis
    if st.session_state.last_analysis:
        res = st.session_state.last_analysis
        st.divider()
        st.header(f"🍴 {res['foodName']}")
        
        col_data1, col_data2 = st.columns(2)
        col_data1.metric("🔥 Calorías", f"{res['calories']} kcal")
        col_data2.metric("⚖️ Peso Est.", f"{res['weight_g']} g")

        # Gráfico de Macros
        labels = ['Proteína', 'Carbos', 'Grasa']
        m_values = [res['macros']['protein_g'], res['macros']['carbs_g'], res['macros']['fat_g']]
        fig = go.Figure(data=[go.Pie(labels=labels, values=m_values, hole=.4, marker_colors=['#27ae60', '#f1c40f', '#e74c3c'])])
        fig.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

        st.write("### 💧 Aporte de Minerales")
        min1, min2 = st.columns(2)
        min1.write(f"🧂 **Sodio:** {res['minerals']['sodium_mg']} mg")
        min1.write(f"🍌 **Potasio:** {res['minerals']['potassium_mg']} mg")
        min2.write(f"🦴 **Calcio:** {res['minerals']['calcium_mg']} mg")
        min2.write(f"💊 **Magnesio:** {res['minerals']['magnesium_mg']} mg")

        if st.button("💾 GUARDAR EN MI DIARIO"):
            res['time'] = datetime.now().strftime("%H:%M")
            st.session_state.nutri_history.append(res)
            st.session_state.last_analysis = None
            st.toast("Guardado correctamente", icon="✅")
            st.rerun()

# TRAYECTO 2: DIARIO
with tabs[1]:
    if not st.session_state.nutri_history:
        st.info("Todavía no has registrado nada hoy. ¡Usa la cámara!")
    else:
        # Calcular totales del día
        total_c = sum(i['calories'] for i in st.session_state.nutri_history)
        total_na = sum(i['minerals']['sodium_mg'] for i in st.session_state.nutri_history)
        total_k = sum(i['minerals']['potassium_mg'] for i in st.session_state.nutri_history)
        
        st.markdown(f"""
            <div class="metric-card">
                <p style="margin:0; font-weight:bold; color:#7f8c8d;">CONSUMO TOTAL HOY</p>
                <h1 style="margin:0; color:#2ecc71;">{total_c} <span style="font-size:15px;">Kcal</span></h1>
                <p style="margin:5px 0 0 0;">🧂 Na: {total_na}mg | 🍌 K: {total_k}mg</p>
            </div>
        """, unsafe_allow_html=True)

        st.subheader("Desglose del día")
        for i, item in enumerate(reversed(st.session_state.nutri_history)):
            with st.expander(f"{item['time']} - {item['foodName']} ({item['calories']} kcal)"):
                st.write(f"**Macros:** P: {item['macros']['protein_g']}g | C: {item['macros']['carbs_g']}g | G: {item['macros']['fat_g']}g")
                st.write(f"**Minerales:** Na: {item['minerals']['sodium_mg']}mg | K: {item['minerals']['potassium_mg']}mg")
                if st.button(f"🗑 Eliminar", key=f"del_{i}"):
                    st.session_state.nutri_history.pop(-(i+1))
                    st.rerun()

# TRAYECTO 3: COACH
with tabs[2]:
    st.subheader("Análisis de Salud Deportiva")
    if not st.session_state.nutri_history:
        st.warning("Añade algunas comidas primero para que el Coach pueda analizar tu día.")
    else:
        if st.button("✨ CONSULTAR AL COACH GEMINI"):
            with st.spinner("Analizando balance Na/K y estado mineral..."):
                datos_hoy = json.dumps(st.session_state.nutri_history)
                prompt_coach = f"""
                Actúa como un experto en nutrición deportiva para un atleta de 54 años preocupado por la FA Vagal.
                Datos de comidas de hoy: {datos_hoy}
                
                Analiza:
                1. El balance Sodio/Potasio.
                2. Si el Magnesio es suficiente para la recuperación.
                3. Da 3 consejos breves y técnicos para lo que queda de día o para mañana.
                Usa emojis y sé muy directo.
                """
                consejo = call_gemini_api(prompt_coach)
                if consejo:
                    st.markdown(f'<div class="advice-box">{consejo}</div>', unsafe_allow_html=True)