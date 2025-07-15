import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd

# --- CONFIGURACIÓN ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except FileNotFoundError:
    st.error("❌ No se ha encontrado el fichero de secretos.")
    st.stop()

# --- FUNCIONES ---
def format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0: return "0m"
    h, m = divmod(seconds // 60, 60)
    return f"{int(h)}h {int(m)}m" if h > 0 else f"{int(m)}m"

def fetch_data_for_day(selected_date):
    """
    Hace dos llamadas a la API: una para el plan y otra para la actividad real.
    """
    date_str = selected_date.strftime('%Y-%m-%d')
    results = {"planned": {}, "actual": {}}

    # --- 1. OBTENER DATOS DEL PLAN ---
    try:
        events_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events"
        params = {'oldest': date_str, 'newest': date_str, 'resolve': True}
        events_response = requests.get(events_url, auth=('API_KEY', API_KEY), params=params)
        
        if events_response.status_code == 200 and events_response.json():
            for event in events_response.json():
                if event.get("category") == "WORKOUT":
                    results["planned"] = {
                        "duration": event.get('duration', 0),
                        "tss": event.get('icu_training_load', 0), # <-- ¡¡CORREGIDO AL CAMPO QUE FUNCIONA!!
                        "if": event.get('intensity', 0) / 100 if event.get('intensity') else 0
                    }
                    break 
    except requests.exceptions.RequestException:
        pass

    # --- 2. OBTENER DATOS REALES ---
    try:
        activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={date_str}&newest={date_str}"
        activities_response = requests.get(activities_url, auth=('API_KEY', API_KEY))
        if activities_response.status_code == 200 and activities_response.json():
            for activity in activities_response.json():
                if activity.get('type') in ['Ride', 'VirtualRide']:
                    results["actual"] = {
                        "name": activity.get('name', 'Actividad sin nombre'),
                        "duration": activity.get('moving_time', 0),
                        "tss": activity.get('icu_training_load', 0),
                        "if": activity.get('icu_intensity', 0) / 100 if activity.get('icu_intensity') else 0,
                        "decoupling": activity.get('decoupling', 0),
                        "power_zones": activity.get('icu_zone_times', []),
                        "hr_zones": activity.get('icu_hr_zone_times', [])
                    }
                    break
    except requests.exceptions.RequestException:
        pass

    return results

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("💯 Análisis Post-Entreno")
st.write("Selecciona un día del pasado para analizar la calidad de ejecución del entrenamiento.")

selected_date = st.date_input("Fecha del entrenamiento", datetime.now().date() - timedelta(days=1))

if selected_date:
    data = fetch_data_for_day(selected_date)

    if not data.get("actual"):
        st.info("ℹ️ No se encontró ninguna actividad de ciclismo completada para este día.")
    else:
        actual = data["actual"]
        planned = data["planned"]
        
        st.header(f"Análisis de: *{actual.get('name', 'N/A')}*")
        
        st.subheader("📈 Comparativa: Plan vs. Realidad")
        
        if not planned or planned.get("tss", 0) == 0:
            st.caption("No se encontró un entrenamiento planificado asociado a esta actividad. Se muestran solo los datos reales.")
            planned_duration, planned_tss, planned_if = 0, 0, 0
        else:
            planned_duration = planned.get("duration", 0)
            planned_tss = planned.get("tss", 0)
            planned_if = planned.get("if", 0)

        duration_delta = actual.get('duration', 0) - planned_duration
        tss_delta = actual.get('tss', 0) - planned_tss
        if_delta = actual.get('if', 0) - planned_if

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Duración Realizada", format_duration(actual.get('duration', 0)), f"{format_duration(duration_delta)} vs. Plan" if planned_duration > 0 else None)
        with col2:
            st.metric("TSS Realizado", f"{actual.get('tss', 0):.0f}", f"{tss_delta:.0f} vs. Plan" if planned_tss > 0 else None)
        with col3:
            st.metric("IF Realizado", f"{actual.get('if', 0):.2f}", f"{if_delta:.2f} vs. Plan" if planned_if > 0 else None)

        st.subheader("💨 Calidad Aeróbica")
        decoupling = actual.get('decoupling', 0)
        st.metric(label="Desacoplamiento (Pw:HR)", value=f"{decoupling:.1f}%")
        st.caption("Un valor bajo (idealmente < 5%) indica una buena resistencia aeróbica durante la sesión.")
        
        st.markdown("---")

        st.subheader("📊 Tiempo en Zonas")
        col_pow, col_hr = st.columns(2)

        with col_pow:
            st.write("**Zonas de Potencia**")
            power_zones = actual.get("power_zones", [])
            if power_zones and isinstance(power_zones, list) and len(power_zones) > 0 and 'secs' in power_zones[0]:
                total_time = sum(z.get('secs', 0) for z in power_zones)
                for i, zone_data in enumerate(power_zones[:7]):
                    zone_time = zone_data.get('secs', 0)
                    if zone_time > 0:
                        st.text(f"Z{i+1}: {format_duration(zone_time)}")
                        st.progress(zone_time / total_time if total_time > 0 else 0)
            else:
                st.info("Sin datos de potencia.")
        
        with col_hr:
            st.write("**Zonas de Frecuencia Cardíaca**")
            hr_zones = actual.get("hr_zones", [])
            if hr_zones and sum(hr_zones) > 0:
                total_time = sum(hr_zones)
                for i, zone_time in enumerate(hr_zones):
                    if zone_time > 0:
                        st.text(f"Z{i+1}: {format_duration(zone_time)}")
                        st.progress(zone_time / total_time if total_time > 0 else 0)
            else:
                st.info("Sin datos de Frecuencia Cardíaca.")