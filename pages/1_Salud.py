import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Coach IA de Readiness",
    page_icon="💗",
    layout="wide"
)

# --- INICIALIZACIÓN DEL ESTADO DE LA SESIÓN (Para el editor de tema) ---
if 'primary_color' not in st.session_state: st.session_state.primary_color = "#00aaff"
if 'background_color' not in st.session_state: st.session_state.background_color = "#0E1117"
if 'secondary_background_color' not in st.session_state: st.session_state.secondary_background_color = "#1C1E26"
if 'text_color' not in st.session_state: st.session_state.text_color = "#FAFAFA"
if 'card_border_base_color' not in st.session_state: st.session_state.card_border_base_color = "#00aaff"
if 'card_border_alpha' not in st.session_state: st.session_state.card_border_alpha = 34

# --- EDITOR DE TEMA EN LA BARRA LATERAL ---
with st.sidebar.expander("🎨 Editor de Tema en Vivo"):
    st.session_state.primary_color = st.color_picker("Color Primario", st.session_state.primary_color)
    st.session_state.background_color = st.color_picker("Color de Fondo Principal", st.session_state.background_color)
    st.session_state.secondary_background_color = st.color_picker("Fondo Secundario", st.session_state.secondary_background_color)
    st.session_state.text_color = st.color_picker("Color del Texto", st.session_state.text_color)
    st.subheader("Borde de Tarjetas")
    st.session_state.card_border_base_color = st.color_picker("Color del Borde", st.session_state.card_border_base_color, key="border_color_picker")
    st.session_state.card_border_alpha = st.slider("Opacidad del Borde", 0, 255, st.session_state.card_border_alpha)

# --- GENERACIÓN E INYECCIÓN DEL CSS DINÁMICO ---
alpha_hex = f'{st.session_state.card_border_alpha:02x}'
final_border_color = f"{st.session_state.card_border_base_color}{alpha_hex}"
dynamic_css = f"""
<style>
    .main .block-container {{ background-color: {st.session_state.background_color}; }}
    body, .stApp, .stMarkdown, .stWrite, .stMetricLabel, .stMetricDelta, .stHeader, .stSubheader, .css-18e3th9, .css-1d391kg {{ color: {st.session_state.text_color} !important; }}
    .card, [data-testid="stExpander"], .gauge-container {{ background-color: {st.session_state.secondary_background_color} !important; border: 1px solid {final_border_color} !important; border-radius: 10px; padding: 10px; margin-bottom: 10px;}}
    [data-testid="stExpander"] summary, .st-emotion-cache-10trblm a {{ color: {st.session_state.primary_color} !important; }}
    .st-emotion-cache-18e3th9 {{ background-color: {st.session_state.background_color} !important; }}
    .gauge-container {{ background-color: #f1f1f1; border-radius: 5px; padding: 2px; }}
    .gauge-fill {{ height: 24px; border-radius: 5px; text-align: center; color: white; font-weight: bold; line-height: 24px; }}
</style>
"""
st.markdown(dynamic_css, unsafe_allow_html=True)

# --- FUNCIÓN PARA CARGAR CSS EXTERNO ---
def local_css(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"Fichero de estilos '{file_name}' no encontrado. Se usarán los estilos por defecto.")

local_css("style.css")

# --- SECRETOS ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except (FileNotFoundError, KeyError):
    ATHLETE_ID = "i10474"
    API_KEY = "27i9azt55smmhvg1ogc5gmn7x"

# --- LÓGICA DE ANÁLISIS UNIFICADA ---
@st.cache_data(ttl=3600)
def get_wellness_data(start_date, end_date):
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness"
    try:
        response = requests.get(wellness_url, auth=('API_KEY', API_KEY), params=params)
        response.raise_for_status()
        if response.json():
            df = pd.DataFrame(response.json())
            df['id'] = pd.to_datetime(df['id'])
            df.set_index('id', inplace=True)
            return df.sort_index()
        return pd.DataFrame()
    except requests.exceptions.RequestException:
        return pd.DataFrame()

def calculate_baselines(daily_df):
    if daily_df.empty or len(daily_df) < 7:
        return {'recovery': pd.Series(dtype='float64'), 'chronic': pd.Series(dtype='float64'), 'historic': pd.Series(dtype='float64')}
    weekly_df = daily_df[['atl', 'restingHR', 'hrv']].resample('W-SUN').mean().dropna()
    if weekly_df.empty:
        return {'recovery': pd.Series(dtype='float64'), 'chronic': pd.Series(dtype='float64'), 'historic': pd.Series(dtype='float64')}
    
    baselines = {}
    avg_atl = weekly_df['atl'].mean()
    low_load_weeks = weekly_df[weekly_df['atl'] <= avg_atl]
    baselines['recovery'] = low_load_weeks[['restingHR', 'hrv']].mean() if not low_load_weeks.empty else pd.Series(dtype='float64')
    baselines['chronic'] = weekly_df[['restingHR', 'hrv']].tail(4).mean() if len(weekly_df) >= 4 else pd.Series(dtype='float64')
    baselines['historic'] = weekly_df[['restingHR', 'hrv']].tail(8).mean() if len(weekly_df) >= 8 else pd.Series(dtype='float64')
    return baselines

def get_readiness_analysis_v3(selected_date):
    start_date = selected_date - timedelta(days=84)
    end_date = selected_date
    df = get_wellness_data(start_date, end_date)
    if df.empty or pd.to_datetime(selected_date).strftime('%Y-%m-%d') not in df.index.strftime('%Y-%m-%d'):
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}
    
    today_data = df.loc[selected_date.strftime('%Y-%m-%d')]
    past_df = df[df.index < pd.to_datetime(selected_date)]
    
    yesterday_str = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    ctl_ayer, atl_ayer, tsb_ayer = None, None, None
    if pd.to_datetime(yesterday_str) in past_df.index:
        yesterday_data = past_df.loc[yesterday_str]
        ctl_ayer = yesterday_data.get('ctl')
        atl_ayer = yesterday_data.get('atl')
        if pd.notna(ctl_ayer) and pd.notna(atl_ayer):
            tsb_ayer = ctl_ayer - atl_ayer

    hrv_hoy, rhr_hoy, sleep_score_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore')

    score, breakdown = 0, []
    hrv_baseline_28d = past_df['hrv'].tail(28).mean()
    hrv_std_28d = past_df['hrv'].tail(28).std()
    
    if pd.notna(hrv_hoy) and pd.notna(hrv_baseline_28d) and pd.notna(hrv_std_28d) and hrv_std_28d > 0:
        hrv_normal_range_lower = hrv_baseline_28d - (0.75 * hrv_std_28d)
        if hrv_hoy >= hrv_baseline_28d + (0.5 * hrv_std_28d): hrv_points = 45
        elif hrv_hoy >= hrv_normal_range_lower: hrv_points = 30
        elif hrv_hoy >= hrv_baseline_28d - hrv_std_28d: hrv_points = 15
        else: hrv_points = 0
        score += hrv_points
        breakdown.append(f"VFC (HRV): {hrv_hoy:.1f}ms -> {hrv_points} ptos.")
    
    if pd.notna(rhr_hoy):
        rhr_points = 0
        if rhr_hoy <= 45: rhr_points = 35
        elif rhr_hoy <= 48: rhr_points = 25
        elif rhr_hoy <= 52: rhr_points = 10
        score += rhr_points
        breakdown.append(f"FC Reposo: {rhr_hoy:.0f}bpm -> {rhr_points} ptos.")

    if pd.notna(sleep_score_hoy):
        sleep_points = 20 if sleep_score_hoy >= 80 else 10 if sleep_score_hoy >= 70 else 0
        score += sleep_points
        breakdown.append(f"P. Sueño: {sleep_score_hoy:.0f} -> {sleep_points} ptos.")
    
    verdict_text = "✅ LUZ VERDE: Estado óptimo."
    if score < 60: verdict_text = "🚫 LUZ ROJA: Señales de fatiga significativa."
    elif score < 80: verdict_text = "⚠️ LUZ AMARILLA: Estado aceptable."
    
    baselines = calculate_baselines(past_df)
    
    return {
        "verdict": verdict_text, "readiness_score": score, "score_breakdown": breakdown,
        "metrics": { "FC Reposo": {"value": rhr_hoy, "avg7": past_df['restingHR'].tail(7).mean()}, "VFC (HRV)": {"value": hrv_hoy, "avg7": past_df['hrv'].tail(7).mean()}, "Puntuación Sueño": {"value": sleep_score_hoy}},
        "baselines": baselines,
        "load_metrics": {"ctl": ctl_ayer, "atl": atl_ayer, "tsb": tsb_ayer}
    }

# --- FUNCIONES DE LA INTERFAZ ---
def display_gauge(score):
    score_color = "#d9534f" if score < 60 else "#f0ad4e" if score < 80 else "#5cb85c"
    gauge_html = f"""
    <div class="gauge-container">
        <div class="gauge-fill" style="background-color: {score_color}; width: {score}%;">
            {score} / 100
        </div>
    </div>
    """
    st.markdown(gauge_html, unsafe_allow_html=True)

# --- INTERFAZ PRINCIPAL ---
st.title("💗 Estado de Salud y Coaching Diario")
selected_date = st.date_input("Selecciona la fecha de análisis:", datetime.now().date())

if selected_date:
    analysis = get_readiness_analysis_v3(selected_date)

    if "error" in analysis:
        st.error(analysis["error"])
    else:
        load = analysis.get("load_metrics", {})
        ctl, atl, tsb = load.get('ctl'), load.get('atl'), load.get('tsb')

        st.markdown('<div class="card-grid">', unsafe_allow_html=True)
        g_col1, g_col2, g_col3 = st.columns(3)
        with g_col1:
            st.metric(label="Forma (CTL) Ayer", value=f"{ctl:.1f}" if pd.notna(ctl) else "N/A")
        with g_col2:
            st.metric(label="Fatiga (ATL) Ayer", value=f"{atl:.1f}" if pd.notna(atl) else "N/A")
        with g_col3:
            st.metric(label="Frescura (TSB) Ayer", value=f"{tsb:.1f}" if pd.notna(tsb) else "N/A", 
                      delta=f"{tsb/ctl*100:.0f}% de Forma" if pd.notna(tsb) and pd.notna(ctl) and ctl != 0 else "", 
                      delta_color="off")
        st.markdown('</div>', unsafe_allow_html=True)
        
        m, b = analysis.get("metrics", {}), analysis.get("baselines", {})
        hrv_hoy, rhr_hoy, sleep_hoy = m.get('VFC (HRV)', {}).get('value'), m.get('FC Reposo', {}).get('value'), m.get('Puntuación Sueño', {}).get('value')
        
        st.markdown("---")
        st.subheader("💡 Coaching del Día")
        frase = "Analizando tus datos..."
        if pd.notna(hrv_hoy) and pd.notna(rhr_hoy) and b.get('historic') is not None and not b.get('historic').empty:
            hrv_vs_hist, rhr_vs_hist = hrv_hoy - b['historic'].get('hrv', hrv_hoy), rhr_hoy - b['historic'].get('restingHR', rhr_hoy)
            if hrv_vs_hist >= 0 and rhr_vs_hist <= 0: frase = "✅ **Tu cuerpo está listo para rendir.**"
            elif hrv_vs_hist < -3 and rhr_vs_hist > 1: frase = "🚫 **Señales claras de fatiga.** Prioriza la recuperación."
            elif hrv_vs_hist < 0 and rhr_vs_hist > 0: frase = "⚠️ **Fatiga presente, pero controlada.** Considera un entrenamiento más ligero."
            else: frase = "🔄 **Estado general estable.** Sigue con el plan."
        st.info(frase)

        st.markdown("##### Vistazo Rápido del Día")
        col1, col2, col3 = st.columns(3)
        with col1:
            hrv_rec_baseline = b.get('recovery', pd.Series()).get('hrv', hrv_hoy)
            texto_hrv = "🧬 **HRV:** N/A"
            if pd.notna(hrv_hoy) and pd.notna(hrv_rec_baseline):
                if hrv_hoy >= hrv_rec_baseline: texto_hrv = "🧬 **HRV:** ✅ Óptimo"
                elif hrv_hoy >= hrv_rec_baseline * 0.95: texto_hrv = "🧬 **HRV:** ⚠️ Estable"
                else: texto_hrv = "🧬 **HRV:** 🚫 Bajo"
            st.markdown(f'<div class="card">{texto_hrv}</div>', unsafe_allow_html=True)
            
        with col2:
            rhr_rec_baseline = b.get('recovery', pd.Series()).get('restingHR', rhr_hoy)
            texto_rhr = "❤️ **RHR:** N/A"
            if pd.notna(rhr_hoy) and pd.notna(rhr_rec_baseline):
                if rhr_hoy <= rhr_rec_baseline: texto_rhr = "❤️ **RHR:** ✅ Óptimo"
                elif rhr_hoy <= rhr_rec_baseline + 2: texto_rhr = "❤️ **RHR:** ⚠️ Ligeramente elevado"
                else: texto_rhr = "❤️ **RHR:** 🚫 Elevado"
            st.markdown(f'<div class="card">{texto_rhr}</div>', unsafe_allow_html=True)

        with col3:
            texto_sleep = "🛌 **Sueño:** N/A"
            if pd.notna(sleep_hoy):
                if sleep_hoy >= 80: texto_sleep = "🛌 **Sueño:** ✅ Bueno"
                elif sleep_hoy >= 70: texto_sleep = "🛌 **Sueño:** ⚠️ Regular"
                else: texto_sleep = "🛌 **Sueño:** 🚫 Pobre"
            st.markdown(f'<div class="card">{texto_sleep}</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("📈 Puntuación y Métricas Detalladas del Día")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**Veredicto General: {analysis.get('verdict', 'N/A')}**")
            display_gauge(analysis.get('readiness_score', 0))
        with col2:
            sub_col1, sub_col2, sub_col3 = st.columns(3)
            with sub_col1: st.metric("VFC (HRV)", f"{hrv_hoy:.1f} ms" if pd.notna(hrv_hoy) else "N/A")
            with sub_col2: st.metric("FC Reposo", f"{rhr_hoy:.0f} bpm" if pd.notna(rhr_hoy) else "N/A")
            with sub_col3: st.metric("Puntuación Sueño", f"{sleep_hoy:.0f}" if pd.notna(sleep_hoy) else "N/A")
        
        st.markdown("---")
        st.header("❤️ Tus Líneas Basales de Referencia")
        b_col1, b_col2, b_col3 = st.columns(3)
        with b_col1:
            st.subheader("De Recuperación")
            rec_rhr, rec_hrv = b.get('recovery', pd.Series()).get('restingHR'), b.get('recovery', pd.Series()).get('hrv')
            st.metric("RHR", f"{rec_rhr:.1f} bpm" if pd.notna(rec_rhr) else "N/A")
            st.metric("HRV", f"{rec_hrv:.1f} ms" if pd.notna(rec_hrv) else "N/A")
        with b_col2:
            st.subheader("Crónica (28 días)")
            chr_rhr, chr_hrv = b.get('chronic', pd.Series()).get('restingHR'), b.get('chronic', pd.Series()).get('hrv')
            st.metric("RHR", f"{chr_rhr:.1f} bpm" if pd.notna(chr_rhr) else "N/A")
            st.metric("HRV", f"{chr_hrv:.1f} ms" if pd.notna(chr_hrv) else "N/A")
        with b_col3:
            st.subheader("Histórica (60 días)")
            his_rhr, his_hrv = b.get('historic', pd.Series()).get('restingHR'), b.get('historic', pd.Series()).get('hrv')
            st.metric("RHR", f"{his_rhr:.1f} bpm" if pd.notna(his_rhr) else "N/A")
            st.metric("HRV", f"{his_hrv:.1f} ms" if pd.notna(his_hrv) else "N/A")

        with st.expander("📋 Resumen para Copiar al Coach"):
            resumen_texto = f"""
**Resumen de Salud para el {selected_date.strftime('%d/%m/%Y')}**

**Estado de Carga (Día Anterior):**
- Forma (CTL): {f'{ctl:.1f}' if pd.notna(ctl) else 'N/A'}
- Fatiga (ATL): {f'{atl:.1f}' if pd.notna(atl) else 'N/A'}
- Frescura (TSB): {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}
---
**Veredicto y Puntuación de Hoy:**
- Veredicto: {analysis.get('verdict', 'N/A')}
- Puntuación de Readiness: {analysis.get('readiness_score', 'N/A')} / 100
---
**Métricas Clave del Día:**
- VFC (HRV): {f'{hrv_hoy:.1f} ms' if pd.notna(hrv_hoy) else 'N/A'}
- FC Reposo: {f'{rhr_hoy:.0f} bpm' if pd.notna(rhr_hoy) else 'N/A'}
- Puntuación de Sueño: {f'{sleep_hoy:.0f}' if pd.notna(sleep_hoy) else 'N/A'}
---
**Desglose de la Puntuación:**
"""
            if analysis.get('score_breakdown'):
                for item in analysis.get('score_breakdown'):
                    resumen_texto += f"- {item}\n"
            else:
                resumen_texto += "No disponible.\n"
            
            # --- INICIO: AÑADIR LÍNEAS BASALES AL RESUMEN ---
            resumen_texto += "\n---"
            resumen_texto += "\n**Líneas Basales de Referencia:**\n"
            
            baseline_types = {'recovery': 'Recuperación', 'chronic': 'Crónica (28d)', 'historic': 'Histórica (60d)'}
            
            for key, name in baseline_types.items():
                baseline_series = b.get(key, pd.Series())
                rhr_base = baseline_series.get('restingHR')
                hrv_base = baseline_series.get('hrv')
                resumen_texto += f"- **{name}:**\n"
                resumen_texto += f"  - RHR: {f'{rhr_base:.1f} bpm' if pd.notna(rhr_base) else 'N/A'}\n"
                resumen_texto += f"  - HRV: {f'{hrv_base:.1f} ms' if pd.notna(hrv_base) else 'N/A'}\n"
            # --- FIN: AÑADIR LÍNEAS BASALES ---

            st.code(resumen_texto, language='markdown')