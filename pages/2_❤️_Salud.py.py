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

# --- LÓGICA DE ANÁLISIS ---
def calculate_trend_alerts(df, selected_date):
    trend_alerts = []
    date_48h_ago = selected_date - timedelta(days=2)
    if pd.to_datetime(date_48h_ago) in df.index and pd.to_datetime(selected_date) in df.index:
        rhr_hoy = df.loc[selected_date.strftime('%Y-%m-%d')].get('restingHR')
        rhr_48h_ago = df.loc[date_48h_ago.strftime('%Y-%m-%d')].get('restingHR')
        if pd.notna(rhr_hoy) and pd.notna(rhr_48h_ago):
            rhr_diff = rhr_hoy - rhr_48h_ago
            if rhr_diff >= 3:
                trend_alerts.append(f"🚫 **Tu RHR ha subido {rhr_diff:.0f} bpm en las últimas 48h.** (De {rhr_48h_ago:.0f} a {rhr_hoy:.0f})")

    last_4_days = df[df.index <= pd.to_datetime(selected_date)].tail(4)
    if len(last_4_days) >= 3:
        last_4_days['hrv_7d_avg'] = last_4_days['hrv'].shift(1).rolling(window=7, min_periods=3).mean()
        last_4_days['is_hrv_low'] = last_4_days['hrv'] < (last_4_days['hrv_7d_avg'] * 0.90)
        if last_4_days['is_hrv_low'].tail(3).sum() >= 3:
            trend_alerts.append("⚠️ **Has tenido 3 o más días seguidos con HRV persistentemente bajo.**")
    return trend_alerts

def get_readiness_analysis(selected_date):
    start_date = selected_date - timedelta(days=10)
    end_date = selected_date
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness"
    try:
        response = requests.get(wellness_url, auth=('API_KEY', API_KEY), params=params)
        if response.status_code != 200 or not response.json():
            return {"error": "No se encontraron suficientes datos de bienestar para calcular la tendencia."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión: {e}"}

    df = pd.DataFrame(response.json())
    df['id'] = pd.to_datetime(df['id'])
    df.set_index('id', inplace=True)
    today_str = selected_date.strftime('%Y-%m-%d')
    if pd.to_datetime(today_str) not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}

    today_data = df.loc[today_str]
    previous_days_df = df.loc[:selected_date - timedelta(days=1)].tail(7)
    hrv_avg_7d = previous_days_df['hrv'].mean()
    rhr_avg_7d = previous_days_df['restingHR'].mean()
    hrv_hoy, rhr_hoy, sleep_score_hoy, atl_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore'), today_data.get('atl')
    
    score, breakdown, checklist = 0, [], []
    
    # Lógica con desglose y checklist
    if pd.notna(hrv_hoy) and pd.notna(hrv_avg_7d):
        hrv_points = 0
        if hrv_hoy >= hrv_avg_7d * 0.95:
            hrv_points = 40; checklist.append("✅ VFC (HRV) estable o en mejora.")
        elif hrv_hoy >= hrv_avg_7d * 0.90:
            hrv_points = 20; checklist.append("⚠️ VFC (HRV) ligeramente bajo (posible fatiga).")
        else: checklist.append("🚫 VFC (HRV) bajo (señal de estrés importante).")
        score += hrv_points
        breakdown.append(f"**VFC (HRV):** Tu valor `{hrv_hoy:.1f}ms` vs media `{hrv_avg_7d:.1f}ms` → **{hrv_points} ptos**.")

    if pd.notna(rhr_hoy) and pd.notna(rhr_avg_7d):
        rhr_points = 0
        if rhr_hoy <= rhr_avg_7d * 1.05:
            rhr_points = 30; checklist.append("✅ FC Reposo estable.")
        elif rhr_hoy <= rhr_avg_7d * 1.10:
            rhr_points = 15; checklist.append("⚠️ FC Reposo ligeramente elevada (vigilar).")
        else: checklist.append("🚫 FC Reposo elevada (señal de estrés).")
        score += rhr_points
        breakdown.append(f"**FC Reposo:** Tu valor `{rhr_hoy:.0f}bpm` vs media `{rhr_avg_7d:.1f}bpm` → **{rhr_points} ptos**.")

    if pd.notna(sleep_score_hoy):
        sleep_points = 0
        if sleep_score_hoy >= 75:
            sleep_points = 20; checklist.append("✅ Descanso óptimo.")
        elif sleep_score_hoy >= 65:
            sleep_points = 10; checklist.append("⚠️ Descanso solo aceptable.")
        else: checklist.append("🚫 Descanso insuficiente.")
        score += sleep_points
        breakdown.append(f"**P. Sueño:** Tu puntuación de `{sleep_score_hoy:.0f}` → **{sleep_points} ptos**.")

    if pd.notna(atl_hoy):
        atl_points = 0
        if atl_hoy < 50:
            atl_points = 10; checklist.append("✅ Carga Aguda (ATL) controlada.")
        elif atl_hoy < 70:
            atl_points = 5; checklist.append("⚠️ Carga Aguda (ATL) elevada.")
        else: checklist.append("🚫 Carga Aguda (ATL) muy alta (riesgo de sobrecarga).")
        score += atl_points
        breakdown.append(f"**Carga (ATL):** Tu valor de `{atl_hoy:.0f}` → **{atl_points} ptos**.")

    trend_alerts = calculate_trend_alerts(df, selected_date)
    verdict = "✅ ¡Listo para Entrenar!"
    if score < 50 or any("🚫" in s for s in trend_alerts): verdict = "🚫 Descanso Recomendado"
    elif score < 75 or trend_alerts: verdict = "⚠️ Entrenar con Precaución"
    
    return {
        "verdict": verdict, "readiness_score": score, "score_breakdown": breakdown, "trend_alerts": trend_alerts, "checklist": checklist,
        "metrics": {"FC Reposo": {"value": rhr_hoy, "avg": rhr_avg_7d}, "VFC (HRV)": {"value": hrv_hoy, "avg": hrv_avg_7d},
                    "Puntuación Sueño": {"value": sleep_score_hoy}, "Carga Aguda (ATL)": {"value": atl_hoy}}
    }

def get_comparison_data(date1, date2, api_key, athlete_id):
    # (El código de esta función no cambia)
    start_date, end_date = min(date1, date2), max(date1, date2)
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"
    try:
        response = requests.get(wellness_url, auth=('API_KEY', api_key), params=params)
        if response.status_code != 200 or not response.json(): return None
    except requests.exceptions.RequestException: return None
    data = response.json()
    data1 = next((item for item in data if item['id'] == date1.strftime('%Y-%m-%d')), {})
    data2 = next((item for item in data if item['id'] == date2.strftime('%Y-%m-%d')), {})
    metrics_to_compare = ["restingHR", "hrv", "sleepScore", "BodyBatteryMax", "BodyBatteryMin", "atl"]
    comparison_list = []
    for metric in metrics_to_compare:
        val1, val2 = data1.get(metric), data2.get(metric)
        change_str = "N/A"
        if val1 is not None and val2 is not None:
            change = val2 - val1
            change_str = f"+{change:.1f}" if change > 0 else f"{change:.1f}"
        comparison_list.append({
            "Métrica": metric.replace("restingHR", "FC Reposo").replace("hrv", "VFC (HRV)").replace("sleepScore", "P. Sueño").replace("BodyBatteryMax", "BB Máx").replace("BodyBatteryMin", "BB Mín").replace("atl", "ATL"),
            f"Día 1 ({date1.strftime('%d-%m')})": f"{val1:.1f}" if val1 is not None else "N/A",
            f"Día 2 ({date2.strftime('%d-%m')})": f"{val2:.1f}" if val2 is not None else "N/A", "Cambio": change_str
        })
    return pd.DataFrame(comparison_list)

# --- INTERFAZ DE USUARIO ---
st.set_page_config(layout="wide")
st.title("🤖 Coach de Readiness Diario")
mode = st.radio("Selecciona un modo de análisis:", ("Análisis Diario", "Comparar Días"), horizontal=True)

if mode == "Análisis Diario":
    selected_date = st.date_input("Fecha de análisis", datetime.now().date())
    if selected_date:
        analysis = get_readiness_analysis(selected_date)
        if "error" in analysis:
            st.error(analysis["error"])
        else:
            st.header(analysis["verdict"])
            score = analysis['readiness_score']
            score_color = "red" if score < 50 else "orange" if score < 75 else "green"
            st.markdown(f"Puntuación de Readiness: <h2 style='color:{score_color}; display:inline;'>{score} / 100</h2>", unsafe_allow_html=True)
            
            if analysis['trend_alerts']:
                st.subheader("🔔 Alertas de Tendencia")
                for alert in analysis['trend_alerts']:
                    st.warning(alert)
            
            # --- CHECKLIST RESTAURADO ---
            if analysis['checklist']:
                st.subheader("🩺 Evaluación Rápida:")
                for item in analysis['checklist']:
                    st.markdown(f"- {item}")

            with st.expander("🔍 ¿Por qué este resultado? Analiza tu puntuación"):
                st.markdown("La puntuación se calcula sobre 100, comparando los datos de hoy con la media de los 7 días anteriores.")
                st.markdown("**El cálculo detallado para hoy ha sido:**")
                for line in analysis['score_breakdown']:
                    st.info(line)
                st.markdown(f"**PUNTUACIÓN TOTAL: {analysis['readiness_score']}**")
            
            st.markdown("---")
            st.subheader("Métricas Clave del Día")
            cols = st.columns(4)
            metrics = analysis["metrics"]
            with cols[0]:
                val, avg = metrics['FC Reposo']['value'], metrics['FC Reposo']['avg']
                st.metric("FC Reposo", f"{val:.0f} bpm" if pd.notna(val) else "N/A", f"{val-avg:.1f} bpm vs avg" if pd.notna(val) and pd.notna(avg) else None, delta_color="inverse")
                if pd.notna(val): st.caption("Un RHR elevado vs. tu media puede indicar fatiga o estrés.")
            with cols[1]:
                val, avg = metrics['VFC (HRV)']['value'], metrics['VFC (HRV)']['avg']
                st.metric("VFC (HRV)", f"{val:.0f} ms" if pd.notna(val) else "N/A", f"{val-avg:.1f} ms vs avg" if pd.notna(val) and pd.notna(avg) else None)
                if pd.notna(val): st.caption("Un HRV bajo vs. tu media sugiere que el sistema nervioso no ha recuperado bien.")
            with cols[2]:
                val = metrics['Puntuación Sueño']['value']
                st.metric("Puntuación Sueño", f"{val:.0f}" if pd.notna(val) else "N/A")
                if pd.notna(val): st.caption("Un mal descanso afecta directamente a la recuperación hormonal y muscular.")
            with cols[3]:
                val = metrics['Carga Aguda (ATL)']['value']
                st.metric("Carga Aguda (ATL)", f"{val:.0f}" if pd.notna(val) else "N/A")
                if pd.notna(val): st.caption("Refleja la fatiga acumulada en los últimos 7 días.")

elif mode == "Comparar Días":
    st.subheader("🧪 Modo de Comparación entre Días")
    c1, c2 = st.columns(2)
    with c1:
        date1 = st.date_input("Selecciona el primer día", datetime.now().date() - timedelta(days=1))
    with c2:
        date2 = st.date_input("Selecciona el segundo día", datetime.now().date())
    
    if date1 and date2:
        if date1 >= date2:
            st.error("La fecha del 'Día 1' debe ser anterior a la del 'Día 2'.")
        else:
            comparison_df = get_comparison_data(date1, date2, API_KEY, ATHLETE_ID)
            if comparison_df is not None and not comparison_df.empty:
                st.write("Resultados de la Comparación:")
                st.dataframe(comparison_df.style.set_properties(**{'text-align': 'center'}), use_container_width=True)
            else:
                st.warning("No se encontraron datos para una o ambas fechas. Intenta con otras.")