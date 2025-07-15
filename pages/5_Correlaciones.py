import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

# --- CONFIGURACIÓN ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except FileNotFoundError:
    st.error("❌ No se ha encontrado el fichero de secretos.")
    st.stop()

# --- FUNCIONES ---
@st.cache_data(ttl=3600)
def fetch_data_in_range(start_date, end_date):
    """Obtiene actividades y bienestar en un rango de fechas."""
    date_format = "%Y-%m-%d"
    s, e = start_date.strftime(date_format), end_date.strftime(date_format)
    auth_tuple = ('API_KEY', API_KEY)
    
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness?oldest={s}&newest={e}"
    wellness_response = requests.get(wellness_url, auth=auth_tuple)
    wellness_data = wellness_response.json() if wellness_response.status_code == 200 else []
    
    activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={s}&newest={e}"
    activities_response = requests.get(activities_url, auth=auth_tuple)
    activities_data = activities_response.json() if activities_response.status_code == 200 else []

    return wellness_data, activities_data

def process_weekly_data(end_date, num_weeks=12):
    """
    Procesa los datos para devolver:
    1. Un DataFrame con métricas semanales.
    2. La línea basal crónica (12 semanas, baja carga).
    3. La línea basal aguda (últimas 4 semanas).
    """
    start_date = end_date - timedelta(days=num_weeks*7 - 1)
    wellness, activities = fetch_data_in_range(start_date, end_date)

    if not wellness:
        return pd.DataFrame(), None, None

    df_wellness = pd.DataFrame(wellness)
    df_wellness['date'] = pd.to_datetime(df_wellness['id'])
    
    df_activities = pd.DataFrame(activities)
    if not df_activities.empty and 'start_date_local' in df_activities.columns:
        df_activities['date'] = pd.to_datetime(df_activities['start_date_local'])
    else:
        # Añadir columna de fecha vacía si no hay actividades para evitar errores
        df_activities = pd.DataFrame(columns=['icu_training_load']).assign(date=pd.Series(dtype='datetime64[ns]'))


    weekly_summary = []
    for i in range(num_weeks):
        week_end = end_date - timedelta(days=i*7)
        week_start = week_end - timedelta(days=6)
        
        week_wellness = df_wellness[(df_wellness['date'].dt.date >= week_start) & (df_wellness['date'].dt.date <= week_end)]
        week_activities_data = df_activities[(df_activities['date'].dt.date >= week_start) & (df_activities['date'].dt.date <= week_end)]
        
        if week_wellness.empty:
            continue

        metrics = {
            'Semana': f"{week_start.strftime('%d/%m')}-{week_end.strftime('%d/%m')}",
            'TSS Semanal': week_activities_data['icu_training_load'].sum(),
            'ATL': week_wellness['atl'].mean(),
            'CTL': week_wellness['ctl'].mean(),
            'RHR': week_wellness['restingHR'].mean(),
            'HRV': week_wellness['hrv'].mean(),
            'P. Sueño': week_wellness['sleepScore'].mean()
        }
        weekly_summary.append(metrics)
    
    df_weekly = pd.DataFrame(weekly_summary).dropna().set_index('Semana')

    if df_weekly.empty:
        return pd.DataFrame(), None, None

    # --- CÁLCULO DE LÍNEAS BASALES ---
    # 1. Línea Basal Crónica (12 semanas, baja carga)
    avg_atl_chronic = df_weekly['ATL'].mean()
    low_load_weeks = df_weekly[df_weekly['ATL'] <= avg_atl_chronic]
    chronic_baseline = low_load_weeks[['RHR', 'HRV', 'P. Sueño']].mean()

    # 2. Línea Basal Aguda (últimas 4 semanas)
    acute_baseline = None
    if len(df_weekly) >= 4:
        recent_4_weeks = df_weekly.head(4)
        acute_baseline = recent_4_weeks[['RHR', 'HRV', 'P. Sueño']].mean()

    return df_weekly, chronic_baseline, acute_baseline

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("🔬 Correlaciones y Línea Basal v2.0")
st.write("Esta sección analiza la relación entre tu carga de entrenamiento y tus métricas de bienestar.")

end_date = st.date_input("Selecciona la fecha final del análisis", datetime.now().date())

if end_date:
    df_weekly, chronic_baseline, acute_baseline = process_weekly_data(end_date)

    if df_weekly.empty:
        st.warning("No hay suficientes datos de bienestar en el periodo seleccionado para realizar el análisis.")
    else:
        # --- NUEVA SECCIÓN DE DOBLE LÍNEA BASAL ---
        st.header("❤️ Tu Doble Línea Basal de Recuperación")
        
        if chronic_baseline is not None and acute_baseline is not None:
            c1, c2 = st.columns(2)
            with c1:
                st.info("**Línea Basal Aguda (28 días)**\n\nRepresenta tu estado de recuperación 'actual', basado en el último mes.")
            with c2:
                st.success("**Línea Basal Crónica (12 sem.)**\n\nRepresenta tu estado de recuperación 'histórico' o ideal, basado en tus semanas más frescas.")

            baseline_data = {
                'Métrica': ['FC Reposo (RHR)', 'VFC (HRV)', 'P. Sueño'],
                'Línea Basal Actual (28d)': [f"{acute_baseline.get('RHR', 0):.1f} bpm", f"{acute_baseline.get('HRV', 0):.1f} ms", f"{acute_baseline.get('P. Sueño', 0):.1f}"],
                'Línea Basal Histórica (12sem)': [f"{chronic_baseline.get('RHR', 0):.1f} bpm", f"{chronic_baseline.get('HRV', 0):.1f} ms", f"{chronic_baseline.get('P. Sueño', 0):.1f}"]
            }
            baseline_df = pd.DataFrame(baseline_data).set_index('Métrica')
            st.dataframe(baseline_df, use_container_width=True)
            
            # Interpretación de la comparación
            if acute_baseline.get('HRV', 0) > chronic_baseline.get('HRV', 0) * 1.02:
                st.write("📈 **Análisis de Tendencia:** ¡Excelente! Tu estado de recuperación actual es superior a tu media histórica. Estás en una clara fase de adaptación positiva.")
            elif acute_baseline.get('HRV', 0) < chronic_baseline.get('HRV', 0) * 0.98:
                st.write("📉 **Análisis de Tendencia:** Atención. Tu estado de recuperación actual es inferior a tu media histórica. Podría ser una señal de fatiga acumulada a largo plazo.")
            else:
                st.write("⚖️ **Análisis de Tendencia:** Tu estado de recuperación se mantiene estable y alineado con tu media histórica.")

        else:
            st.info("No hay suficientes datos para una comparación completa de líneas basales.")

        st.markdown("---")
        
        # --- El resto de la app (Mapa de Calor y Resumen) no cambia ---
        st.header("🔥 Mapa de Calor de Correlaciones")
        st.caption("Muestra cómo se relacionan tus métricas. Amarillo = relación positiva. Azul/Morado = relación negativa.")
        
        correlation_matrix = df_weekly.corr(method='pearson')
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(correlation_matrix, ax=ax, annot=True, cmap='viridis', fmt=".2f")
        plt.title("Matriz de Correlación")
        st.pyplot(fig)
        
        st.markdown("---")
        st.header("📋 Resumen de las Últimas 12 Semanas")
        st.dataframe(df_weekly.style.format("{:.1f}"), use_container_width=True)