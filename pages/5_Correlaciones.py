import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import base64

# --- CONFIGURACIÓN ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except FileNotFoundError:
    ATHLETE_ID = "i10474"
    API_KEY = "27i9azt55smmhvg1ogc5gmn7x"

# --- FUNCIONES ---
@st.cache_data(ttl=3600)
def fetch_data_for_week(start_date, end_date):
    """Obtiene actividades y bienestar para UN RANGO SEMANAL ESPECÍFICO."""
    date_format = "%Y-%m-%d"
    s, e = start_date.strftime(date_format), end_date.strftime(date_format)
    
    headers = {"Authorization": f"Basic {base64.b64encode(f'API_KEY:{API_KEY}'.encode()).decode()}"}
    
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness?oldest={s}&newest={e}"
    wellness_response = requests.get(wellness_url, headers=headers)
    wellness_data = wellness_response.json() if wellness_response.status_code == 200 else []
    
    activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={s}&newest={e}"
    activities_response = requests.get(activities_url, headers=headers)
    activities_data = activities_response.json() if activities_response.status_code == 200 else []

    return wellness_data, activities_data

def process_weekly_data(start_date, end_date):
    """
    Procesa los datos para devolver un DataFrame con métricas semanales para el rango especificado.
    """
    weekly_summary = []
    
    # Calcular el número de semanas en el rango
    delta_days = (end_date - start_date).days
    num_weeks = delta_days // 7 + 1
    
    for i in range(num_weeks):
        week_start = start_date + timedelta(days=i*7)
        week_end = min(week_start + timedelta(days=6), end_date)
        
        # Si week_start es mayor que end_date, terminar el bucle
        if week_start > end_date:
            break
            
        wellness_data, activities_data = fetch_data_for_week(week_start, week_end)
        
        if not wellness_data and not activities_data:
            continue
        
        total_tss = 0
        for activity in activities_data:
            if activity.get('type') == 'WeightTraining':
                total_tss += 10
            else:
                tss = activity.get('icu_training_load')
                if pd.notna(tss):
                    total_tss += tss
        
        df_wellness_week = pd.DataFrame(wellness_data)
        
        metrics = {
            'Semana': f"{week_start.strftime('%d/%m')}-{week_end.strftime('%d/%m')}",
            'TSS Semanal': total_tss,
            'ATL': df_wellness_week['atl'].mean() if not df_wellness_week.empty and 'atl' in df_wellness_week.columns else np.nan,
            'CTL': df_wellness_week['ctl'].mean() if not df_wellness_week.empty and 'ctl' in df_wellness_week.columns else np.nan,
            'RHR': df_wellness_week['restingHR'].mean() if not df_wellness_week.empty and 'restingHR' in df_wellness_week.columns else np.nan,
            'HRV': df_wellness_week['hrv'].mean() if not df_wellness_week.empty and 'hrv' in df_wellness_week.columns else np.nan,
            'P. Sueño': df_wellness_week['sleepScore'].mean() if not df_wellness_week.empty and 'sleepScore' in df_wellness_week.columns else np.nan
        }
        weekly_summary.append(metrics)
    
    if not weekly_summary:
        return pd.DataFrame()

    df = pd.DataFrame(weekly_summary).set_index('Semana')
    return df

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("🔬 Correlaciones y Línea Basal")
st.write("Esta sección analiza la relación entre tu carga de entrenamiento y tus métricas de bienestar.")

# Selector de rango de fechas
col_fecha1, col_fecha2 = st.columns(2)
with col_fecha1:
    start_date = st.date_input(
        "Fecha de inicio del análisis:", 
        value=(datetime.now() - timedelta(days=84)).date(),  # 12 semanas por defecto
        key="start_date_correlations"
    )
with col_fecha2:
    end_date = st.date_input(
        "Fecha final del análisis:", 
        value=datetime.now().date(),
        key="end_date_correlations"
    )

# Validar rango de fechas
if start_date > end_date:
    st.error("⚠️ La fecha de inicio debe ser anterior a la fecha final.")
    st.stop()

if end_date:
    df_weekly = process_weekly_data(start_date, end_date)

    if df_weekly.empty:
        st.warning("No hay suficientes datos en el periodo seleccionado para realizar el análisis.")
    else:
        df_weekly = df_weekly.dropna(subset=['RHR', 'HRV', 'ATL', 'CTL'])
        if df_weekly.empty:
            st.warning("Los datos encontrados no tienen información de bienestar (RHR, HRV, etc.) para analizar.")
            st.stop()

        avg_atl = df_weekly['ATL'].mean()
        low_load_weeks = df_weekly[df_weekly['ATL'] <= avg_atl]
        baseline_recovery = low_load_weeks[['RHR', 'HRV', 'P. Sueño']].mean()
        baseline_chronic = df_weekly[['RHR', 'HRV', 'P. Sueño']].tail(4).mean() if len(df_weekly) >= 4 else pd.Series(dtype='float64')
        baseline_historic = df_weekly[['RHR', 'HRV', 'P. Sueño']].tail(8).mean() if len(df_weekly) >= 8 else pd.Series(dtype='float64')

        st.header("❤️ Tus Líneas Basales de Referencia")
        st.caption("Compara tu estado diario con estas tres referencias clave calculadas a partir de tus datos semanales.")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.subheader("🛌 De Recuperación")
            if not baseline_recovery.empty:
                st.metric("RHR", f"{baseline_recovery.get('RHR', 0):.1f} bpm")
                st.metric("HRV", f"{baseline_recovery.get('HRV', 0):.1f} ms")
        with col2:
            st.subheader("🗓️ Crónica (28 días)")
            if not baseline_chronic.empty:
                st.metric("RHR", f"{baseline_chronic.get('RHR', 0):.1f} bpm")
                st.metric("HRV", f"{baseline_chronic.get('HRV', 0):.1f} ms")
        with col3:
            st.subheader("📚 Histórica (60 días)")
            if not baseline_historic.empty:
                st.metric("RHR", f"{baseline_historic.get('RHR', 0):.1f} bpm")
                st.metric("HRV", f"{baseline_historic.get('HRV', 0):.1f} ms")

        st.markdown("---")

        st.header("🔥 Mapa de Calor de Correlaciones")
        st.caption("Este mapa muestra cómo se relacionan tus métricas. Valores cercanos a 1 indican una relación positiva fuerte; cercanos a -1, una relación negativa fuerte.")

        correlation_matrix = df_weekly.corr(method='pearson')
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(correlation_matrix, ax=ax, annot=True, cmap='viridis', fmt=".2f")
        st.pyplot(fig)

        # --- NUEVA SECCIÓN: TABLA DE CORRELACIONES COPIABLE ---
        st.subheader("📊 Tabla de Correlaciones - Para Copiar y Pegar")
        
        # Convertir la matriz de correlación a formato tabla copiable
        correlation_df = correlation_matrix.round(2)
        
        with st.expander("📋 Matriz de Correlaciones en Formato Tabla", expanded=True):
            # Crear texto formateado para copiar
            correlation_text = f"**MATRIZ DE CORRELACIONES**\n"
            correlation_text += f"**Período:** {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}\n\n"
            
            # Crear encabezados
            metrics = correlation_df.columns.tolist()
            correlation_text += "Métrica".ljust(12)
            for metric in metrics:
                correlation_text += f"{metric}".ljust(12)
            correlation_text += "\n" + "-" * (12 + len(metrics) * 12) + "\n"
            
            # Crear filas de datos
            for index, row in correlation_df.iterrows():
                correlation_text += f"{index}".ljust(12)
                for value in row:
                    correlation_text += f"{value:.2f}".ljust(12)
                correlation_text += "\n"
            
            correlation_text += "\n**Interpretación:**\n"
            correlation_text += "- Valores cercanos a 1.00: Correlación positiva fuerte\n"
            correlation_text += "- Valores cercanos a -1.00: Correlación negativa fuerte\n"
            correlation_text += "- Valores cercanos a 0.00: Sin correlación significativa\n"
            
            st.code(correlation_text, language='text')
            st.info("💡 **Tip:** Selecciona todo el texto del cuadro superior (Ctrl+A) y cópialo (Ctrl+C) para pegarlo donde necesites.")

        st.markdown("---")
        st.header("📋 Resumen de las Últimas Semanas")
        st.dataframe(df_weekly.style.format("{:.1f}", na_rep="-"), use_container_width=True)