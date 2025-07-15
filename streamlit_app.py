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

# --- FUNCIONES AUXILIARES ---
def format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0: return "0m"
    h, m = divmod(seconds // 60, 60)
    return f"{int(h)}h {int(m)}m" if h > 0 else f"{int(m)}m"

def get_value(data, key, default='N/A'):
    return data.get(key) if data.get(key) is not None else default

def format_value(value, decimals=0, default='N/A'):
    if isinstance(value, (int, float)): return f"{value:.{decimals}f}"
    return default

# --- INICIO: NUEVA FUNCIÓN DE READINESS UNIFICADA (V3.0) ---
def get_readiness_analysis_v3(selected_date, api_key, athlete_id):
    start_date = selected_date - timedelta(days=60)
    end_date = selected_date
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"
    
    try:
        response = requests.get(wellness_url, auth=('API_KEY', api_key), params=params)
        if response.status_code != 200 or not response.json():
            return {"error": "No se encontraron suficientes datos de bienestar para calcular las tendencias."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión: {e}"}

    df = pd.DataFrame(response.json())
    df['id'] = pd.to_datetime(df['id'])
    df.set_index('id', inplace=True)
    df = df.sort_index()
    
    today_str = selected_date.strftime('%Y-%m-%d')
    if pd.to_datetime(today_str) not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}

    today_data = df.loc[today_str]
    past_df = df.loc[df.index < pd.to_datetime(today_str)]

    hrv_baseline_28d = past_df['hrv'].tail(28).mean()
    hrv_std_28d = past_df['hrv'].tail(28).std()
    
    hrv_hoy, rhr_hoy, sleep_score_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore')

    score, breakdown = 0, []
    
    if pd.notna(hrv_hoy) and pd.notna(hrv_baseline_28d) and pd.notna(hrv_std_28d):
        hrv_points = 0
        hrv_normal_range_lower = hrv_baseline_28d - (0.75 * hrv_std_28d)
        if hrv_hoy >= hrv_baseline_28d + (0.5 * hrv_std_28d): hrv_points = 45
        elif hrv_hoy >= hrv_normal_range_lower: hrv_points = 30
        elif hrv_hoy >= hrv_baseline_28d - hrv_std_28d: hrv_points = 15
        score += hrv_points
        breakdown.append(f"**VFC (HRV):** `{hrv_hoy:.1f}ms`. Rango normal: `{hrv_normal_range_lower:.1f}ms - {hrv_baseline_28d + (0.5 * hrv_std_28d):.1f}ms` → **{hrv_points} ptos**.")

    if pd.notna(rhr_hoy):
        rhr_points = 0
        if rhr_hoy <= 45: rhr_points = 35
        elif rhr_hoy <= 48: rhr_points = 25
        elif rhr_hoy <= 52: rhr_points = 10
        score += rhr_points
        breakdown.append(f"**FC Reposo:** `{rhr_hoy:.0f}bpm` → **{rhr_points} ptos**.")

    if pd.notna(sleep_score_hoy):
        sleep_points = 20 if sleep_score_hoy >= 80 else 10 if sleep_score_hoy >= 70 else 0
        score += sleep_points
        breakdown.append(f"**P. Sueño:** `{sleep_score_hoy:.0f}` → **{sleep_points} ptos**.")
    
    verdict_text = ""
    if score >= 80: verdict_text = "✅ **LUZ VERDE:** Estado óptimo."
    elif score >= 60: verdict_text = "⚠️ **LUZ AMARILLA:** Procede con cautela."
    else: verdict_text = "🚫 **LUZ ROJA:** Recuperación prioritaria."

    return {"verdict": verdict_text, "readiness_score": score, "score_breakdown": breakdown}

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
# --- FIN: NUEVA FUNCIÓN DE READINESS UNIFICADA (V3.0) ---


# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("📈 Historial de Actividades y Consejos")
start_date = st.date_input("Fecha de inicio", datetime.now().date() - timedelta(days=7))
end_date = st.date_input("Fecha de fin", datetime.now().date())

# --- LÓGICA PRINCIPAL ---
if start_date and end_date:
    if start_date > end_date:
        st.error("Error: La fecha de inicio no puede ser posterior a la fecha de fin.")
    else:
        params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
        st.header("🚴 Resumen de Actividades")
        activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities"
        try:
            activities_response = requests.get(activities_url, auth=('API_KEY', API_KEY), params=params)
            if activities_response.status_code == 200 and activities_response.json():
                processed_activities = []
                for activity in reversed(activities_response.json()):
                    if activity.get('type') in ['Ride', 'VirtualRide']:
                        # (El código de procesamiento de actividades no cambia)
                        ctl = get_value(activity, 'icu_ctl', 0)
                        atl = get_value(activity, 'icu_atl', 0)
                        processed_activities.append({
                            'Fecha': datetime.strptime(get_value(activity, 'start_date_local', '1900-01-01')[:10], '%Y-%m-%d').date(),
                            'Actividad': get_value(activity, 'name', 'Sin Nombre'),
                            'Duración': format_duration(get_value(activity, 'moving_time', 0)),
                            'TSS': get_value(activity, 'icu_training_load', 0),
                            'IF': format_value(get_value(activity, 'icu_intensity', 0) / 100, 2, 'N/A'),
                            'Potencia Norm. (W)': get_value(activity, 'icu_weighted_avg_watts', 0),
                            'FC Media': round(get_value(activity, 'average_heartrate', 0)),
                            'FC Máx': round(get_value(activity, 'max_heartrate', 0)),
                            'CTL': round(ctl), 'ATL': round(atl), 'TSB': round(ctl - atl)
                        })
                
                if processed_activities:
                    df_activities = pd.DataFrame(processed_activities).set_index('Fecha')
                    st.dataframe(df_activities, use_container_width=True)
                else:
                    st.info("ℹ️ No se encontraron actividades de ciclismo en el rango seleccionado.")
            else:
                st.warning("No se pudo obtener el historial de actividades.")
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Error de conexión de red al obtener actividades: {e}")

        st.markdown("---")
        # --- SECCIÓN DE CONSEJO TOTALMENTE ACTUALIZADA ---
        st.header(f"⭐ Análisis de Readiness para el Último Día ({end_date.strftime('%d-%m-%Y')})")
        
        # Llamamos a la nueva función v3
        readiness = get_readiness_analysis_v3(end_date, API_KEY, ATHLETE_ID)
        
        if readiness and "error" not in readiness:
            st.subheader(readiness['verdict'])
            st.caption("Puntuación de Readiness:")
            display_gauge(readiness['readiness_score'])
            
            with st.expander("🔍 Analiza tu puntuación en detalle"):
                for line in readiness['score_breakdown']:
                    st.info(line)
                st.markdown(f"**PUNTUACIÓN TOTAL: {readiness['readiness_score']}**")
        else:
            st.info(f"No hay suficientes datos para generar un veredicto para el {end_date.strftime('%d-%m-%Y')}.")