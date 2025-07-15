import streamlit as st
import requests
from datetime import datetime, timedelta
import re

# --- CONFIGURACIÓN ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except FileNotFoundError:
    st.error("❌ No se ha encontrado el fichero de secretos.")
    st.stop()
    
# --- DICCIONARIOS PARA TRADUCCIÓN ---
dias_semana_es = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"}
meses_es = {"January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril", "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto", "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre"}


# --- FUNCIONES ---
def format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0: return "0m"
    h, m = divmod(seconds // 60, 60)
    return f"{int(h)}h {int(m)}m" if h > 0 else f"{int(m)}m"

def get_week_dates(year, week_number):
    start_date = datetime.fromisocalendar(year, week_number, 1).date()
    end_date = start_date + timedelta(days=6)
    return start_date, end_date

def fetch_planned_events(start_date, end_date):
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events"
    params = {
        'oldest': start_date.strftime('%Y-%m-%d'),
        'newest': end_date.strftime('%Y-%m-%d'),
        'resolve': True 
    }
    try:
        response = requests.get(url, auth=('API_KEY', API_KEY), params=params)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error al contactar con la API: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("🗓️ Planificador Semanal")
st.write("Introduce el año y el número de la semana que quieres consultar para ver los entrenamientos programados.")

current_year = datetime.now().year
current_week = datetime.now().isocalendar().week
col1, col2 = st.columns(2)
with col1:
    selected_year = st.number_input("Año", min_value=2020, max_value=2030, value=current_year)
with col2:
    selected_week = st.number_input("Número de Semana", min_value=1, max_value=53, value=current_week)

# --- LÓGICA PARA MOSTRAR EL PLAN ---
if selected_year and selected_week:
    start_date, end_date = get_week_dates(selected_year, selected_week)
    st.header(f"Plan para la Semana {selected_week} ({start_date.strftime('%d-%m')} al {end_date.strftime('%d-%m')})")

    events = fetch_planned_events(start_date, end_date)
    if events:
        workouts = [evt for evt in events if evt.get("category") == "WORKOUT"]
        if workouts:
            workouts.sort(key=lambda x: x.get('start_date_local', ''))
            
            for workout in workouts:
                fecha_obj = datetime.fromisoformat(workout.get('start_date_local'))
                
                # --- ¡TRADUCCIÓN A ESPAÑOL! ---
                dia_en = fecha_obj.strftime('%A')
                mes_en = fecha_obj.strftime('%B')
                dia_es = dias_semana_es.get(dia_en, dia_en)
                mes_es = meses_es.get(mes_en, mes_en)
                activity_date = f"{dia_es}, {fecha_obj.day} de {mes_es}"
                
                activity_name = workout.get('name', 'Entrenamiento sin nombre')
                description = workout.get("description", "")
                
                duration_sec = workout.get('moving_time', 0)
                tss = workout.get('icu_training_load', 0)
                intensity_if = workout.get('icu_intensity', 0)
                np_planned = workout.get('_power', {}).get('value', 0)
                
                expander_title = f"**{activity_date} - {activity_name}**"
                expander_metrics = []
                if duration_sec > 0:
                    expander_metrics.append(f"Dur: {format_duration(duration_sec)}")
                if tss > 0:
                    expander_metrics.append(f"TSS: {tss:.0f}")
                if intensity_if > 0:
                    expander_metrics.append(f"IF: {intensity_if/100:.2f}")
                
                if expander_metrics:
                    expander_title += f"  |  `{' / '.join(expander_metrics)}`"

                with st.expander(expander_title):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Duración", format_duration(duration_sec))
                    c2.metric("TSS Planificado", f"{tss:.0f}")
                    c3.metric("Intensidad Planificada (%)", f"{intensity_if:.1f}%" if intensity_if > 0 else "N/A")
                    c4.metric("NP Planificada (W)", f"{np_planned:.0f}" if np_planned > 0 else "N/A")
                    
                    st.markdown("---")
                    st.markdown("##### Estructura del Entrenamiento:")
                    st.text(description if description and description.strip().lower() != 'none' else "Sin estructura detallada.")
        else:
            st.info("✅ No hay entrenamientos estructurados planificados para esta semana.")
    else:
        st.info("ℹ️ No se encontraron eventos planificados para la semana seleccionada.")