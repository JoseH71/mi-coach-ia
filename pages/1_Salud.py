import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except FileNotFoundError:
    st.error("❌ No se ha encontrado el fichero de secretos.")
    st.stop()

# --- LÓGICA DE ANÁLISIS AVANZADA V3 ---

def get_readiness_analysis_v3(selected_date):
    # Fetch de 60 días para un cálculo estadístico robusto
    start_date = selected_date - timedelta(days=60)
    end_date = selected_date
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness"
    
    try:
        response = requests.get(wellness_url, auth=('API_KEY', API_KEY), params=params)
        if response.status_code != 200 or not response.json():
            return {"error": "No se encontraron suficientes datos de bienestar para calcular las tendencias."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión: {e}"}

    df = pd.DataFrame(response.json())
    df['id'] = pd.to_datetime(df['id'])
    df.set_index('id', inplace=True)
    df = df.sort_index() # Asegurarse de que los datos están ordenados por fecha
    
    today_str = selected_date.strftime('%Y-%m-%d')
    if pd.to_datetime(today_str) not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}

    # --- CÁLCULO DE MÉTRICAS Y ESTADÍSTICAS ---
    today_data = df.loc[today_str]
    past_df = df.loc[df.index < pd.to_datetime(today_str)]

    # Medias móviles
    hrv_avg_7d = past_df['hrv'].tail(7).mean()
    rhr_avg_7d = past_df['restingHR'].tail(7).mean()
    
    # Línea de base crónica (28 días) y su dispersión (desviación estándar)
    hrv_baseline_28d = past_df['hrv'].tail(28).mean()
    hrv_std_28d = past_df['hrv'].tail(28).std()
    
    hrv_hoy, rhr_hoy, sleep_score_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore')

    # --- LÓGICA DE PUNTUACIÓN BASADA EN RANGO DE NORMALIDAD ---
    score, breakdown = 0, []
    
    # Puntuación HRV (45 ptos) - La más importante
    if pd.notna(hrv_hoy) and pd.notna(hrv_baseline_28d) and pd.notna(hrv_std_28d):
        hrv_points = 0
        hrv_normal_range_lower = hrv_baseline_28d - (0.75 * hrv_std_28d)
        if hrv_hoy >= hrv_baseline_28d + (0.5 * hrv_std_28d): hrv_points = 45 # Excelente, supercompensando
        elif hrv_hoy >= hrv_normal_range_lower: hrv_points = 30 # Bien, dentro de la normalidad
        elif hrv_hoy >= hrv_baseline_28d - hrv_std_28d: hrv_points = 15 # Aviso, por debajo de lo normal
        score += hrv_points
        breakdown.append(f"**VFC (HRV):** `{hrv_hoy:.1f}ms`. Rango normal: `{hrv_normal_range_lower:.1f}ms - {hrv_baseline_28d + (0.5 * hrv_std_28d):.1f}ms` → **{hrv_points} ptos**.")

    # Puntuación RHR (35 ptos)
    if pd.notna(rhr_hoy):
        rhr_points = 0
        # Puntuación simple para RHR ya que su rango es menos variable
        if rhr_hoy <= 45: rhr_points = 35
        elif rhr_hoy <= 48: rhr_points = 25
        elif rhr_hoy <= 52: rhr_points = 10
        score += rhr_points
        breakdown.append(f"**FC Reposo:** `{rhr_hoy:.0f}bpm` → **{rhr_points} ptos**.")

    # Puntuación Sueño (20 ptos)
    if pd.notna(sleep_score_hoy):
        sleep_points = 20 if sleep_score_hoy >= 80 else 10 if sleep_score_hoy >= 70 else 0
        score += sleep_points
        breakdown.append(f"**P. Sueño:** `{sleep_score_hoy:.0f}` → **{sleep_points} ptos**.")
    
    # --- VEREDICTO FINAL Y TEXTO DE ANÁLISIS ---
    verdict_text = ""
    if score >= 80: verdict_text = "✅ **LUZ VERDE:** Estado óptimo para entrenar. Tu cuerpo está recuperado y listo para asimilar carga de calidad."
    elif score >= 60: verdict_text = "⚠️ **LUZ AMARILLA:** Estado aceptable, pero con señales de fatiga. Procede con cautela. Considera reducir la intensidad o el volumen."
    else: verdict_text = "🚫 **LUZ ROJA:** Señales de fatiga significativa. La recuperación es la prioridad. Se recomienda descanso total o una sesión regenerativa muy suave."

    return {
        "verdict": verdict_text, "readiness_score": score, "score_breakdown": breakdown,
        "hrv_7d_data": past_df['hrv'].tail(7),
        "rhr_7d_data": past_df['restingHR'].tail(7),
        "metrics": {
            "FC Reposo": {"value": rhr_hoy, "avg7": rhr_avg_7d}, 
            "VFC (HRV)": {"value": hrv_hoy, "avg7": hrv_avg_7d, "normal_range": f"{hrv_baseline_28d - (0.75 * hrv_std_28d):.1f}-{hrv_baseline_28d + (0.5 * hrv_std_28d):.1f}"},
            "Puntuación Sueño": {"value": sleep_score_hoy}
        }
    }

# --- FUNCIÓN PARA LA INTERFAZ ---
def display_gauge(score):
    score_color = "#d9534f" if score < 60 else "#f0ad4e" if score < 80 else "#5cb85c"
    gauge_html = f"""
    <div style="background-color: #f1f1f1; border-radius: 5px; padding: 2px;">
        <div style="background-color: {score_color}; width: {score}%; height: 24px; border-radius: 5px; text-align: center; color: white; font-weight: bold; line-height: 24px;">
            {score} / 100
        </div>
    </div>
    """
    st.markdown(gauge_html, unsafe_allow_html=True)

# --- INTERFAZ DE USUARIO V3 ---
st.set_page_config(layout="wide", page_title="Coach IA de Readiness v3")
st.title("💗 Estado de Salud")

selected_date = st.date_input("Selecciona la fecha de análisis:", datetime.now().date())

if selected_date:
    analysis = get_readiness_analysis_v3(selected_date)
    
    if "error" in analysis:
        st.error(analysis["error"])
    else:
        st.markdown("---")
        # --- NUEVO: Cuadro de Mandos Principal ---
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.subheader("Veredicto del Día")
            st.markdown(f"**{analysis['verdict']}**")
            st.caption("Puntuación de Readiness:")
            display_gauge(analysis['readiness_score'])

        with col2:
            st.subheader("Tendencia HRV (7d)")
            if not analysis['hrv_7d_data'].empty:
                st.line_chart(analysis['hrv_7d_data'], height=120)
            else:
                st.info("Faltan datos de HRV.")
        
        with col3:
            st.subheader("Tendencia RHR (7d)")
            if not analysis['rhr_7d_data'].empty:
                st.line_chart(analysis['rhr_7d_data'], height=120)
            else:
                st.info("Faltan datos de RHR.")
        
        st.markdown("---")
        
        # --- Métricas Detalladas ---
        st.subheader("Métricas del Día")
        d_col1, d_col2, d_col3 = st.columns(3)
        m = analysis["metrics"]

        with d_col1:
            val, avg7 = m['VFC (HRV)']['value'], m['VFC (HRV)']['avg7']
            delta_color = "normal" if pd.notna(val) and pd.notna(avg7) and val >= avg7 else "inverse"
            st.metric("VFC (HRV)", f"{val:.0f} ms" if pd.notna(val) else "N/A", f"{val-avg7:.1f} vs 7d avg" if pd.notna(val) and pd.notna(avg7) else None, delta_color=delta_color)
            if pd.notna(val): st.caption(f"Rango Normal (28d): {m['VFC (HRV)']['normal_range']} ms")

        with d_col2:
            val, avg7 = m['FC Reposo']['value'], m['FC Reposo']['avg7']
            delta_color = "inverse" if pd.notna(val) and pd.notna(avg7) and val <= avg7 else "normal"
            st.metric("FC Reposo", f"{val:.0f} bpm" if pd.notna(val) else "N/A", f"{val-avg7:.1f} vs 7d avg" if pd.notna(val) and pd.notna(avg7) else None, delta_color=delta_color)
            if pd.notna(val): st.caption("Un RHR elevado indica posible fatiga.")

        with d_col3:
            val = m['Puntuación Sueño']['value']
            st.metric("Puntuación Sueño", f"{val:.0f}" if pd.notna(val) else "N/A")
            st.caption("El descanso es clave para la adaptación.")

        # --- Desglose de Puntuación ---
        with st.expander("🔍 Analiza tu puntuación en detalle"):
            for line in analysis['score_breakdown']:
                st.info(line)
            st.markdown(f"**PUNTUACIÓN TOTAL: {analysis['readiness_score']}**")