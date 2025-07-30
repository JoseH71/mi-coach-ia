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

# --- FUNCIONES AUXILIARES ---
def format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0: return "0m"
    h, m = divmod(seconds // 60, 60)
    s = seconds % 60
    if h > 0:
        return f"{int(h)}h {int(m)}m"
    return f"{int(m)}m {int(s)}s"

def fetch_data_for_day(selected_date):
    date_str = selected_date.strftime('%Y-%m-%d')
    results = {"planned": {}, "actual": {}}
    auth_tuple = ('API_KEY', API_KEY)

    # --- 1. OBTENER DATOS DEL PLAN ---
    try:
        events_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events"
        params = {'oldest': date_str, 'newest': date_str}
        events_response = requests.get(events_url, auth=auth_tuple, params=params)
        if events_response.status_code == 200 and events_response.json():
            for event in events_response.json():
                if event.get("category") == "WORKOUT":
                    results["planned"] = {
                        "duration": event.get('moving_time', 0),
                        "tss": event.get('icu_training_load', 0),
                        "if": event.get('icu_intensity', 0) / 100 if event.get('icu_intensity') else 0
                    }
                    break
    except requests.exceptions.RequestException:
        pass

    # --- 2. OBTENER DATOS REALES ---
    try:
        activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={date_str}&newest={date_str}"
        activities_response = requests.get(activities_url, auth=auth_tuple)
        if activities_response.status_code == 200 and activities_response.json():
            for activity in activities_response.json():
                if activity.get('type') in ['Ride', 'VirtualRide']:
                    results["actual"] = activity # Guardamos toda la actividad para el análisis de intervalos
                    break
    except requests.exceptions.RequestException:
        pass

    return results

# --- NUEVA FUNCIÓN PARA ANALIZAR INTERVALOS ---
def analyze_intervals(activity_data):
    intervals = activity_data.get("intervals", [])
    if not intervals:
        return pd.DataFrame()

    processed_intervals = []
    # Filtramos para quedarnos solo con las series de trabajo ('WORK')
    work_intervals = [i for i in intervals if i.get('type') == 'WORK' and i.get('duration', 0) > 120] # Mínimo 2 min

    for i, interval in enumerate(work_intervals, 1):
        watts = interval.get('avg_watts')
        hr = interval.get('avg_hr')
        
        processed_intervals.append({
            "Serie": i,
            "Duración": format_duration(interval.get('duration', 0)),
            "Potencia (W)": f"{watts:.0f}" if watts is not None else "N/A",
            "FC Media": f"{hr:.0f}" if hr is not None else "N/A",
            "FC Máx": f"{interval.get('max_hr', 0):.0f}",
            "Cadencia": f"{interval.get('avg_cadence', 0):.0f}",
            "Eficiencia (W/lpm)": f"{(watts / hr):.2f}" if watts is not None and hr is not None and hr > 0 else "N/A"
        })
        
    return pd.DataFrame(processed_intervals)

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("🔬 Análisis Post-Entreno v2.0")
st.write("Selecciona un día del pasado para analizar la calidad de ejecución del entrenamiento.")

selected_date = st.date_input("Fecha del entrenamiento", datetime.now().date() - timedelta(days=3)) # Por defecto, anteayer

if selected_date:
    data = fetch_data_for_day(selected_date)

    if not data.get("actual"):
        st.info("ℹ️ No se encontró ninguna actividad de ciclismo completada para este día.")
    else:
        actual = data["actual"]
        planned = data["planned"]
        
        st.header(f"Análisis de: *{actual.get('name', 'N/A')}*")
        
        # --- SECCIÓN 1: Comparativa General ---
        st.subheader("📈 Comparativa: Plan vs. Realidad")
        
        # ... (código de métricas generales sin cambios) ...
        planned_duration = planned.get("duration", 0)
        planned_tss = planned.get("tss", 0)
        planned_if = planned.get("if", 0)
        duration_delta = actual.get('moving_time', 0) - planned_duration
        tss_delta = actual.get('icu_training_load', 0) - planned_tss
        if_delta = (actual.get('icu_intensity', 0) / 100 if actual.get('icu_intensity') else 0) - planned_if

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Duración", format_duration(actual.get('moving_time', 0)), f"{format_duration(duration_delta)} vs. Plan" if planned_duration > 0 else None)
        with col2:
            st.metric("TSS", f"{actual.get('icu_training_load', 0):.0f}", f"{tss_delta:.0f} vs. Plan" if planned_tss > 0 else None)
        with col3:
            st.metric("IF", f"{(actual.get('icu_intensity', 0) / 100 if actual.get('icu_intensity') else 0):.2f}", f"{if_delta:.2f} vs. Plan" if planned_if > 0 else None)
        with col4:
            st.metric("Desacoplamiento", f"{actual.get('decoupling', 0):.1f}%")

        st.markdown("---")
        
        # --- NUEVA SECCIÓN 2: ANÁLISIS DE INTERVALOS ---
        st.subheader("⚡ Análisis de Intervalos de Calidad")
        interval_df = analyze_intervals(actual)
        
        if not interval_df.empty:
            # Aplicamos estilo visual a la tabla
            st.dataframe(
                interval_df.style
                    .background_gradient(cmap='viridis', subset=['Potencia (W)'])
                    .background_gradient(cmap='Reds', subset=['FC Media', 'FC Máx'])
                    .highlight_max(subset=['Eficiencia (W/lpm)'], color='#5cb85c')
                    .format("{:.2f}", subset=['Eficiencia (W/lpm)'])
                    .set_properties(**{'text-align': 'center'}),
                use_container_width=True
            )
            st.caption("Nota: El análisis busca automáticamente las series de trabajo principales de tu entrenamiento.")
        else:
            st.info("No se detectaron intervalos de trabajo significativos en esta actividad (o no se pulsó el botón 'Lap').")

        st.markdown("---")

        # --- SECCIÓN 3: Tiempo en Zonas (sin cambios) ---
        st.subheader("📊 Tiempo en Zonas")
        # ... (código de zonas sin cambios) ...
        col_pow, col_hr = st.columns(2)
        with col_pow:
            st.write("**Zonas de Potencia**")
            power_zones = actual.get("icu_zone_times", [])
            total_time = actual.get("moving_time", 1)
            for i, zone_data in enumerate(power_zones[:7]):
                zone_time = zone_data.get('secs', 0)
                if zone_time > 0:
                    st.text(f"Z{i+1}: {format_duration(zone_time)}")
                    st.progress(zone_time / total_time)
        with col_hr:
            st.write("**Zonas de Frecuencia Cardíaca**")
            hr_zones = actual.get("icu_hr_zone_times", [])
            if hr_zones and sum(hr_zones) > 0:
                total_time_hr = sum(hr_zones)
                for i, zone_time in enumerate(hr_zones):
                    if zone_time > 0:
                        st.text(f"Z{i+1}: {format_duration(zone_time)}")
                        st.progress(zone_time / total_time_hr)