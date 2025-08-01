import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN CON CLAVES INTEGRADAS ---
st.set_page_config(layout="wide", page_title="Análisis de Eficiencia Cardiovascular")

ATHLETE_ID = "i10474"
API_KEY = "27i9azt55smmhvg1ogc5gmn7x"
MAX_HR = 173

# --- FUNCIONES AUXILIARES ---
def format_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0: return "0m"
    h, m = divmod(seconds // 60, 60)
    return f"{int(h)}h {int(m)}m" if h > 0 else f"{int(m)}m"

# --- LÓGICA DE ANÁLISIS V3.3 ---
@st.cache_data(ttl=3600)
def fetch_data(end_date, days_to_fetch=180):
    start_date = end_date - timedelta(days=days_to_fetch)
    date_format = "%Y-%m-%d"
    s, e = start_date.strftime(date_format), end_date.strftime(date_format)
    auth_tuple = ('API_KEY', API_KEY)
    
    activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={s}&newest={e}"
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness?oldest={s}&newest={e}"
    
    try:
        activities_response = requests.get(activities_url, auth=auth_tuple)
        wellness_response = requests.get(wellness_url, auth=auth_tuple)
        activities_response.raise_for_status()
        wellness_response.raise_for_status()
        activities = activities_response.json()
        wellness = wellness_response.json()
        return [
            act for act in activities 
            if act.get('type') in ['Ride', 'VirtualRide'] and act.get("icu_zone_times")
        ], wellness
    except requests.exceptions.RequestException as e:
        st.error(f"Error al conectar con la API de Intervals.icu: {e}")
        return [], []

def calculate_metrics_v3(activity, rhr):
    power_weights = {2: 1, 3: 2, 4: 3, 5: 3, 6: 3} 
    hr_weights = {2: 1, 3: 2, 4: 3, 5: 3, 6: 3}

    power_zones_raw = activity.get("icu_zone_times", [])
    if power_zones_raw and isinstance(power_zones_raw[0], dict):
        power_zones = [z.get('secs', 0) for z in power_zones_raw]
    else:
        power_zones = power_zones_raw

    weighted_power_time = sum(secs * power_weights.get(i, 0) for i, secs in enumerate(power_zones) if i >= 2)
    hr_zones = activity.get("icu_hr_zone_times", [])
    weighted_hr_time = sum(t * hr_weights.get(i, 0) for i, t in enumerate(hr_zones) if i >= 2)
    weighted_iec = (weighted_power_time / weighted_hr_time) if weighted_hr_time > 0 else 0
    
    np_watts = activity.get('icu_weighted_avg_watts')
    avg_hr = activity.get('average_heartrate')
    ef = (np_watts / avg_hr) if np_watts and avg_hr and avg_hr > 0 else 0
    
    hrr_percent = 0
    max_hr_numeric = int(MAX_HR)
    if avg_hr and rhr and max_hr_numeric and (max_hr_numeric - rhr) > 0:
        hrr_percent = ((avg_hr - rhr) / (max_hr_numeric - rhr)) * 100

    return {
        "weighted_iec": weighted_iec, "ef": ef,
        "power_zones_data": {f"Z{i+1}": secs for i, secs in enumerate(power_zones)},
        "hr_zones_data": {f"Z{i+1}": t for i, t in enumerate(hr_zones)},
        "hrr_percent": hrr_percent
    }

def calculate_weighted_iec_trend(activities, wellness_data, today_activity_id, num_sessions=4):
    past_rides = sorted([act for act in activities if act['id'] != today_activity_id], key=lambda x: x['start_date_local'], reverse=True)
    sessions_for_trend = past_rides[:num_sessions]
    iec_tss_pairs = []
    for act in sessions_for_trend:
        tss, rhr = act.get('icu_training_load', 0), next((w.get('restingHR') for w in wellness_data if w['id'] == act['start_date_local'][:10]), None)
        if tss > 0 and rhr:
            metrics = calculate_metrics_v3(act, rhr)
            iec = metrics.get('weighted_iec', 0)
            if iec > 0: iec_tss_pairs.append({'iec': iec, 'tss': tss})
    if not iec_tss_pairs: return 0
    df = pd.DataFrame(iec_tss_pairs)
    if df['tss'].sum() == 0: return 0
    return np.average(df['iec'], weights=df['tss'])

def get_iec_interpretation(iec, if_val, decoupling):
    if iec > 2.5 and if_val <= 0.78: return "✅ **Eficiencia excelente a baja carga:** Gran señal de forma aeróbica. Tu motor funciona muy bien a bajas revoluciones, lo que indica una base sólida."
    if iec > 2.5 and if_val >= 0.85 and decoupling > 8: return "⚠️ **Potencia mantenida a alto coste cardíaco:** Has logrado una buena eficiencia, pero el alto desacoplamiento sugiere que has tenido que forzar para mantener el ritmo, posiblemente por fatiga o condiciones adversas."
    if iec < 2.0 and if_val > 0.8: return "🤔 **Día exigente con eficiencia limitada:** La eficiencia ha sido baja para la intensidad marcada. Puede ser un indicador de fatiga acumulada, mala nutrición/hidratación o condiciones externas (calor, viento)."
    if iec > 2.8 and if_val > 0.8 and decoupling < 5: return "🚀 **Rendimiento de pico:** Has combinado una altísima eficiencia con una intensidad elevada y un control de la fatiga excelente. ¡Una señal de estado de forma óptimo!"
    return "📈 **Análisis estándar:** La sesión se encuentra dentro de los parámetros normales. Revisa las tendencias a lo largo del tiempo para ver tu progreso."

# --- MÓDULO DE COMPARACIÓN MEJORADO ---
def find_comparison_sessions(today_activity, all_activities):
    past_activities = sorted([act for act in all_activities if act['id'] != today_activity['id']], key=lambda x: x['start_date_local'], reverse=True)
    
    # --- MODIFICADO: Búsqueda de ruta insensible a mayúsculas/minúsculas y espacios ---
    today_name_clean = today_activity.get('name', '').strip().lower()
    same_route_session = next((act for act in past_activities if act.get('name', '').strip().lower() == today_name_clean), None)
    
    duration_tolerance, today_duration = timedelta(minutes=10).total_seconds(), today_activity.get('moving_time', 0)
    z2_sessions = []
    for act in past_activities:
        power_zones_raw = act.get("icu_zone_times", [])
        if power_zones_raw:
            power_zones = [z.get('secs', 0) for z in power_zones_raw] if isinstance(power_zones_raw[0], dict) else power_zones_raw
            if len(power_zones) > 1 and power_zones[1] == max(power_zones):
                z2_sessions.append(act)
    similar_z2_session = next((act for act in z2_sessions if abs(act.get('moving_time', 0) - today_duration) <= duration_tolerance), None)
    
    return same_route_session, similar_z2_session

def display_comparison_card(title, today_activity, comp_activity, today_metrics, wellness_data):
    st.subheader(title)
    
    comp_rhr = next((w.get('restingHR') for w in wellness_data if w['id'] == comp_activity['start_date_local'][:10]), None)
    if not comp_rhr:
        st.warning(f"Sesión encontrada ('{comp_activity.get('name')}' del {comp_activity['start_date_local'][:10]}), pero no se puede comparar porque no tiene datos de RHR (FC en Reposo) registrados ese día.", icon="⚠️")
        return

    comp_metrics = calculate_metrics_v3(comp_activity, comp_rhr)
    
    metrics_to_compare = {"IEC Ponderado": ("weighted_iec", ".2f"), "Efficiency Factor": ("ef", ".2f"), "Desacoplamiento": ("decoupling", ".1f", "%"), "HRR%": ("hrr_percent", ".1f", "%"), "RPE (Sesión)": ("session_rpe", ".0f")}
    
    today_metrics.update({'decoupling': today_activity.get('decoupling', 0), 'session_rpe': today_activity.get('session_rpe')})
    comp_metrics.update({'decoupling': comp_activity.get('decoupling', 0), 'session_rpe': comp_activity.get('session_rpe')})

    # --- MODIFICADO: Título de comparación más descriptivo ---
    st.caption(f"Comparando con: **'{comp_activity.get('name')}'** del {comp_activity['start_date_local'][:10]}")
    
    for label, (key, fmt, *suffix) in metrics_to_compare.items():
        current_val, past_val = today_metrics.get(key), comp_metrics.get(key)
        if current_val is not None and past_val is not None and past_val > 0:
            diff_percent = ((current_val - past_val) / past_val) * 100
            val_str, delta_str = f"{current_val:{fmt}}{suffix[0] if suffix else ''} vs {past_val:{fmt}}{suffix[0] if suffix else ''}", f"{diff_percent:+.1f}%"
            st.metric(label=label, value=val_str, delta=delta_str)

# --- INTERFAZ DE USUARIO V3.3 ---
st.title("⚡️ Análisis de Eficiencia Cardiovascular (v3.3)")
selected_date = st.date_input("Selecciona la fecha del entrenamiento a analizar", datetime.now().date())

if selected_date:
    activities, wellness_data = fetch_data(selected_date)
    today_activity = next((act for act in activities if act['start_date_local'].startswith(selected_date.strftime('%Y-%m-%d'))), None)
    
    if not today_activity:
        st.info("ℹ️ No se encontró ninguna actividad de ciclismo completada para este día.")
    else:
        today_wellness = next((w for w in wellness_data if w['id'] == selected_date.strftime('%Y-%m-%d')), {})
        today_rhr = today_wellness.get('restingHR')
        if not today_rhr:
            st.warning("⚠️ No se encontraron datos de RHR para hoy. Algunos cálculos pueden ser imprecisos.", icon="🚨")
            today_rhr = 0

        today_metrics = calculate_metrics_v3(today_activity, today_rhr)
        intensity_factor, decoupling = today_activity.get('icu_intensity', 0) / 100, today_activity.get('decoupling', 0)
        trend_iec_weighted = calculate_weighted_iec_trend(activities, wellness_data, today_activity['id'])
        interpretation_text = get_iec_interpretation(today_metrics['weighted_iec'], intensity_factor, decoupling)
        route_name = today_activity.get('name', 'Entrenamiento sin nombre')

        st.header(f"Análisis para: *{route_name}*")
        st.markdown("---")
        st.subheader("📊 Cuadro de Mandos de la Sesión")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="IEC Ponderado (v3)", value=f"{today_metrics['weighted_iec']:.2f}", help="Eficiencia en intensidad (Z3+). Más alto es mejor.")
            if trend_iec_weighted > 0: st.caption(f"Tendencia (4 sesiones): {trend_iec_weighted:.2f}")
        with col2:
            st.metric(label="Factor de Intensidad (IF)", value=f"{intensity_factor:.2f}", help="Dureza relativa de la sesión vs tu FTP.")
        with col3:
            st.metric(label="Desacoplamiento (Pw:HR)", value=f"{decoupling:.1f}%", help="Pérdida de eficiencia por fatiga. <5% es ideal.")
        with col4:
            st.metric(label="Utilización de FCR (HRR%)", value=f"{today_metrics['hrr_percent']:.1f}%", help="Estrés cardiovascular relativo de la sesión.")
        
        st.markdown("---")
        st.subheader("💡 Diagnóstico de la Sesión")
        st.markdown(interpretation_text)
        
        st.markdown("---")
        st.header("🔄 Comparativa con Sesiones Anteriores")
        same_route_session, similar_z2_session = find_comparison_sessions(today_activity, activities)
        comp_col1, comp_col2 = st.columns(2)
        with comp_col1:
            if same_route_session:
                display_comparison_card("🆚 Misma Ruta", today_activity, same_route_session, today_metrics.copy(), wellness_data)
            else: st.info("No se encontró una sesión anterior con el mismo nombre de ruta para comparar.")
        with comp_col2:
            if similar_z2_session:
                display_comparison_card("🆚 Sesión Z2 Similar", today_activity, similar_z2_session, today_metrics.copy(), wellness_data)
            else: st.info("No se encontró una sesión Z2 de duración similar para comparar.")

        st.markdown("---")
        st.subheader("📊 Tiempo en Zonas")
        # ... (código de las gráficas de zonas, sin cambios)
        col_pow, col_hr = st.columns(2)
        with col_pow:
            st.write("**Zonas de Potencia**")
            power_df = pd.DataFrame.from_dict(today_metrics['power_zones_data'], orient='index', columns=['Segundos'])
            if not power_df[power_df.Segundos > 0].empty: st.bar_chart(power_df)
        with col_hr:
            st.write("**Zonas de Frecuencia Cardíaca**")
            hr_df = pd.DataFrame.from_dict(today_metrics['hr_zones_data'], orient='index', columns=['Segundos'])
            if not hr_df[hr_df.Segundos > 0].empty: st.bar_chart(hr_df)
            
        # --- MODIFICADO: Guía de interpretación restaurada y completa ---
        with st.expander("📖 Guía de Interpretación de Datos (v3.3)"):
            st.markdown("""
            #### **Interpretando el Cuadro de Mandos**
            * **IEC Ponderado (v3):**
                * **¿Qué es?** Mide tu eficiencia en intensidad (Z3+). Un número alto es mejor.
                * **Tendencia (4 sesiones):** Es la media de tu IEC en las últimas 4 sesiones, ponderada por su dureza (TSS). **Este es tu indicador clave de progreso.**
            * **Factor de Intensidad (IF):**
                * **¿Qué es?** La dureza relativa de la sesión en comparación con tu umbral (FTP).
                * **Interpretación:** Nos da el **contexto de la dureza**. Un IEC alto en un día de IF bajo es bueno, pero un IEC alto en un día de IF alto es excelente.
            * **Desacoplamiento (Pw:HR):**
                * **¿Qué es?** Mide si tu corazón se "descontrola" para mantener la misma potencia, una señal de fatiga. Un valor bajo (`< 5%`) es ideal.
            * **Utilización de FCR (HRR%):**
                * **¿Qué es?** Mide qué porcentaje de tu "rango de trabajo" del corazón (`FC Máxima - FC Reposo`) has utilizado de media.
                * **Interpretación:** Nos da una idea del estrés cardiovascular real.

            ---
            #### **El Diagnóstico Automático**
            Esta sección combina las métricas anteriores para darte una conclusión directa sobre tu rendimiento en la sesión, ayudándote a entender si fue un día de construcción de base, un pico de forma o una señal de que necesitas descansar.
            
            ---
            #### **La Comparativa Automática**
            * **¿Qué es?** Compara tu sesión actual con entrenamientos pasados para darte un contexto real de tu progreso.
            * **Misma Ruta:** Compara con la última vez que hiciste este recorrido. Es la mejor forma de ver si eres más eficiente en el mismo circuito.
            * **Sesión Z2 Similar:** Compara con un entrenamiento de resistencia de duración parecida. Ideal para ver si tu base aeróbica está mejorando.
            * **Delta (`Δ`):** Muestra el cambio porcentual. Un delta positivo verde (`+X%`) significa que has mejorado en esa métrica respecto a la sesión pasada.
            """)