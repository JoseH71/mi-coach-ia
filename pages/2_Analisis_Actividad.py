import streamlit as st
import requests
from datetime import datetime
import base64
import pandas as pd

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="Extractor de Actividad")

try:
    API_KEY = st.secrets["API_KEY"]
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
except (FileNotFoundError, KeyError):
    API_KEY = "27i9azt55smmhvg1ogc5gmn7x"
    ATHLETE_ID = "i10474"

HEADERS = {"Authorization": f"Basic {base64.b64encode(f'API_KEY:{API_KEY}'.encode()).decode()}"}
BASE_URL = "https://intervals.icu/api/v1"

# --- FUNCIONES ---
@st.cache_data(ttl=3600)
def fetch_activities_for_date(date_str):
    """Obtiene todas las actividades para una fecha específica."""
    try:
        url = f"{BASE_URL}/athlete/{ATHLETE_ID}/activities?oldest={date_str}&newest={date_str}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error al consultar la API: {e}")
        return []

def format_duration(seconds):
    """Formatea segundos a un formato Xh Ym."""
    if pd.isna(seconds) or not isinstance(seconds, (int, float)) or seconds < 0:
        return None
    minutes_total = int(seconds / 60)
    hours, minutes = divmod(minutes_total, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def process_and_format_activity(activity):
    """Procesa una actividad y la formatea como un string organizado por secciones."""
    
    summary, load, power, hr, cadence, zones, garmin, subjective = {}, {}, {}, {}, {}, {}, {}, {}

    # --- POBLAR DICCIONARIOS CON TODOS LOS DATOS DISPONIBLES ---
    
    summary['Actividad'] = f"**{activity.get('name', 'Sin Nombre')}**"
    summary['Tipo'] = activity.get('type')
    summary['Fecha'] = activity.get('start_date_local', 'Sin fecha')[:10]
    summary['Duración'] = format_duration(activity.get('moving_time'))
    summary['Distancia'] = f"{activity.get('distance', 0) / 1000:.2f} km"
    summary['Desnivel Positivo'] = f"{activity.get('total_elevation_gain', 0):.0f} m"
    summary['Desnivel Negativo'] = f"{activity.get('total_elevation_loss', 0):.0f} m"
    summary['Trabajo Total'] = f"{activity.get('icu_joules', 0) / 1000:.0f} kJ"
    summary['Temperatura Media'] = f"{activity.get('average_temp', 0):.1f} °C" if activity.get('average_temp') is not None else None

    load['TSS'] = f"{activity.get('icu_training_load', 0):.0f}"
    load['Carga de FC'] = f"{activity.get('hr_load', 0):.0f}"
    load['IF'] = f"{activity.get('icu_intensity', 0) / 100:.2f}"
    load['CTL (al inicio)'] = f"{activity.get('icu_ctl', 0):.1f}"
    load['ATL (al inicio)'] = f"{activity.get('icu_atl', 0):.1f}"
    load['FTP Rodante (eFTP)'] = f"{activity.get('icu_rolling_ftp', 0):.0f} W"
    
    power['Potencia Media'] = f"{activity.get('average_watts', 0):.0f} W"
    power['Potencia Normalizada (NP)'] = f"{activity.get('icu_weighted_avg_watts', 0):.0f} W"
    power['Potencia Máxima'] = f"{activity.get('max_watts', 0):.0f} W"
    power['Índice de Variabilidad (VI)'] = f"{activity.get('icu_variability_index', 0):.2f}"
    power['Potencia/FC en Z2'] = f"{activity.get('icu_power_hr_z2', 0):.2f}"
    power['Balance I/D'] = f"{activity.get('weighted_avg_power_lr_balance', 0):.1f}%"
    power['kJ por encima de FTP'] = f"{activity.get('icu_joules_above_ftp', 0) / 1000:.1f} kJ"

    hr['FC Media'] = f"{activity.get('average_heartrate', 0):.0f} bpm"
    hr['FC Máx'] = f"{activity.get('max_heartrate', 0):.0f} bpm"
    hr['Desacoplamiento (Pw:HR)'] = f"{activity.get('decoupling', 0):.1f}%"
    hr['Eficiencia (NP/FC)'] = f"{activity.get('icu_efficiency', 0):.2f}"
    
    cadence['Cadencia Media'] = f"{activity.get('average_cadence', 0):.0f}"
    cadence['Cadencia Máxima'] = f"{activity.get('max_cadence', 0):.0f}"

    subjective['Cumplimiento del Plan'] = f"{activity.get('compliance', 0):.1f}%"
    subjective['RPE (ICU)'] = activity.get('icu_rpe')
    subjective['RPE (Sesión)'] = activity.get('session_rpe')
    subjective['Sensaciones (1-5)'] = activity.get('feel')
    
    # --- INICIO DE LA CORRECCIÓN DEFINITIVA PARA ZONAS ---
    hr_zones_secs = activity.get('icu_hr_zone_times', [])
    power_zones_raw = activity.get('icu_zone_times', [])
    
    if hr_zones_secs and isinstance(hr_zones_secs, list) and sum(hr_zones_secs) > 0:
        zones['Zonas de FC'] = ", ".join([f"Z{i+1}: {format_duration(secs)}" for i, secs in enumerate(hr_zones_secs)])
    
    power_zones_secs = []
    if power_zones_raw and isinstance(power_zones_raw, list) and len(power_zones_raw) > 0:
        # Comprobar si es una lista de números (formato antiguo/simple)
        if isinstance(power_zones_raw[0], (int, float)):
            power_zones_secs = power_zones_raw
        # Comprobar si es una lista de diccionarios (formato nuevo/complejo)
        elif isinstance(power_zones_raw[0], dict):
            # Llenar una lista temporal con los segundos de cada zona
            temp_secs = [0] * 7
            for zone_data in power_zones_raw:
                if 'id' in zone_data and zone_data['id'].startswith('Z'):
                    try:
                        zone_index = int(zone_data['id'][1:]) - 1
                        if 0 <= zone_index < 7:
                            temp_secs[zone_index] = zone_data.get('secs', 0)
                    except (ValueError, IndexError):
                        continue
            power_zones_secs = temp_secs

    if power_zones_secs and sum(power_zones_secs) > 0:
        zones['Zonas de Potencia'] = ", ".join([f"Z{i+1}: {format_duration(secs)}" for i, secs in enumerate(power_zones_secs)])
    # --- FIN DE LA CORRECCIÓN ---

    # Métricas de Garmin
    if activity.get('vo2max'): garmin['VO2max (Garmin)'] = f"{activity.get('vo2max'):.1f}"
    if activity.get('aerobic_training_effect'): garmin['Training Effect Aeróbico'] = f"{activity.get('aerobic_training_effect'):.1f}"
    if activity.get('anaerobic_training_effect'): garmin['Training Effect Anaeróbico'] = f"{activity.get('anaerobic_training_effect'):.1f}"
    if activity.get('recovery_hours'): garmin['Tiempo de Recuperación Sugerido'] = f"{activity.get('recovery_hours')} horas"

    # Construir el string final
    final_output_parts = []
    sections = {
        "--- RESUMEN GENERAL ---": summary,
        "--- MÉTRICAS DE CARGA Y FITNESS ---": load,
        "--- MÉTRICAS DE POTENCIA ---": power,
        "--- MÉTRICAS DE FRECUENCIA CARDÍACA ---": hr,
        "--- MÉTRICAS DE CADENCIA ---": cadence,
        "--- DISTRIBUCIÓN DE ZONAS ---": zones,
        "--- MÉTRICAS DE GARMIN ---": garmin,
        "--- MÉTRICAS SUBJETIVAS Y DE CUMPLIMIENTO ---": subjective
    }

    for title, data_dict in sections.items():
        clean_dict = {k: v for k, v in data_dict.items() if v is not None and str(v).replace('.','').replace('%','').replace(' ','').replace('W','').replace('bpm','').replace('km','').replace('m','').replace('kJ','').replace('h','').replace('°C','') != "0"}
        if clean_dict:
            final_output_parts.append(title)
            for key, value in clean_dict.items():
                final_output_parts.append(f"{key}: {value}")
            final_output_parts.append("") 

    return "\n".join(final_output_parts)

# --- INTERFAZ DE USUARIO ---
st.title("📄 Extractor de Actividad para Análisis")
st.caption("Selecciona una fecha para extraer todos los datos de una actividad en formato de texto, listo para copiar y pegar.")

selected_date = st.date_input("Selecciona la fecha de la actividad", datetime.now().date())

if selected_date:
    date_str = selected_date.strftime("%Y-%m-%d")
    activities = fetch_activities_for_date(date_str)
    
    if activities:
        st.markdown("---")
        if len(activities) > 1:
            activity_options = {f"{act.get('name', 'Actividad sin nombre')} ({format_duration(act.get('moving_time'))})": act for act in activities}
            selected_activity_name = st.selectbox("Se encontró más de una actividad, selecciona una:", activity_options.keys())
            selected_activity = activity_options[selected_activity_name]
        else:
            selected_activity = activities[0]
        
        st.subheader(f"Análisis para: **{selected_activity.get('name', 'Actividad sin nombre')}**")
        
        activity_summary_text = process_and_format_activity(selected_activity)

        st.text_area(
            "Resumen para Copiar y Pegar",
            value=activity_summary_text,
            height=600,
            help="Haz clic aquí, pulsa Ctrl+A (o Cmd+A en Mac) para seleccionar todo, y luego Ctrl+C (o Cmd+C) para copiar."
        )
    else:
        st.info(f"ℹ️ No se encontraron actividades para el {selected_date.strftime('%d-%m-%Y')}.")