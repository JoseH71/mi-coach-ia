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
    
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness?oldest={s}&newest={e}"
    wellness_response = requests.get(wellness_url, auth=('API_KEY', API_KEY))
    wellness_data = wellness_response.json() if wellness_response.status_code == 200 else []
    
    activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={s}&newest={e}"
    activities_response = requests.get(activities_url, auth=('API_KEY', API_KEY))
    activities_data = activities_response.json() if activities_response.status_code == 200 else []

    return wellness_data, activities_data

def process_weekly_data(end_date, num_weeks=12):
    """Procesa los datos para devolver un DataFrame con métricas semanales."""
    start_date = end_date - timedelta(days=num_weeks*7 - 1)
    wellness, activities = fetch_data_in_range(start_date, end_date)

    if not wellness:
        return pd.DataFrame()

    df_wellness = pd.DataFrame(wellness)
    df_wellness['date'] = pd.to_datetime(df_wellness['id'])
    
    df_activities = pd.DataFrame(activities)
    if not df_activities.empty:
        df_activities['date'] = pd.to_datetime(df_activities['start_date_local'])
    else:
        df_activities = pd.DataFrame(columns=['date', 'icu_training_load'])

    weekly_summary = []
    for i in range(num_weeks):
        week_end = end_date - timedelta(days=i*7)
        week_start = week_end - timedelta(days=6)
        
        week_wellness = df_wellness[(df_wellness['date'] >= pd.to_datetime(week_start)) & (df_wellness['date'] <= pd.to_datetime(week_end))]
        week_activities_data = df_activities[(df_activities['date'] >= pd.to_datetime(week_start)) & (df_activities['date'] <= pd.to_datetime(week_end))]
        
        if week_wellness.empty:
            continue

        total_tss = week_activities_data['icu_training_load'].sum()
        metrics = {
            'Semana': f"{week_start.strftime('%d/%m')}-{week_end.strftime('%d/%m')}",
            'TSS Semanal': total_tss,
            'ATL': week_wellness['atl'].mean(),
            'CTL': week_wellness['ctl'].mean(),
            'RHR': week_wellness['restingHR'].mean(),
            'HRV': week_wellness['hrv'].mean(),
            'P. Sueño': week_wellness['sleepScore'].mean()
        }
        weekly_summary.append(metrics)
    
    df = pd.DataFrame(weekly_summary).dropna(subset=['RHR', 'HRV', 'ATL', 'CTL']).set_index('Semana')
    return df.iloc[::-1]

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("🔬 Correlaciones y Línea Basal")
st.write("Esta sección analiza la relación entre tu carga de entrenamiento y tus métricas de bienestar durante las últimas 12 semanas.")

end_date = st.date_input("Selecciona la fecha final del análisis", datetime.now().date())

if end_date:
    df_weekly = process_weekly_data(end_date)

    if df_weekly.empty:
        st.warning("No hay suficientes datos de bienestar en el periodo seleccionado para realizar el análisis.")
    else:
        # --- CÁLCULO DE LAS 3 LÍNEAS BASALES ---
        
        # 1. Basal de Recuperación
        avg_atl = df_weekly['ATL'].mean()
        low_load_weeks = df_weekly[df_weekly['ATL'] <= avg_atl]
        baseline_recovery = low_load_weeks[['RHR', 'HRV', 'P. Sueño']].mean()

        # 2. Basal Crónica (Últimas 4 semanas)
        if len(df_weekly) >= 4:
            baseline_chronic = df_weekly[['RHR', 'HRV', 'P. Sueño']].tail(4).mean()
        else:
            baseline_chronic = pd.Series(dtype='float64')

        # 3. Basal Histórica (Últimas 8 semanas)
        if len(df_weekly) >= 8:
            baseline_historic = df_weekly[['RHR', 'HRV', 'P. Sueño']].tail(8).mean()
        else:
            baseline_historic = pd.Series(dtype='float64')

        # --- VISUALIZACIÓN DE LAS 3 LÍNEAS BASALES ---
        st.header("❤️ Tus Líneas Basales de Referencia")
        st.caption("Compara tu estado diario con estas tres referencias clave calculadas a partir de tus datos semanales.")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("🛌 De Recuperación")
            st.caption("Tu estado 'fresco' (semanas de baja carga)")
            if not baseline_recovery.empty:
                st.metric("FC Reposo (RHR)", f"{baseline_recovery.get('RHR', 0):.1f} bpm")
                st.metric("VFC (HRV)", f"{baseline_recovery.get('HRV', 0):.1f} ms")
                st.metric("P. Sueño", f"{baseline_recovery.get('P. Sueño', 0):.1f}")

        with col2:
            st.subheader("🗓️ Crónica (28 días)")
            st.caption("Tu tendencia reciente")
            if not baseline_chronic.empty:
                st.metric("FC Reposo (RHR)", f"{baseline_chronic.get('RHR', 0):.1f} bpm")
                st.metric("VFC (HRV)", f"{baseline_chronic.get('HRV', 0):.1f} ms")
                st.metric("P. Sueño", f"{baseline_chronic.get('P. Sueño', 0):.1f}")
            else:
                st.info("No hay datos suficientes (se necesitan 4 semanas).")

        with col3:
            st.subheader("📚 Histórica (60 días)")
            st.caption("Tu referencia a largo plazo")
            if not baseline_historic.empty:
                st.metric("FC Reposo (RHR)", f"{baseline_historic.get('RHR', 0):.1f} bpm")
                st.metric("VFC (HRV)", f"{baseline_historic.get('HRV', 0):.1f} ms")
                st.metric("P. Sueño", f"{baseline_historic.get('P. Sueño', 0):.1f}")
            else:
                st.info("No hay datos suficientes (se necesitan 8 semanas).")
        
        # --- NUEVO DESPLEGABLE EXPLICATIVO ---
        with st.expander("💡 ¿Cómo se calculan estas Líneas Basales?"):
            st.markdown("""
            Los cálculos en esta pestaña se realizan sobre una tabla de datos donde cada fila ya es un **promedio de una semana completa**. Esto suaviza las fluctuaciones diarias y es ideal para el análisis de tendencias.

            1.  **Línea Basal de Recuperación:**
                * **Objetivo:** Definir tu estado fisiológico en semanas de baja carga.
                * **Método:**
                    1.  Se calcula tu `ATL` (fatiga) promedio de todas las semanas analizadas.
                    2.  Se seleccionan **solo las semanas en las que tu `ATL` fue inferior a esa media**.
                    3.  La línea basal es el promedio de `RHR`, `HRV` y `P. Sueño` de esas semanas.

            2.  **Línea Basal Crónica (28 días):**
                * **Objetivo:** Reflejar tu tendencia reciente.
                * **Método:** Se toman las **últimas 4 semanas** de la tabla de promedios semanales y se calcula la media de `RHR`, `HRV` y `P. Sueño`.

            3.  **Línea Basal Histórica (60 días):**
                * **Objetivo:** Dar una referencia a largo plazo.
                * **Método:** Se toman las **últimas 8 semanas** de la tabla de promedios semanales y se calcula la media de `RHR`, `HRV` y `P. Sueño`.
            
            **Nota Importante:** Estas basales **sí incluyen la Puntuación de Sueño** en sus cálculos.
            """)

        st.markdown("---")
        
        st.header("🔥 Mapa de Calor de Correlaciones")
        st.caption("Este mapa muestra cómo se relacionan tus métricas. Valores cercanos a 1 (amarillo) indican una relación positiva fuerte. Valores cercanos a -1 (morado oscuro) indican una relación negativa fuerte.")
        
        # Filtramos columnas que no son puramente numéricas o son id de semana
        corr_df = df_weekly.drop(columns=[], errors='ignore')
        correlation_matrix = corr_df.corr(method='pearson')
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(correlation_matrix, ax=ax, annot=True, cmap='viridis', fmt=".2f")
        st.pyplot(fig)
        
        # --- SECCIÓN DE INTERPRETACIÓN DETALLADA ---
        st.subheader("💡 Interpretación del Coach IA")
        st.markdown("""
        Una correlación nos dice si dos variables se mueven juntas.
        - **Positiva Fuerte (ej. +0.8):** Cuando una sube, la otra también sube de forma clara.
        - **Negativa Fuerte (ej. -0.7):** Cuando una sube, la otra baja de forma clara.
        - **Débil (cerca de 0):** No hay una relación evidente.
        
        A continuación, analizamos las relaciones más importantes para tu entrenamiento en las últimas 12 semanas:
        """)
        
        try:
            # ATL vs HRV
            atl_hrv_corr = correlation_matrix.loc['ATL', 'HRV']
            if atl_hrv_corr < -0.5:
                st.info(f"**🔴 ATL vs HRV ({atl_hrv_corr:.2f}):** Tienes una **fuerte relación negativa**. Esto es lo esperado y confirma que tu cuerpo responde a la carga: cuando tu fatiga a corto plazo (ATL) aumenta, tu sistema nervioso se estresa y tu recuperación (HRV) disminuye de forma predecible.")
            elif atl_hrv_corr < -0.2:
                st.info(f"**🟠 ATL vs HRV ({atl_hrv_corr:.2f}):** Relación negativa moderada. Tu HRV tiende a bajar cuando el ATL sube, pero otros factores (sueño, estrés no deportivo) también pueden estar influyendo mucho.")
            else:
                st.info(f"**⚪️ ATL vs HRV ({atl_hrv_corr:.2f}):** No hay una relación negativa clara. Podría significar que toleras muy bien la fatiga o que tu HRV es más sensible a otros estímulos.")

            # CTL vs HRV
            ctl_hrv_corr = correlation_matrix.loc['CTL', 'HRV']
            if ctl_hrv_corr > 0.4:
                st.success(f"**🟢 CTL vs HRV ({ctl_hrv_corr:.2f}):** ¡Esta es la mejor noticia! Tienes una **correlación positiva**, lo que significa que a medida que tu estado de forma a largo plazo (CTL) ha mejorado, tu sistema nervioso se ha hecho más fuerte y tu HRV ha tendido a subir. Estás asimilando bien el entrenamiento a largo plazo.")
            
            # TSS vs Sueño
            if 'P. Sueño' in correlation_matrix.columns and 'TSS Semanal' in correlation_matrix.index:
                tss_sleep_corr = correlation_matrix.loc['TSS Semanal', 'P. Sueño']
                if tss_sleep_corr < -0.4:
                    st.warning(f"**🟠 TSS Semanal vs P. Sueño ({tss_sleep_corr:.2f}):** Correlación negativa. Los datos sugieren que las semanas con mucha carga de entrenamiento (TSS alto) tienden a ser semanas con peor puntuación de sueño. Es una alerta para vigilar: el entrenamiento duro podría estar afectando a la calidad de tu descanso.")
                else:
                    st.info(f"**⚪️ TSS Semanal vs P. Sueño ({tss_sleep_corr:.2f}):** No se ve una relación clara entre la carga semanal y tu sueño. Es una buena señal de que gestionas bien la recuperación nocturna.")

        except KeyError as e:
            st.warning(f"No se pudieron calcular todas las interpretaciones. Falta la métrica: {e}")
            
        st.markdown("---")
        st.header("📋 Resumen de las Últimas 12 Semanas")
        st.dataframe(df_weekly.style.format("{:.1f}"), use_container_width=True)