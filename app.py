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

def get_readiness_analysis(selected_date, api_key, athlete_id):
    start_date = selected_date - timedelta(days=7)
    end_date = selected_date
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"
    try:
        response = requests.get(wellness_url, auth=('API_KEY', api_key), params=params)
        if response.status_code != 200 or not response.json(): return None
    except requests.exceptions.RequestException: return None
    df = pd.DataFrame(response.json())
    if 'id' not in df.columns: return None
    df['id'] = pd.to_datetime(df['id'])
    df.set_index('id', inplace=True)
    today_str = selected_date.strftime('%Y-%m-%d')
    if pd.to_datetime(today_str) not in df.index: return None
    today_data = df.loc[today_str]
    previous_days_df = df.loc[:selected_date - timedelta(days=1)].tail(7)
    hrv_avg_7d = previous_days_df['hrv'].mean()
    rhr_avg_7d = previous_days_df['restingHR'].mean()
    hrv_hoy = today_data.get('hrv')
    rhr_hoy = today_data.get('restingHR')
    sleep_score_hoy = today_data.get('sleepScore')
    atl_hoy = today_data.get('atl')
    score = 0
    if pd.notna(hrv_hoy) and pd.notna(hrv_avg_7d):
        if hrv_hoy >= hrv_avg_7d * 0.95: score += 40
        elif hrv_hoy >= hrv_avg_7d * 0.90: score += 20
    if pd.notna(rhr_hoy) and pd.notna(rhr_avg_7d):
        if rhr_hoy <= rhr_avg_7d * 1.05: score += 30
        elif rhr_hoy <= rhr_avg_7d * 1.10: score += 15
    if pd.notna(sleep_score_hoy):
        if sleep_score_hoy >= 75: score += 20
        elif sleep_score_hoy >= 65: score += 10
    if pd.notna(atl_hoy):
        if atl_hoy < 50: score += 10
        elif atl_hoy < 70: score += 5
    verdict = "✅ ¡Listo para Entrenar!"
    if score < 50: verdict = "🚫 Descanso Recomendado"
    elif score < 75: verdict = "⚠️ Entrenar con Precaución"
    return {"verdict": verdict, "score": score}

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("📈 Historial y Análisis de Actividades")
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
                            'Cadencia Media': round(get_value(activity, 'average_cadence', 0)),
                            'V.I.': format_value(get_value(activity, 'icu_variability_index', 0), 2, 'N/A'),
                            'Desnivel (m)': round(get_value(activity, 'total_elevation_gain', 0)),
                            'Trabajo (kJ)': round(get_value(activity, 'icu_joules', 0) / 1000),
                            'Trabajo >FTP (kJ)': round(get_value(activity, 'icu_joules_above_ftp', 0) / 1000),
                            'VO2Max (Garmin)': format_value(get_value(activity, 'VO2MaxGarmin', 'N/A'), 1, 'N/A'),
                            'CTL': round(ctl),
                            'ATL': round(atl),
                            'TSB': round(ctl - atl),
                            'Eficiencia (Pw:HR) %': format_value(get_value(activity, 'decoupling', 0), 1, 'N/A'),
                            'Temperatura Media (°C)': format_value(get_value(activity, 'average_temp', 'N/A'), 1, 'N/A')
                        })
                
                if processed_activities:
                    df_activities = pd.DataFrame(processed_activities).set_index('Fecha')
                    st.write("**Tabla de Actividades:**")
                    all_columns = [col for col in df_activities.columns.tolist() if col != 'Actividad']
                    default_columns = ['Duración', 'TSS', 'IF', 'Potencia Norm. (W)', 'FC Media', 'FC Máx', 'CTL', 'ATL', 'TSB', 'Eficiencia (Pw:HR) %', 'VO2Max (Garmin)']
                    selected_columns = st.multiselect("Selecciona las columnas a mostrar:", options=all_columns, default=[col for col in default_columns if col in all_columns])
                    
                    if selected_columns:
                        display_df = df_activities[['Actividad'] + selected_columns]
                        st.dataframe(display_df.style.set_properties(**{'text-align': 'center'}), use_container_width=True)

                    st.write("**Gráfico de Tendencias de Rendimiento:**")
                    numeric_activity_cols = df_activities.select_dtypes(include=np.number).columns.tolist()
                    default_chart_activity_cols = ['TSS', 'CTL', 'ATL', 'TSB']
                    selected_chart_activity_cols = st.multiselect("Selecciona métricas para el gráfico de rendimiento:", options=numeric_activity_cols, default=[col for col in default_chart_activity_cols if col in numeric_activity_cols])
                    
                    if selected_chart_activity_cols:
                        chart_data_activities = df_activities[selected_chart_activity_cols].dropna(how='all')
                        if not chart_data_activities.empty:
                            st.line_chart(chart_data_activities)
                else:
                    st.info("ℹ️ No se encontraron actividades de ciclismo en el rango seleccionado.")
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Error de conexión de red al obtener actividades: {e}")

        st.markdown("---")
        st.header("⭐ Veredicto del Último Día")
        readiness = get_readiness_analysis(end_date, API_KEY, ATHLETE_ID)
        if readiness:
            st.subheader(f"Para el {end_date.strftime('%d-%m-%Y')}: {readiness['verdict']}")
            st.metric(label="Puntuación de Readiness calculada", value=f"{readiness['score']} / 100")
        else:
            st.info(f"No hay suficientes datos para generar un veredicto para el {end_date.strftime('%d-%m-%Y')}.")