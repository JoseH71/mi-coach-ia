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

# --- FUNCIONES ---
def fetch_activities(start_date, end_date):
    """Obtiene todas las actividades en un rango de fechas."""
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={start_date}&newest={end_date}"
    try:
        response = requests.get(url, auth=('API_KEY', API_KEY))
        if response.status_code == 200:
            return response.json() or []
        st.error(f"Error al contactar con la API: {response.status_code}")
        return []
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión: {e}")
        return []

def process_activities_to_df(activities_raw):
    """Procesa una lista de actividades y devuelve un DataFrame de pandas."""
    processed_list = []
    for activity in activities_raw:
        if activity.get('type') not in ['Ride', 'VirtualRide']:
            continue

        power_norm = activity.get("icu_weighted_avg_watts")
        hr_avg = activity.get("average_heartrate")
        power_avg = activity.get("icu_average_watts")

        efficiency = round(power_norm / hr_avg, 2) if hr_avg and power_norm and hr_avg > 0 and power_norm > 0 else 0
        power_hr = round(power_avg / hr_avg, 2) if hr_avg and power_avg and hr_avg > 0 and power_avg > 0 else 0
        
        processed_list.append({
            "date": pd.to_datetime(activity.get("start_date_local")), # <-- Mantenemos como objeto de fecha
            "Actividad": activity.get("name", "N/A"),
            "Eficiencia (NP/FC)": efficiency,
            "Potencia/FC": power_hr,
            "Eficiencia Z2 (Pot/FC)": activity.get("icu_power_hr_z2", 0),
        })
    
    if not processed_list:
        return pd.DataFrame()
        
    df = pd.DataFrame(processed_list).set_index('date')
    df.sort_index(inplace=True) # <-- ¡CORRECCIÓN CLAVE! Ordenamos el índice cronológicamente
    return df

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("⚡ Análisis de Eficiencia Aeróbica")
st.write("Esta sección analiza tu eficiencia aeróbica, un indicador clave de cómo mejora tu 'motor' de resistencia.")

selected_date = st.date_input("Selecciona una fecha para analizar sus métricas y ver las tendencias", datetime.now().date() - timedelta(days=1))

if selected_date:
    start_date_60d = selected_date - timedelta(days=59)
    activities_raw = fetch_activities(start_date_60d.strftime("%Y-%m-%d"), selected_date.strftime("%Y-%m-%d"))

    if not activities_raw:
        st.warning("No se encontraron actividades en el periodo de 60 días para calcular tendencias.")
    else:
        df_efficiency = process_activities_to_df(activities_raw)
        
        st.markdown("---")
        st.subheader(f"Métricas para el día {selected_date.strftime('%d-%m-%Y')}")
        
        # Convertimos el selected_date a datetime para poder comparar con el índice
        selected_datetime = pd.to_datetime(selected_date)
        today_data = df_efficiency[df_efficiency.index.date == selected_datetime.date()]

        if today_data.empty or (today_data.iloc[0][['Eficiencia (NP/FC)', 'Potencia/FC', 'Eficiencia Z2 (Pot/FC)']] == 0).all():
            st.info("ℹ️ No hubo actividad con datos de eficiencia para este día.")
        else:
            today_metrics = today_data.iloc[0]
            
            df_period_7d = df_efficiency[df_efficiency.index <= selected_datetime].tail(7)
            avg_7d = df_period_7d.select_dtypes(include=np.number).replace(0, np.nan).mean()

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Eficiencia (NP/FC)", f"{today_metrics['Eficiencia (NP/FC)']:.2f}", f"{today_metrics['Eficiencia (NP/FC)'] - avg_7d.get('Eficiencia (NP/FC)', 0):.2f} vs. 7d")
            with col2:
                st.metric("Potencia/FC", f"{today_metrics['Potencia/FC']:.2f}", f"{today_metrics['Potencia/FC'] - avg_7d.get('Potencia/FC)', 0):.2f} vs. 7d")
            with col3:
                st.metric("Eficiencia Z2 (Pot/FC)", f"{today_metrics['Eficiencia Z2 (Pot/FC)']:.2f}", f"{today_metrics['Eficiencia Z2 (Pot/FC)'] - avg_7d.get('Eficiencia Z2 (Pot/FC)', 0):.2f} vs. 7d")
            
        st.markdown("---")
        st.subheader("📊 Promedios Móviles Desplegables")
        st.caption("Haz clic en cada periodo para ver las actividades que se han usado para calcular la media.")

        for period in [7, 30, 60]:
            period_df = df_efficiency[df_efficiency.index.date <= selected_date].tail(period)
            
            numeric_cols = period_df.select_dtypes(include=np.number)
            period_avg = numeric_cols.replace(0, np.nan).mean()

            title = (
                f"Últimos {period} días  |  "
                f"Eficiencia: {period_avg.get('Eficiencia (NP/FC)', 0):.2f}  |  "
                f"Potencia/FC: {period_avg.get('Potencia/FC', 0):.2f}  |  "
                f"Eficiencia Z2: {period_avg.get('Eficiencia Z2 (Pot/FC)', 0):.2f}"
            )
            
            with st.expander(title):
                display_period_df = period_df[(period_df.select_dtypes(include=np.number) > 0).any(axis=1)].copy()
                # Formateamos el índice a un formato de texto legible antes de mostrarlo
                display_period_df.index = display_period_df.index.strftime('%d-%m-%Y')
                st.dataframe(display_period_df, use_container_width=True)