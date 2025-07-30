import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
from statistics import mean
import base64

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(layout="wide", page_title="Planificador de Mesociclos")

# --- FUNCIONES (sin cambios) ---
@st.cache_data(ttl=3600)
def fetch_data(url, headers, params=None):
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión con la API: {e}")
        return []

@st.cache_data(ttl=3600)
def get_latest_ctl(api_key, athlete_id):
    today = datetime.now().date()
    start_date = today - timedelta(days=28)
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': today.strftime('%Y-%m-%d')}
    headers = {"Authorization": f"Basic {base64.b64encode(f'API_KEY:{api_key}'.encode()).decode()}"}
    wellness_data = fetch_data(f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness", headers, params)
    
    if not wellness_data: return None
    sundays_with_ctl = [d for d in wellness_data if datetime.strptime(d['id'], '%Y-%m-%d').weekday() == 6 and d.get('ctl') is not None]
    if sundays_with_ctl: return sundays_with_ctl[-1]['ctl']
    if wellness_data: return wellness_data[-1].get('ctl')
    return None

def process_weekly_data(end_date, num_weeks=4):
    api_key = "27i9azt55smmhvg1ogc5gmn7x"
    athlete_id = "i10474"
    base_url = "https://intervals.icu/api/v1"
    headers = {"Authorization": f"Basic {base64.b64encode(f'API_KEY:{api_key}'.encode()).decode()}"}
    
    start_date = end_date - timedelta(days=num_weeks * 7 - 1)
    params = {'oldest': start_date.strftime("%Y-%m-%d"), 'newest': end_date.strftime("%Y-%m-%d")}
    
    wellness_json = fetch_data(f"{base_url}/athlete/{athlete_id}/wellness", headers, params)
    activities_json = fetch_data(f"{base_url}/athlete/{athlete_id}/activities", headers, params)

    if not wellness_json: return pd.DataFrame()

    df_daily = pd.DataFrame(wellness_json)
    if df_daily.empty: return pd.DataFrame()
        
    df_daily['date'] = pd.to_datetime(df_daily['id'])
    df_daily = df_daily.set_index('date')

    weekly_data = []
    for i in range(4):
        week_end_obj = end_date - timedelta(days=7 * i)
        week_start_obj = week_end_obj - timedelta(days=6)
        
        week_wellness = df_daily[(df_daily.index >= pd.to_datetime(week_start_obj)) & (df_daily.index <= pd.to_datetime(week_end_obj))]
        week_activities = [act for act in activities_json if week_start_obj <= datetime.strptime(act['start_date_local'][:10], '%Y-%m-%d').date() <= week_end_obj]
        
        rhr_list = week_wellness['restingHR'].dropna().tolist()
        hrv_list = week_wellness['hrv'].dropna().tolist()
        sleep_list = week_wellness['sleepScore'].dropna().tolist()
        ctl_final = week_wellness['ctl'].iloc[-1] if not week_wellness.empty and 'ctl' in week_wellness.columns and not week_wellness['ctl'].dropna().empty else None
        
        total_tss = 0
        for act in week_activities:
            tss = act.get('icu_training_load', 0) or 0
            if act.get('type') == 'WeightTraining': tss = 10
            total_tss += tss
        
        power_zones_secs = [0] * 7
        for act in week_activities:
            zones = act.get('icu_zone_times') or []
            for zone_data in zones:
                if 'id' in zone_data and isinstance(zone_data['id'], str) and zone_data['id'].startswith('Z'):
                    try:
                        zone_index = int(zone_data['id'][1:]) - 1
                        if 0 <= zone_index < 7: power_zones_secs[zone_index] += (zone_data.get('secs', 0) or 0)
                    except (ValueError, IndexError): continue
        
        weekly_data.append({
            "Semana": f"{week_start_obj.strftime('%d/%m')} - {week_end_obj.strftime('%d/%m')}",
            "TSS_Realizado": total_tss, "CTL_Final": ctl_final,
            "Tiempo_Zonas_Potencia_Horas": [s / 3600 for s in power_zones_secs],
            "RHR_Avg": mean(rhr_list) if rhr_list else None,
            "HRV_Avg": mean(hrv_list) if hrv_list else None,
            "SleepScore_Avg": mean(sleep_list) if sleep_list else None,
        })
        
    df_weekly = pd.DataFrame(weekly_data).set_index("Semana")
    return df_weekly.iloc[::-1]

def generar_resumen_ejecutivo(df_weekly, planned_data):
    # (Función sin cambios)
    positivos, mejoras = [], []
    total_real_tss = df_weekly['TSS_Realizado'].sum()
    total_plan_tss = sum(d['TSS'] for d in planned_data)
    compliance_perc = (total_real_tss / total_plan_tss * 100) if total_plan_tss > 0 else 0
    if 90 <= compliance_perc <= 110: positivos.append(f"**Adherencia Excelente:** Has cumplido el plan de carga con un **{compliance_perc:.0f}%** de cumplimiento del TSS total.")
    weeks_under_z2 = 0
    for i in range(len(df_weekly)):
        real_z2 = df_weekly.iloc[i].get('Tiempo_Zonas_Potencia_Horas', [0]*7)[1]
        plan_z2 = planned_data[i].get('Z2', 0)
        if real_z2 < plan_z2 * 0.9: weeks_under_z2 += 1
    if weeks_under_z2 >= 2: mejoras.append(f"**Volumen de Base Inconsistente:** En **{weeks_under_z2} de {len(df_weekly)} semanas**, el volumen en Z2 ha estado por debajo del objetivo.")
    weeks_low_sleep = df_weekly[df_weekly['SleepScore_Avg'] < 75].shape[0]
    if weeks_low_sleep > 1: mejoras.append(f"**Calidad del Descanso:** Se detectaron **{weeks_low_sleep} semana(s)** con una puntuación de sueño media inferior a 75.")
    if compliance_perc < 90: mejoras.append(f"**Carga Insuficiente:** El TSS total se quedó en un **{compliance_perc:.0f}%** de lo planificado.")
    elif compliance_perc > 115: mejoras.append(f"**Sobrecarga Potencial:** El TSS total fue de un **{compliance_perc:.0f}%** sobre lo planificado.")
    if not positivos: positivos.append("La adherencia al plan de carga fue inconsistente.")
    if not mejoras: mejoras.append("No se detectaron puntos débiles claros. ¡Buen trabajo!")
    recomendacion = f"Jose, el balance general de este mesociclo es **positivo**. Has completado un bloque de entrenamiento sólido y exigente.\n\n"
    if "Volumen de Base Inconsistente" in " ".join(mejoras): recomendacion += "Nuestro principal foco para el próximo ciclo debe ser la **consistencia en el volumen de entrenamiento en Zona 2**.\n\n"
    else: recomendacion += "El trabajo de **intensidad ha sido de calidad** y la carga ha sido la correcta, es la línea a mantener.\n\n"
    recomendacion += "**Plan de Acción:**\n1. **🎯 Objetivo Principal:** Asegurar el **cumplimiento del 100% de las horas planificadas en Z2**.\n2. **📈 Intensidad:** Mantener la buena adherencia al trabajo de Z3/Z4 planificado.\n"
    if "Calidad del Descanso" in " ".join(mejoras): recomendacion += "3. **💤 Descanso:** Vigilar la higiene del sueño para maximizar la recuperación.\n"
    return positivos, mejoras, recomendacion

# --- INTERFAZ DE USUARIO ---
st.title("🚀 Planificador de Mesociclos Inteligente")
st.caption("Analiza el ciclo anterior para planificar el siguiente con la máxima precisión.")

today = datetime.now().date()
last_sunday = today - timedelta(days=today.weekday() + 1)
end_date_analysis = st.date_input("Último día del Mesociclo a Analizar", value=last_sunday, help="Selecciona el último día (domingo) del ciclo de 4 semanas que quieres analizar.")

st.markdown("---")
st.header("🎯 Planificación del Próximo Mesociclo")

api_key = "27i9azt55smmhvg1ogc5gmn7x"
athlete_id = "i10474"
ctl_inicial = get_latest_ctl(api_key, athlete_id)

if ctl_inicial is None:
    st.error("No se pudo obtener tu CTL inicial. Revisa la conexión.")
    st.stop()

ctl_objetivo_final = ctl_inicial + 6

plan_cols = st.columns(3)
with plan_cols[0]: st.metric("CTL Inicial (Automático)", f"{ctl_inicial:.1f}")
with plan_cols[1]: st.metric("CTL Objetivo Final (Coach IA)", f"~{ctl_objetivo_final:.0f}")
with plan_cols[2]:
    # --- INICIO: LISTA DE ENFOQUES RESTAURADA Y AMPLIADA ---
    enfoque_options = [
        "Base Extensiva (Dominio de Z2)",
        "Base Intensiva (Z2 alto y Cadencia)",
        "Introducción al Tempo (Z2 + Bloques cortos Z3)",
        "Consolidación del Tempo (Dominio de Z3)",
        "Tempo Progresivo (Z3 bajo a alto)",
        "Sweet Spot (Umbral Bajo - Z3/Z4)",
        "Mantenimiento y Técnica",
        "Bloque de Fuerza y Potencia Neuromuscular"
    ]
    enfoque = st.selectbox("Enfoque Principal del Ciclo", options=enfoque_options, index=3, help="Selecciona el objetivo fisiológico principal para las próximas 4 semanas.")
    # --- FIN: LISTA DE ENFOQUES ---

with st.form(key="planning_form"):
    # --- INICIO: LÓGICA DE PLANIFICACIÓN DINÁMICA RESTAURADA ---
    week_labels = ["Semana 1 (Carga)", "Semana 2 (Carga+)", "Semana 3 (Pico)", "Semana 4 (Descarga)"]
    
    # Valores por defecto base
    base_tss = [round(ctl_inicial * 7.5), round(ctl_inicial * 8), round(ctl_inicial * 8.5), round(ctl_inicial * 4)]
    base_z2 = [6.0, 6.5, 7.0, 3.5]
    base_z3 = [0.0, 0.0, 0.0, 0.0]
    base_z4 = [0.0, 0.0, 0.0, 0.0]

    if "Base Extensiva" in enfoque:
        default_tss, default_z2, default_z3, default_z4 = base_tss, base_z2, base_z3, base_z4
    elif "Base Intensiva" in enfoque:
        default_tss, default_z2, default_z3, default_z4 = [t + 10 for t in base_tss], [h - 0.5 for h in base_z2], [0.5, 0.5, 0.75, 0.25], base_z4
    elif "Introducción al Tempo" in enfoque:
        default_tss, default_z2, default_z3, default_z4 = [t + 20 for t in base_tss], [h - 1 for h in base_z2], [0.75, 1.0, 1.25, 0.5], base_z4
    elif "Consolidación del Tempo" in enfoque:
        default_tss, default_z2, default_z3, default_z4 = [t + 30 for t in base_tss], [h - 1.5 for h in base_z2], [1.5, 1.75, 2.0, 0.75], base_z4
    elif "Tempo Progresivo" in enfoque:
        default_tss, default_z2, default_z3, default_z4 = [t + 35 for t in base_tss], [h - 1.5 for h in base_z2], [1.75, 2.0, 2.25, 0.75], base_z4
    elif "Sweet Spot" in enfoque:
        default_tss, default_z2, default_z3, default_z4 = [t + 40 for t in base_tss], [h - 2 for h in base_z2], [1.0, 1.25, 1.25, 0.5], [0.75, 1.0, 1.25, 0.25]
    else: # Mantenimiento y otros
        default_tss, default_z2, default_z3, default_z4 = [300, 300, 300, 150], [4.0, 4.0, 4.0, 2.0], [0.5, 0.5, 0.5, 0], [0, 0, 0, 0]
    # --- FIN: LÓGICA DE PLANIFICACIÓN ---

    st.write("**Carga Semanal Planificada**")
    tss_cols = st.columns(4)
    planned_data = []
    for i, col in enumerate(tss_cols):
        with col:
            st.markdown(f"**{week_labels[i]}**")
            tss = st.number_input("TSS Objetivo", value=default_tss[i], step=10, key=f"tss_{i}")
            z2 = st.number_input("Horas en Z2 (Resistencia)", value=default_z2[i], step=0.25, format="%.2f", key=f"z2_{i}")
            z3 = st.number_input("Horas en Z3 (Tempo)", value=default_z3[i], step=0.25, format="%.2f", key=f"z3_{i}")
            z4 = st.number_input("Horas en Z4 (Umbral)", value=default_z4[i], step=0.25, format="%.2f", key=f"z4_{i}")
            planned_data.append({'TSS': tss, 'Z2': z2, 'Z3': z3, 'Z4': z4})
    
    submitted = st.form_submit_button("📊 Analizar Mesociclo Anterior")

# --- SECCIÓN 2: ANÁLISIS ---
if submitted:
    st.markdown("---")
    st.header("🔍 Análisis del Mesociclo Anterior")
    
    df_weekly = process_weekly_data(end_date_analysis)

    if df_weekly.empty:
        st.warning("No se encontraron suficientes datos para el periodo seleccionado.")
    else:
        for i in range(len(df_weekly)):
            week_real_data = df_weekly.iloc[i]
            week_plan_data = planned_data[i]
            week_name = df_weekly.index[i]
            
            st.subheader(f"Análisis de la Semana: {week_name}")
            
            with st.expander("🔬 Análisis Detallado de Zonas (Plan vs. Real)"):
                real_zones_h = week_real_data.get('Tiempo_Zonas_Potencia_Horas', [0]*7)
                plan_z2, plan_z3, plan_z4 = week_plan_data.get('Z2', 0), week_plan_data.get('Z3', 0), week_plan_data.get('Z4', 0)
                real_z5plus = sum(real_zones_h[4:])
                zones_comparison_data = {
                    'Zona': ['Z1', 'Z2', 'Z3', 'Z4', 'Z5+'],
                    'Planificado (h)': ['-', f"{plan_z2:.2f}", f"{plan_z3:.2f}", f"{plan_z4:.2f}", '-'],
                    'Realizado (h)': [f"{real_zones_h[0]:.2f}", f"{real_zones_h[1]:.2f}", f"{real_zones_h[2]:.2f}", f"{real_zones_h[3]:.2f}", f"{real_z5plus:.2f}"],
                    'Diferencia (min)': ['-', f"{(real_zones_h[1] - plan_z2) * 60:+.0f}", f"{(real_zones_h[2] - plan_z3) * 60:+.0f}", f"{(real_zones_h[3] - plan_z4) * 60:+.0f}", '-']
                }
                st.table(pd.DataFrame(zones_comparison_data).set_index('Zona'))

            st.markdown("**Respuesta Fisiológica en esta Semana:**")
            wellness_cols = st.columns(3)
            with wellness_cols[0]: st.metric("HRV Promedio", f"{week_real_data.get('HRV_Avg', 0):.1f} ms")
            with wellness_cols[1]: st.metric("RHR Promedio", f"{week_real_data.get('RHR_Avg', 0):.1f} bpm")
            with wellness_cols[2]: st.metric("Sueño Promedio", f"{week_real_data.get('SleepScore_Avg', 0):.1f}")
            
            st.markdown("---")
            
        st.header("🎯 Conclusión Final y Resumen Ejecutivo del Mesociclo")
        
        positivos, mejoras, recomendacion = generar_resumen_ejecutivo(df_weekly, planned_data)
        
        res_cols = st.columns(2)
        with res_cols[0]:
            st.subheader("✅ Lo Positivo")
            for punto in positivos:
                st.markdown(f"- {punto}")
        with res_cols[1]:
            st.subheader("⚠️ Puntos de Mejora")
            for punto in mejoras:
                st.markdown(f"- {punto}")
                
        st.subheader("🧠 Recomendación del Coach IA")
        st.info(recomendacion)