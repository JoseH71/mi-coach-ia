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
    # Usando valores de respaldo si los secretos no están disponibles
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
    if pd.isna(seconds) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return None
    minutes_total = int(seconds / 60)
    hours, minutes = divmod(minutes_total, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def process_and_format_activity(activity):
    """Procesa una actividad y la formatea como un string organizado por secciones."""
    
    # --- MODIFICADO: Se añade el diccionario 'wellness' ---
    summary, load, power, hr, cadence, zones, garmin, subjective, wellness = {}, {}, {}, {}, {}, {}, {}, {}, {}

    # --- POBLAR DICCIONARIOS CON LÓGICA CONDICIONAL MEJORADA ---
    summary['Actividad'] = f"**{activity.get('name', 'Sin Nombre')}**"
    if activity.get('type'): summary['Tipo'] = activity.get('type')
    if activity.get('start_date_local'): summary['Fecha'] = activity.get('start_date_local', 'Sin fecha')[:10]
    if activity.get('moving_time'): summary['Duración'] = format_duration(activity.get('moving_time'))
    if activity.get('distance'): summary['Distancia'] = f"{activity.get('distance', 0) / 1000:.2f} km"
    # --- NUEVO: Métricas de Velocidad (convertidas de m/s a km/h) ---
    if activity.get('average_speed'): summary['Velocidad Media'] = f"{activity.get('average_speed') * 3.6:.1f} km/h"
    if activity.get('max_speed'): summary['Velocidad Máxima'] = f"{activity.get('max_speed') * 3.6:.1f} km/h"
    if activity.get('total_elevation_gain'): summary['Desnivel Positivo'] = f"{activity.get('total_elevation_gain', 0):.0f} m"
    if activity.get('total_elevation_loss'): summary['Desnivel Negativo'] = f"{activity.get('total_elevation_loss', 0):.0f} m"
    if activity.get('icu_joules'): summary['Trabajo Total'] = f"{activity.get('icu_joules', 0) / 1000:.0f} kJ"
    # --- NUEVO: Calorías, descripción y equipamiento ---
    if activity.get('calories'): summary['Calorías'] = f"{activity.get('calories', 0):.0f} kcal"
    if activity.get('average_temp') is not None: summary['Temperatura Media'] = f"{activity.get('average_temp'):.1f} °C"
    if activity.get('description'): summary['Notas'] = activity.get('description')
    if activity.get('gear'): summary['Equipamiento'] = activity.get('gear')

    if activity.get('icu_training_load'): load['TSS'] = f"{activity.get('icu_training_load', 0):.0f}"
    if activity.get('hr_load'): load['Carga de FC'] = f"{activity.get('hr_load', 0):.0f}"
    if activity.get('icu_intensity'): load['IF'] = f"{activity.get('icu_intensity', 0) / 100:.2f}"
    if activity.get('icu_ctl'): load['CTL (al inicio)'] = f"{activity.get('icu_ctl', 0):.1f}"
    if activity.get('icu_atl'): load['ATL (al inicio)'] = f"{activity.get('icu_atl', 0):.1f}"
    if activity.get('icu_rolling_ftp'): load['FTP Rodante (eFTP)'] = f"{activity.get('icu_rolling_ftp', 0):.0f} W"
    # --- NUEVO: VO2max estimado por eFTP ---
    if activity.get('icu_vo2max_eftp'): load['VO2max (eFTP)'] = f"{activity.get('icu_vo2max_eftp'):.1f}"
    if activity.get('polarization_index'): load['Índice de Polarización'] = f"{activity.get('polarization_index', 0):.2f}"
    
    if activity.get('average_watts'): power['Potencia Media'] = f"{activity.get('average_watts', 0):.0f} W"
    if activity.get('icu_weighted_avg_watts'): power['Potencia Normalizada (NP)'] = f"{activity.get('icu_weighted_avg_watts', 0):.0f} W"
    if activity.get('max_watts'): power['Potencia Máxima'] = f"{activity.get('max_watts', 0):.0f} W"
    if activity.get('icu_variability_index'): power['Índice de Variabilidad (VI)'] = f"{activity.get('icu_variability_index', 0):.2f}"
    if activity.get('weighted_avg_power_lr_balance'): power['Balance I/D'] = f"{activity.get('weighted_avg_power_lr_balance', 0):.1f}%"
    if activity.get('icu_joules_above_ftp'): power['kJ por encima de FTP'] = f"{activity.get('icu_joules_above_ftp', 0) / 1000:.1f} kJ"
    # --- NUEVO: Balance de W' ---
    if activity.get('w_prime_balance') is not None: power['Balance de W\' (final)'] = f"{activity.get('w_prime_balance') * 100:.1f}%"

    if activity.get('average_heartrate'): hr['FC Media'] = f"{activity.get('average_heartrate', 0):.0f} bpm"
    if activity.get('max_heartrate'): hr['FC Máx'] = f"{activity.get('max_heartrate', 0):.0f} bpm"
    if activity.get('decoupling'): hr['Desacoplamiento (Pw:HR)'] = f"{activity.get('decoupling', 0):.1f}%"
    
    # --- MODIFICADO: Lógica de cálculo de eficiencia mejorada ---
    power_norm = activity.get("icu_weighted_avg_watts")
    hr_avg = activity.get("average_heartrate")
    power_avg = activity.get("average_watts")
    
    if hr_avg and power_norm and hr_avg > 0 and power_norm > 0:
        efficiency_val = activity.get('icu_efficiency_factor')
        if not efficiency_val or efficiency_val == 0:
            efficiency_val = round(power_norm / hr_avg, 2)
        hr['Eficiencia (NP/FC)'] = f"{efficiency_val:.2f}"
        
    if hr_avg and power_avg and hr_avg > 0 and power_avg > 0:
        power_hr_calc = round(power_avg / hr_avg, 2)
        hr['Potencia/FC'] = f"{power_hr_calc:.2f}"
        
    if activity.get('icu_power_hr_z2'): hr['Eficiencia Z2 (Pot/FC)'] = f"{activity.get('icu_power_hr_z2', 0):.2f}"
    
    if activity.get('average_cadence'): cadence['Cadencia Media'] = f"{activity.get('average_cadence', 0):.0f}"
    if activity.get('max_cadence'): cadence['Cadencia Máxima'] = f"{activity.get('max_cadence', 0):.0f}"

    if activity.get('compliance'): subjective['Cumplimiento del Plan'] = f"{activity.get('compliance', 0):.1f}%"
    if activity.get('icu_rpe'): subjective['RPE (ICU)'] = activity.get('icu_rpe')
    if activity.get('session_rpe'): subjective['RPE (Sesión)'] = activity.get('session_rpe')
    if activity.get('feel'): subjective['Sensaciones (1-5)'] = activity.get('feel')
    
    # --- Lógica de Zonas (sin cambios, ya era robusta) ---
    hr_zones_secs = activity.get('icu_hr_zone_times', [])
    if hr_zones_secs and isinstance(hr_zones_secs, list) and sum(hr_zones_secs) > 0:
        zones['Zonas de FC'] = ", ".join([f"Z{i+1}: {format_duration(secs)}" for i, secs in enumerate(hr_zones_secs) if secs > 0])
    
    power_zones_raw = activity.get('icu_zone_times', [])
    power_zones_secs = []
    if power_zones_raw and isinstance(power_zones_raw, list) and len(power_zones_raw) > 0:
        if isinstance(power_zones_raw[0], (int, float)):
            power_zones_secs = power_zones_raw
        elif isinstance(power_zones_raw[0], dict):
            temp_secs = [0] * 7 
            for zone_data in power_zones_raw:
                if 'id' in zone_data and zone_data['id'].startswith('Z'):
                    try:
                        zone_index = int(zone_data['id'][1:]) - 1
                        if 0 <= zone_index < len(temp_secs):
                            temp_secs[zone_index] = zone_data.get('secs', 0)
                    except (ValueError, IndexError):
                        continue
            power_zones_secs = temp_secs
    if power_zones_secs and sum(power_zones_secs) > 0:
        zones['Zonas de Potencia'] = ", ".join([f"Z{i+1}: {format_duration(secs)}" for i, secs in enumerate(power_zones_secs) if secs > 0])

    if activity.get('VO2MaxGarmin'): garmin['VO2max (Garmin)'] = f"{activity.get('VO2MaxGarmin'):.1f}"
    if activity.get('AerobicEffect'): garmin['Training Effect Aeróbico'] = f"{activity.get('AerobicEffect'):.1f}"
    if activity.get('AnaerobicEffect'): garmin['Training Effect Anaeróbico'] = f"{activity.get('AnaerobicEffect'):.1f}"
    if activity.get('RecoveryTime'): garmin['Tiempo de Recuperación Sugerido'] = f"{activity.get('RecoveryTime', 0):.0f} horas"

    # --- NUEVO: Sección de Bienestar ---
    if activity.get('icu_hrv'): wellness['HRV (mañana)'] = f"{activity.get('icu_hrv')} ms"
    if activity.get('icu_resting_hr'): wellness['FC en Reposo (mañana)'] = f"{activity.get('icu_resting_hr')} bpm"

    # --- Construir el string final ---
    final_output_parts = []
    # --- MODIFICADO: Añadida la nueva sección 'wellness' ---
    sections = {
        "--- RESUMEN GENERAL ---": summary,
        "--- MÉTRICAS DE CARGA Y FITNESS ---": load,
        "--- MÉTRICAS DE BIENESTAR (DÍA DE LA ACTIVIDAD) ---": wellness, # NUEVA SECCIÓN
        "--- MÉTRICAS DE POTENCIA ---": power,
        "--- MÉTRICAS DE FRECUENCIA CARDÍACA ---": hr,
        "--- MÉTRICAS DE CADENCIA ---": cadence,
        "--- DISTRIBUCIÓN DE ZONAS ---": zones,
        "--- MÉTRICAS DE GARMIN ---": garmin,
        "--- MÉTRICAS SUBJETIVAS Y DE CUMPLIMIENTO ---": subjective
    }

    # --- MODIFICADO: La lógica de limpieza ahora es más sencilla porque los diccionarios ya vienen filtrados ---
    for title, data_dict in sections.items():
        if data_dict: # Solo procesar si el diccionario no está vacío
            final_output_parts.append(title)
            for key, value in data_dict.items():
                final_output_parts.append(f"{key}: {value}")
            final_output_parts.append("") 

    return "\n".join(final_output_parts)

# --- INTERFAZ DE USUARIO ---
st.title("📄 Extractor de Actividad para Análisis")
st.caption("Selecciona una fecha para extraer todos los datos de una actividad en formato de texto, listo para copiar y pegar.")

selected_date = st.date_input("Selecciona la fecha de la actividad", datetime.now())

if selected_date:
    date_str = selected_date.strftime("%Y-%m-%d")
    activities = fetch_activities_for_date(date_str)
    
    if activities:
        st.markdown("---")
        if len(activities) > 1:
            activity_options = {f"{act.get('name', 'Actividad sin nombre')} ({act.get('type', '')} - {format_duration(act.get('moving_time'))})": act for act in activities}
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