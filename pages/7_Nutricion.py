import streamlit as st
import google.generative_ai as genai
import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- ⚙ CONFIGURACIÓN ---
# Configura tu página
st.set_page_config(
    page_title="NutriScan AI",
    page_icon="🥑",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Estilos CSS para intentar imitar "App Móvil"
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        height: 3em;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 10px;
    }
    /* Ocultar menú hamburguesa y footer para limpieza */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 🔑 API KEY ---
# En Streamlit Cloud, esto va en los "Secrets". Localmente puedes ponerla directa (no recomendado para compartir).
# st.secrets["GOOGLE_API_KEY"]
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    api_key = st.text_input("Introduce tu Google API Key:", type="password")

if not api_key:
    st.warning("⚠️ Por favor, introduce tu API Key para continuar.")
    st.stop()

genai.configure(api_key=api_key)

# --- 🧠 LÓGICA IA ---

def analyze_image(image_data):
    """Envía la imagen a Gemini Flash para análisis nutricional."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    Actúa como nutricionista experto. Analiza esta imagen de comida.
    Identifica el plato y estima sus valores nutricionales.
    
    IMPORTANTE: Devuelve SIEMPRE sodium, potassium, calcium, magnesium en "minerals" (aunque sean 0).
    Si ves otros importantes, ponlos en "other_minerals".
    
    Responde SOLO con este JSON válido (sin markdown ```json):
    {
      "foodName": "Nombre del plato",
      "estimatedWeight_g": numero_peso,
      "calories": numero_calorias,
      "macros": { "protein_g": numero, "carbs_g": numero, "fat_g": numero },
      "minerals": { "sodium_mg": numero, "potassium_mg": numero, "calcium_mg": numero, "magnesium_mg": numero },
      "analysis": "Breve comentario de 1 frase."
    }
    """
    
    try:
        response = model.generate_content([prompt, image_data])
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        st.error(f"Error analizando imagen: {e}")
        return None

def ask_coach(history_data):
    """Consulta al Coach IA."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Eres un entrenador personal para un deportista con FA Vagal.
    Datos de hoy: {json.dumps(history_data)}
    Dame 3 consejos breves y técnicos para recuperación hoy. Usa emojis.
    """
    response = model.generate_content(prompt)
    return response.text

def get_recipes(food_name):
    """Pide recetas."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"Dame 2 ideas de recetas rápidas y saludables usando: {food_name}. Sé breve."
    response = model.generate_content(prompt)
    return response.text

# --- 💾 GESTIÓN DE ESTADO (MEMORIA TEMPORAL) ---
if 'history' not in st.session_state:
    st.session_state.history = []
if 'current_analysis' not in st.session_state:
    st.session_state.current_analysis = None

# --- 📱 INTERFAZ DE USUARIO ---

# Título
st.title("🥑 NutriScan AI")
st.caption("Tu escáner de macros y minerales para FA Vagal")

# Pestañas de navegación
tab1, tab2 = st.tabs(["📸 Escáner", "📅 Diario"])

# --- PESTAÑA 1: ESCÁNER ---
with tab1:
    st.write("### ¿Qué comemos hoy?")
    
    input_method = st.radio("Método de entrada:", ["Cámara", "Subir Foto"], horizontal=True, label_visibility="collapsed")
    
    image_file = None
    if input_method == "Cámara":
        image_file = st.camera_input("Haz una foto")
    else:
        image_file = st.file_uploader("Sube una imagen", type=['jpg', 'png', 'jpeg'])

    if image_file:
        # Convertir a imagen PIL para mostrar y procesar
        from PIL import Image
        img = Image.open(image_file)
        
        if st.button("🔍 Analizar Alimento", type="primary"):
            with st.spinner("La IA está pesando los ingredientes..."):
                result = analyze_image(img)
                if result:
                    st.session_state.current_analysis = result
                    st.success("¡Análisis completado!")

    # MOSTRAR RESULTADOS
    if st.session_state.current_analysis:
        data = st.session_state.current_analysis
        
        st.divider()
        st.header(data['foodName'])
        st.caption(f"⚖️ {data['estimatedWeight_g']}g • 🔥 {data['calories']} Kcal")
        
        # Gráfico de Macros (Donut)
        labels = ['Proteína', 'Carbos', 'Grasa']
        values = [data['macros']['protein_g'], data['macros']['carbs_g'], data['macros']['fat_g']]
        colors = ['#10b981', '#f59e0b', '#ef4444']
        
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.5, marker_colors=colors)])
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=200, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Macros numéricos
        c1, c2, c3 = st.columns(3)
        c1.metric("Prot", f"{data['macros']['protein_g']}g")
        c2.metric("Carb", f"{data['macros']['carbs_g']}g")
        c3.metric("Grasa", f"{data['macros']['fat_g']}g")
        
        st.subheader("💧 Minerales")
        m1, m2 = st.columns(2)
        m1.info(f"**Sodio:** {data['minerals']['sodium_mg']} mg")
        m2.success(f"**Potasio:** {data['minerals']['potassium_mg']} mg")
        m3, m4 = st.columns(2)
        m3.warning(f"**Calcio:** {data['minerals']['calcium_mg']} mg")
        m4.info(f"**Magnesio:** {data['minerals']['magnesium_mg']} mg")
        
        col_btn1, col_btn2 = st.columns(2)
        
        if col_btn1.button("💾 Guardar en Diario"):
            # Añadir fecha
            entry = data.copy()
            entry['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state.history.append(entry)
            st.toast("Guardado en el historial", icon="✅")
            st.session_state.current_analysis = None # Reset
            st.rerun()
            
        if col_btn2.button("👨‍🍳 Ideas Recetas"):
            ideas = get_recipes(data['foodName'])
            st.info(ideas)

# --- PESTAÑA 2: DIARIO ---
with tab2:
    if not st.session_state.history:
        st.info("No hay registros hoy. ¡Escanea algo!")
    else:
        # Calcular totales
        df = pd.DataFrame(st.session_state.history)
        total_cal = sum(d['calories'] for d in st.session_state.history)
        total_na = sum(d['minerals']['sodium_mg'] for d in st.session_state.history)
        total_k = sum(d['minerals']['potassium_mg'] for d in st.session_state.history)
        
        # Tarjeta Resumen
        st.markdown(f"""
        <div class="metric-card">
            <h3>Total Hoy</h3>
            <h1 style="color: #15803d;">{total_cal} Kcal</h1>
            <p>Na: {total_na}mg | K: {total_k}mg</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Botón Coach
        if st.button("✨ Análisis del Coach IA"):
            with st.spinner("Analizando tu día..."):
                advice = ask_coach(st.session_state.history)
                st.success(advice)
        
        st.subheader("Historial")
        for i, item in enumerate(reversed(st.session_state.history)):
            with st.expander(f"{item['timestamp'][-5:]} - {item['foodName']} ({item['calories']} kcal)"):
                st.write(f"**Macros:** P: {item['macros']['protein_g']}g | C: {item['macros']['carbs_g']}g | G: {item['macros']['fat_g']}g")
                st.write(f"**Minerales:** Na: {item['minerals']['sodium_mg']} | K: {item['minerals']['potassium_mg']}")
                if st.button("Borrar", key=f"del_{i}"):
                    st.session_state.history.pop(-(i+1))
                    st.rerun()