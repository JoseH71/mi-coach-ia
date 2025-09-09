import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Coach IA de Readiness v2.9.23",
    page_icon="🧠",
    layout="wide"
)

# --- INICIALIZACIÓN DEL ESTADO DE LA SESIÓN ---
if 'primary_color' not in st.session_state: st.session_state.primary_color = "#00aaff"
if 'background_color' not in st.session_state: st.session_state.background_color = "#0E1117"
if 'secondary_background_color' not in st.session_state: st.session_state.secondary_background_color = "#1C1E26"
if 'text_color' not in st.session_state: st.session_state.text_color = "#FAFAFA"
if 'card_border_base_color' not in st.session_state: st.session_state.card_border_base_color = "#00aaff"
if 'card_border_alpha' not in st.session_state: st.session_state.card_border_alpha = 34

# --- EDITOR DE TEMA EN LA BARRA LATERAL ---
with st.sidebar.expander("🎨 Editor de Tema en Vivo"):
    st.session_state.primary_color = st.color_picker("Color Primario", st.session_state.primary_color)
    st.session_state.background_color = st.color_picker("Color de Fondo Principal", st.session_state.background_color)
    st.session_state.secondary_background_color = st.color_picker("Fondo Secundario", st.session_state.secondary_background_color)
    st.session_state.text_color = st.color_picker("Color del Texto", st.session_state.text_color)
    st.subheader("Borde de Tarjetas")
    st.session_state.card_border_base_color = st.color_picker("Color del Borde", st.session_state.card_border_base_color, key="border_color_picker")
    st.session_state.card_border_alpha = st.slider("Opacidad del Borde", 0, 255, st.session_state.card_border_alpha)

# --- GENERACIÓN E INYECCIÓN DEL CSS DINÁMICO ---
alpha_hex = f'{st.session_state.card_border_alpha:02x}'
final_border_color = f"{st.session_state.card_border_base_color}{alpha_hex}"
dynamic_css = f"""
<style>
    .main .block-container {{ background-color: {st.session_state.background_color}; }}
    body, .stApp, .stMarkdown, .stWrite, .stMetricLabel, .stMetricDelta, .stHeader, .stSubheader, .css-18e3th9, .css-1d391kg {{ color: {st.session_state.text_color} !important; }}
    .card, [data-testid="stExpander"], .gauge-container, .dashboard-container {{ background-color: {st.session_state.secondary_background_color} !important; border: 1px solid {final_border_color} !important; border-radius: 10px; padding: 10px; margin-bottom: 10px;}}
    [data-testid="stExpander"] summary, .st-emotion-cache-10trblm a {{ color: {st.session_state.primary_color} !important; }}
    .st-emotion-cache-18e3th9 {{ background-color: {st.session_state.background_color} !important; }}
    .dashboard-container {{ padding: 20px; }}
    .dashboard-col {{ text-align: center; }}
    .dashboard-col h3 {{ font-size: 1.2em; margin-bottom: 5px; }}
    .dashboard-col p {{ font-size: 0.9em; color: #a0a0a0; margin-top: 0; }}
    .score {{ font-size: 2.5em; font-weight: bold; line-height: 1.2; }}
    .interpretation-box {{ background-color: {st.session_state.background_color}; border-radius: 8px; padding: 15px; margin-top: 15px; text-align: center; border: 1px solid {final_border_color} }}
</style>
"""
st.markdown(dynamic_css, unsafe_allow_html=True)

# --- SECRETOS ---
try:
    ATHLETE_ID = st.secrets["ATHLETE_ID"]
    API_KEY = st.secrets["API_KEY"]
except (FileNotFoundError, KeyError):
    ATHLETE_ID = "i10474"
    API_KEY = "27i9azt55smmhvg1ogc5gmn7x"

# --- LÓGICA DE DATOS ---
@st.cache_data(ttl=3600)
def get_wellness_data(start_date, end_date):
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    wellness_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness"
    try:
        response = requests.get(wellness_url, auth=('API_KEY', API_KEY), params=params)
        response.raise_for_status()
        if response.json():
            df = pd.DataFrame(response.json())
            df['id'] = pd.to_datetime(df['id'])
            df.set_index('id', inplace=True)
            for col in ['hrv', 'restingHR', 'sleepScore', 'atl', 'ctl']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        return pd.DataFrame()
    except requests.exceptions.RequestException:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_activity_data(start_date, end_date):
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities"
    try:
        response = requests.get(activities_url, auth=('API_KEY', API_KEY), params=params)
        response.raise_for_status()
        if not response.json():
            return pd.DataFrame(columns=['trimp', 'aerobic_efficiency'])
        activities = []
        for activity in response.json():
            date = pd.to_datetime(activity.get('start_date_local')).date()
            duration_min = activity.get('moving_time', 0) / 60
            avg_hr = activity.get('average_heartrate', 0)
            trimp = 0
            if duration_min > 0 and avg_hr > 0:
                trimp = duration_min * avg_hr * 1.92
            aerobic_efficiency = np.nan
            if activity.get('name', '').lower().find('z2') != -1 or activity.get('name', '').lower().find('endurance') != -1:
                norm_power = activity.get('icu_normalized_power')
                if norm_power and avg_hr:
                    aerobic_efficiency = norm_power / avg_hr
            activities.append({'id': pd.to_datetime(date), 'trimp': trimp, 'aerobic_efficiency': aerobic_efficiency})
        if not activities:
             return pd.DataFrame(columns=['trimp', 'aerobic_efficiency'])
        df_act = pd.DataFrame(activities)
        df_act = df_act.groupby('id').sum(min_count=1)
        return df_act
    except requests.exceptions.RequestException:
        return pd.DataFrame(columns=['trimp', 'aerobic_efficiency'])

def calculate_baselines(daily_df):
    if daily_df.empty or len(daily_df) < 7:
        return {'recovery': pd.Series(dtype='float64'), 'chronic': pd.Series(dtype='float64'), 'historic': pd.Series(dtype='float64')}
    cols_to_avg = ['restingHR', 'hrv', 'atl']
    baselines = {}
    baselines['recovery'] = daily_df[daily_df['atl'] < daily_df['atl'].quantile(0.4)][cols_to_avg].mean()
    baselines['chronic'] = daily_df[cols_to_avg].tail(28).mean()
    baselines['historic'] = daily_df[cols_to_avg].tail(60).mean()
    return baselines

def calcular_ier_recov(hrv_gap, rhr_gap, hrv_trend):
    ier_score = (hrv_gap * 2.0) + (rhr_gap * 1.0)
    if hrv_trend < -0.3:
        ier_score -= 10
    if hrv_gap > 0 and rhr_gap > 0:
        ier_score += 10
    return min(100, max(0, int(ier_score)))

def check_dual_model(tsb, hrv_today, hrv_baseline):
    alerts = []
    score_adj = 0
    if pd.notna(tsb) and pd.notna(hrv_today) and pd.notna(hrv_baseline):
        hrv_gap = ((hrv_today / hrv_baseline) - 1) * 100
        if tsb > 0 and hrv_gap < -5:
            alerts.append("⚠️ Disociación: Fresco por carga, pero HRV bajo → posible fatiga oculta.")
            score_adj -= 7
        elif tsb < 0 and hrv_gap > 0:
            alerts.append("✅ Disociación positiva: Fatigado por carga, pero HRV aguanta → buena tolerancia.")
            score_adj += 5
        else:
            alerts.append("🔄 Carga interna y externa alineadas.")
    return alerts, score_adj

def _score_sleep(df_including_today, sleep_score_hoy):
    score, points, verdict, alerts, breakdown = 0, 0, "⚠️ Sin datos suficientes", [], []
    if len(df_including_today) >= 28:
        sleep_data_7d = df_including_today['sleepScore'].tail(7)
        if sleep_data_7d.notna().sum() >= 5:
            sleep_ma7 = sleep_data_7d.mean()
            sleep_ma28 = df_including_today['sleepScore'].tail(28).mean()
            if pd.notna(sleep_ma7) and pd.notna(sleep_ma28):
                if sleep_ma7 >= sleep_ma28: points = 15
                elif sleep_ma7 > sleep_ma28 * 0.95: points = 12
                elif sleep_ma7 >= sleep_ma28 * 0.9: points = 7
                score += points
                if pd.notna(sleep_score_hoy):
                    if sleep_score_hoy >= 80: score += 2; alerts.append("Bonus: Sueño de alta calidad.")
                    if sleep_score_hoy < 60: score -= 5; alerts.append("Penalización: Sueño pobre.")
                breakdown.append(f"P. Sueño (MA7 vs MA28) -> {points} ptos.")
                verdict = "✅ Bueno" if points >= 12 else "⚠️ Regular" if points >= 7 else "🚫 Pobre"
    return score, points, verdict, alerts, breakdown

def _score_rhr(df_including_today, rhr_hoy, baselines):
    score, points, verdict, alerts, breakdown = 0, 0, "N/A", [], []
    rhr_baseline_rec = baselines.get('recovery', pd.Series()).get('restingHR')
    if pd.notna(rhr_hoy) and pd.notna(rhr_baseline_rec):
        rhr_deviation = rhr_hoy - rhr_baseline_rec
        if rhr_deviation <= 1: points = 35
        elif rhr_deviation <= 2: points = 25
        elif rhr_deviation <= 3: points = 15
        score += points
        breakdown.append(f"FC Reposo (vs rec) -> {points} ptos.")
        verdict = "✅ Óptimo" if points >= 25 else "⚠️ Ligeramente Elevado" if points >= 15 else "🚫 Elevado"
        if rhr_hoy < rhr_baseline_rec - 5:
            score -= 3
            alerts.append("Penalización: RHR anormalmente bajo.")
    return score, points, verdict, alerts, breakdown

def _score_hrv(df_including_today, hrv_hoy, historic_baseline_df):
    score, points, verdict, alerts, breakdown, z_score = 0, 0, "N/A", [], [], np.nan
    is_declining = False
    hrv_data_7d = df_including_today['hrv'].tail(7)
    if hrv_data_7d.notna().sum() >= 5:
        hrv_ma7_today = hrv_data_7d.mean()
        hrv_baseline_hist_mean = historic_baseline_df['hrv'].mean()
        hrv_baseline_hist_std = historic_baseline_df['hrv'].std()
        if len(df_including_today) >= 10:
            hrv_ma7_3days_ago = df_including_today.head(-3)['hrv'].tail(7).mean()
            if pd.notna(hrv_ma7_today) and pd.notna(hrv_ma7_3days_ago) and hrv_ma7_today < hrv_ma7_3days_ago:
                is_declining = True
        if pd.notna(hrv_ma7_today) and pd.notna(hrv_baseline_hist_mean) and pd.notna(hrv_baseline_hist_std) and hrv_baseline_hist_std > 0:
            z_score = (hrv_ma7_today - hrv_baseline_hist_mean) / hrv_baseline_hist_std
            if z_score >= 0.5: points = 50
            elif -0.5 <= z_score < 0.5: points = 35
            elif -1.0 <= z_score < -0.5: points = 20
            score += points
            breakdown.append(f"VFC (HRV Z-Score): {z_score:.2f} -> {points} ptos.")
            verdict = "✅ Óptimo" if points >= 35 else "⚠️ Estable" if points >= 20 else "🚫 Bajo"
    return score, points, verdict, alerts, breakdown, is_declining, z_score

def get_readiness_analysis_v16(selected_date, manual_context, df, prev_day_verdict=""):
    if df.empty or pd.to_datetime(selected_date).strftime('%Y-%m-%d') not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}
    today_data = df.loc[selected_date.strftime('%Y-%m-%d')]
    df_including_today = df[df.index <= pd.to_datetime(selected_date)]
    past_df = df_including_today.iloc[:-1]
    if past_df.empty: return {"error": "Faltan datos históricos para un análisis completo."}
    hrv_hoy, rhr_hoy, sleep_score_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore')
    yesterday_str = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    ctl_ayer, atl_ayer, tsb_ayer = None, None, None
    if pd.to_datetime(yesterday_str) in df_including_today.index:
        yesterday_data = df_including_today.loc[yesterday_str]
        ctl_ayer, atl_ayer = yesterday_data.get('ctl'), yesterday_data.get('atl')
        if pd.notna(ctl_ayer) and pd.notna(atl_ayer): tsb_ayer = ctl_ayer - atl_ayer
    historic_baseline_df = past_df.tail(min(60, len(past_df)))
    baselines = calculate_baselines(past_df)
    score_s, sleep_points, sleep_verdict, alerts_s, breakdown_s = _score_sleep(df_including_today, sleep_score_hoy)
    score_r, rhr_points, rhr_verdict, alerts_r, breakdown_r = _score_rhr(df_including_today, rhr_hoy, baselines)
    score_h, hrv_points, hrv_verdict, alerts_h, breakdown_h, is_hrv_declining, hrv_z_score = _score_hrv(df_including_today, hrv_hoy, historic_baseline_df)
    
    ier_recov_score = None
    hrv_baseline_rec = baselines.get('recovery', {}).get('hrv')
    rhr_baseline_rec = baselines.get('recovery', {}).get('restingHR')
    hrv_gap, rhr_gap, hrv_trend_raw = 0, 0, 0
    if pd.notna(hrv_hoy) and pd.notna(hrv_baseline_rec) and hrv_baseline_rec > 0:
        hrv_gap = ((hrv_hoy / hrv_baseline_rec) - 1) * 100
    if pd.notna(rhr_hoy) and pd.notna(rhr_baseline_rec) and rhr_hoy > 0:
        rhr_gap = ((rhr_baseline_rec / rhr_hoy) - 1) * 100
    hrv_ma7_today = df_including_today['hrv'].tail(7).mean()
    hrv_ma7_3days_ago = df_including_today.head(-3)['hrv'].tail(7).mean()
    if pd.notna(hrv_ma7_today) and pd.notna(hrv_ma7_3days_ago) and hrv_ma7_3days_ago > 0:
        hrv_trend_raw = (hrv_ma7_today / hrv_ma7_3days_ago) - 1
    
    ier_recov_score = calcular_ier_recov(hrv_gap, rhr_gap, hrv_trend_raw)
    
    score = score_s + score_r + score_h
    alerts = alerts_s + alerts_r + alerts_h
    breakdown = breakdown_s + breakdown_r + breakdown_h
    
    if len(df_including_today) >= 28:
        hrv_data_28d = df_including_today['hrv'].tail(28)
        hrv_28d_mean = hrv_data_28d.mean()
        hrv_28d_std = hrv_data_28d.std()
        hrv_7d_mean = df_including_today['hrv'].tail(7).mean()
        if pd.notna(hrv_7d_mean) and pd.notna(hrv_28d_mean) and pd.notna(hrv_28d_std):
            if hrv_7d_mean < (hrv_28d_mean - hrv_28d_std):
                alerts.append("🚨 ALERTA LUISMA: HRV 7D roza tu línea roja (-1 SD). Riesgo de sobreentrenamiento en 3-5 días")
            elif hrv_7d_mean > (hrv_28d_mean + hrv_28d_std):
                alerts.append("✅ Supercompensación detectada. Hoy tolera carga +15%")
                
    is_hrv_low = hrv_points <= 20
    is_rhr_high = rhr_points <= 15
    is_hrv_good = hrv_points >= 35
    is_sleep_good = sleep_points >= 12
    if is_hrv_good and is_sleep_good:
        score += 3
        alerts.append("Bonus: Recuperación integral (Sueño y HRV óptimos).")
    
    dual_alerts, dual_score_adj = check_dual_model(tsb_ayer, hrv_hoy, baselines.get('recovery', {}).get('hrv'))
    alerts.extend(dual_alerts)
    score += dual_score_adj
    
    if "Vacaciones" in manual_context: score += 5; alerts.append("Bonus: Modo vacaciones.")
    if "Buen Descanso Extra" in manual_context: score += 5; alerts.append("Bonus: Descanso extra.")
    if "Estrés Laboral/Personal" in manual_context: score -= 5
    if "Calor Extremo" in manual_context: score -= 5
    if "Alcohol" in manual_context: score -= 7
    if "Enfermedad Leve" in manual_context: score -= 10
    
    R = max(0, min(100, int(score)))
    
    override_context = "Enfermedad Leve" in manual_context or "Alcohol" in manual_context
    override_fatigue = pd.notna(tsb_ayer) and tsb_ayer < -10 and hrv_trend_raw < -0.25
    
    verdict_text = ""
    if R >= 82 and ier_recov_score >= 60 and not override_context and not override_fatigue:
        if "VERDE" in prev_day_verdict or ier_recov_score >= 75:
             verdict_text = "✅ LUZ VERDE: Sistema preparado para carga."
        else:
             verdict_text = "⚠️ LUZ AMARILLA: Señales positivas, pero requiere confirmación (Histeresis)."
    elif R < 60 or (ier_recov_score < 35 and hrv_trend_raw < -0.25) or (pd.notna(tsb_ayer) and tsb_ayer < -12 and (is_hrv_low or is_rhr_high)):
        verdict_text = "🚫 LUZ ROJA: Priorizar recuperación."
    else: 
        verdict_text = "⚠️ LUZ AMARILLA: Modificar. Mantener volumen, bajar intensidad."

    return {
        "verdict": verdict_text, "readiness_score": R, "alerts": alerts, "score_breakdown": breakdown,
        "metrics": { "VFC (HRV)": hrv_hoy, "FC Reposo": rhr_hoy, "Puntuación Sueño": sleep_score_hoy },
        "verdicts": {"hrv": hrv_verdict, "rhr": rhr_verdict, "sleep": sleep_verdict},
        "points": {"hrv": hrv_points, "rhr": rhr_points, "sleep": sleep_points},
        "baselines": baselines, "load_metrics": {"ctl": ctl_ayer, "atl": atl_ayer, "tsb": tsb_ayer},
        "manual_context": manual_context, "ier_recov_score": ier_recov_score, "hrv_z_score": hrv_z_score
    }

def generate_health_summary_range(start_date, end_date, df_full):
    summary_text = f"**📊 RESUMEN DE MÉTRICAS DE SALUD**\n**Período:** {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}\n\n"
    current_date = start_date
    prev_verdict = ""
    while current_date <= end_date:
        analysis = get_readiness_analysis_v16(current_date, [], df_full, prev_verdict)
        date_str = current_date.strftime('%d/%m/%Y')
        if "error" in analysis:
            summary_text += f"**{date_str}:** No hay datos disponibles.\n"
        else:
            verdict = analysis.get('verdict', ''); score = analysis.get('readiness_score', 'N/A')
            prev_verdict = verdict
            emoji = "✅" if "VERDE" in verdict else "⚠️" if "AMARILLA" in verdict else "🚫"
            metrics = analysis.get('metrics', {}); hrv, rhr, sleep = metrics.get('VFC (HRV)'), metrics.get('FC Reposo'), metrics.get('Puntuación Sueño')
            load = analysis.get('load_metrics', {}); tsb = load.get('tsb')
            summary_text += f"**{date_str}:** {emoji} {score}/100 | HRV: {f'{hrv:.1f}' if pd.notna(hrv) else 'N/A'} | RHR: {f'{rhr:.0f}' if pd.notna(rhr) else 'N/A'} | Sueño: {f'{sleep:.0f}' if pd.notna(sleep) else 'N/A'} | TSB: {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}\n"
        current_date += timedelta(days=1)
    return summary_text

def display_comparative_dashboard(readiness_score, ier_recov_score):
    readiness_color = "#d9534f" if readiness_score < 60 else "#f0ad4e" if readiness_score < 80 else "#5cb85c"
    readiness_emoji = "🚫" if readiness_score < 60 else "⚠️" if readiness_score < 80 else "✅"
    
    ier_color = "#5cb85c" if ier_recov_score > 70 else "#f0ad4e" if ier_recov_score > 40 else "#d9534f"
    ier_emoji = "🟢" if ier_recov_score > 70 else "🟡" if ier_recov_score > 40 else "🔴"
    
    if readiness_score >= 80:
        readiness_text = "Entrenar según plan."
    elif readiness_score >= 60:
        readiness_text = "Considerar modificar."
    else:
        readiness_text = "Descanso o recuperación activa."

    if ier_recov_score > 70:
        ier_text = "Día excepcional. Ideal para cargas fuertes."
    elif ier_recov_score > 40:
        ier_text = "Estado normal. Estrés controlado."
    else:
        ier_text = "Estrés alto. No es día para forzar."

    interpretation = f"**Brújula Diaria:** {readiness_text} **Alerta Temprana:** {ier_text}"
    dashboard_html = f"""
    <div class="dashboard-container">
        <div class="row">
            <div class="col-md-6 dashboard-col" style="border-right: 1px solid {final_border_color}; padding-right: 20px;">
                <h3>{readiness_emoji} Readiness Global</h3>
                <p>Tu estado operativo del día</p>
                <div class="score" style="color: {readiness_color};">{readiness_score} <span style="font-size: 0.5em;">/ 100</span></div>
            </div>
            <div class="col-md-6 dashboard-col" style="padding-left: 20px;">
                <h3>{ier_emoji} Índice Recup. Aguda</h3>
                <p>Detector de supercompensación</p>
                <div class="score" style="color: {ier_color};">{ier_recov_score} <span style="font-size: 0.5em;">/ 100</span></div>
            </div>
        </div>
        <div class="interpretation-box">
            <p style="margin: 0;">{interpretation}</p>
        </div>
    </div>
    """
    st.markdown(dashboard_html, unsafe_allow_html=True)

def generate_coaching_summary(analysis, df, selected_date):
    R = analysis.get('readiness_score', 0)
    I_recov = analysis.get('ier_recov_score', 0)
    hrv_z_score = analysis.get('hrv_z_score')
    
    hrv_hoy = analysis.get('metrics', {}).get('VFC (HRV)')
    rhr_hoy = analysis.get('metrics', {}).get('FC Reposo')
    hrv_baseline = analysis.get('baselines', {}).get('recovery', {}).get('hrv')
    rhr_baseline = analysis.get('baselines', {}).get('recovery', {}).get('restingHR')
    
    verdict = analysis.get('verdict', '')
    if "VERDE" in verdict:
        estado = f"✅ VERDE - {verdict.split(':')[-1].strip()}"
    elif "AMARILLA" in verdict:
        estado = f"⚠️ AMARILLA - {verdict.split(':')[-1].strip()}"
    else:
        estado = f"🚫 ROJO - {verdict.split(':')[-1].strip()}"
        
    hrv_text = "N/A"
    if pd.notna(hrv_hoy) and pd.notna(hrv_baseline) and hrv_baseline > 0:
        hrv_diff = ((hrv_hoy / hrv_baseline) - 1) * 100
        hrv_text = f"{hrv_hoy:.1f}ms ({hrv_diff:+.1f}% vs rec)"
    
    rhr_text = "N/A"
    if pd.notna(rhr_hoy) and pd.notna(rhr_baseline):
        rhr_diff = rhr_hoy - rhr_baseline
        rhr_text = f"{rhr_hoy:.0f}bpm ({rhr_diff:+.1f} vs rec)"
    
    hrv_trend_text = "↔️ estable"
    if pd.notna(hrv_z_score):
        hrv_trend_text = f"↔️ estable (Z:{hrv_z_score:.2f})"

    if "VERDE" in verdict:
        if R >= 88 and I_recov >= 80:
             patron = "✅ Súper-compensación: Sistema preparado para máxima carga."
             plan = "Calidad máxima. Día ideal para tests, VO2max o el entreno más duro."
        else:
             patron = "✅ Base sólida: Sistema recuperado y listo para carga planificada."
             plan = "Entrenar según lo planificado. Luz verde para intensidad."
    elif "AMARILLA" in verdict:
        if "Histeresis" in verdict:
             patron = "🟡 Señal positiva (Histeresis): El cuerpo mejora, pero necesita confirmar la tendencia."
             plan = "Entrenar según plan, pero con un RPE un punto por debajo. Evitar esfuerzos máximos."
        elif R >= 80 and I_recov < 60:
             patron = "🟡 Contradicción: Buena base pero con estrés agudo (ej. mal sueño). Motor listo, pero sistema nervioso fatigado."
             plan = "Mantener volumen (Z2), pero guiar por Sensaciones (RPE) o FC. Evitar intensidad alta."
        else:
             patron = "🟡 Recuperación en proceso: Energía limitada."
             plan = "Entrenamiento de base (Z2) o técnica. Evitar alta intensidad."
    else: # ROJO
        patron = "🔴 Fatiga acumulada: El cuerpo pide descanso."
        plan = "Descanso activo (Z1 muy suave) o total. Prioridad a la recuperación."

    summary = f"""
**Estado:** {estado}
**HRV:** {hrv_text} - Tendencia: {hrv_trend_text}
**RHR:** {rhr_text}
**Patrón:** {patron}
**Plan:** {plan}
"""
    return summary

def validate_buchheit(df):
    if 'trimp' not in df.columns or df['trimp'].isna().sum() > len(df) * 0.5:
        return "N/A (Faltan datos de TRIMP)"
    df['hrv_7d'] = df['hrv'].rolling(window=7, min_periods=5).mean()
    df['trimp_7d'] = df['trimp'].rolling(window=7, min_periods=5).mean()
    df['hrv_trend'] = df['hrv_7d'].diff()
    df['trimp_trend'] = df['trimp_7d'].diff()
    concordant_days = df[((df['hrv_trend'] >= 0) & (df['trimp_trend'] <= 0)) | ((df['hrv_trend'] <= 0) & (df['trimp_trend'] >= 0))]
    total_valid_days = df.dropna(subset=['hrv_trend', 'trimp_trend'])
    if len(total_valid_days) == 0:
        return "N/A"
    concordance = (len(concordant_days) / len(total_valid_days)) * 100
    return f"{concordance:.1f}%"

def validate_banister(df_val):
    if 'tsb' not in df_val.columns or 'readiness_score' not in df_val.columns:
        return "N/A"
    correlation = df_val['tsb'].corr(df_val['readiness_score'])
    return f"r = {correlation:.2f}"

def quick_decision_visual(verdict):
    if "VERDE" in verdict:
        st.success("🟢 HOY SÍ - Entrena según plan")
    elif "AMARILLA" in verdict:
        st.warning("🟡 MODIFICAR - Mantén volumen, baja intensidad")
    else:
        st.error("🔴 DESCANSO - Recuperación activa o total")

# --- INTERFAZ PRINCIPAL ---
st.title("🧠 Coach IA de Readiness v2.9.23")
selected_date = st.date_input("Selecciona la fecha de análisis:", datetime.now().date())
context_options = st.multiselect("Contexto del Día (Opcional):", ["Calor Extremo", "Estrés Laboral/Personal", "Viaje", "Alcohol", "Mala Nutrición", "Enfermedad Leve", "Vacaciones", "Buen Descanso Extra"])
baseline_types = {'recovery': 'De Recuperación', 'chronic': 'Crónica (28d)', 'historic': 'Histórica (60d)'}

if selected_date:
    df_full = get_wellness_data(selected_date - timedelta(days=90), selected_date)
    
    prev_day_verdict = ""
    prev_date = selected_date - timedelta(days=1)
    if pd.to_datetime(prev_date).strftime('%Y-%m-%d') in df_full.index:
        prev_analysis = get_readiness_analysis_v16(prev_date, [], df_full)
        if "error" not in prev_analysis:
            prev_day_verdict = prev_analysis.get('verdict', "")
            
    analysis = get_readiness_analysis_v16(selected_date, context_options, df_full, prev_day_verdict)
    
    tabs = ["📊 Readiness Diario", "❤️ Líneas Basales", "🗓️ Resumen por Rango", "🔬 Validación del Modelo"]
    tab1, tab2, tab3, tab4 = st.tabs(tabs)

    if "error" in analysis:
        st.error(analysis["error"])
    else:
        with tab1:
            st.subheader("🚦 Veredicto Rápido del Día")
            quick_decision_visual(analysis.get('verdict', ''))

            load = analysis.get("load_metrics", {})
            ctl, atl, tsb = load.get('ctl'), load.get('atl'), load.get('tsb')
            st.markdown('<div class="card-grid">', unsafe_allow_html=True)
            g_col1, g_col2, g_col3 = st.columns(3)
            with g_col1: st.metric(label="Forma (CTL) Ayer", value=f"{ctl:.1f}" if pd.notna(ctl) else "N/A")
            with g_col2: st.metric(label="Fatiga (ATL) Ayer", value=f"{atl:.1f}" if pd.notna(atl) else "N/A")
            with g_col3: st.metric(label="Frescura (TSB) Ayer", value=f"{tsb:.1f}" if pd.notna(tsb) else "N/A")
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("---")
            st.subheader("📊 Dashboard Comparativo del Día")
            if analysis.get("manual_context"):
                st.warning(f"**Contexto Manual Aplicado:** {', '.join(analysis['manual_context'])}.")
            display_comparative_dashboard(analysis.get('readiness_score', 0), analysis.get('ier_recov_score', 0))
            
            with st.expander("⚡️ Coaching Rápido IA (Análisis para José)"):
                coaching_summary_text = generate_coaching_summary(analysis, df_full[df_full.index <= pd.to_datetime(selected_date)], selected_date)
                st.markdown(coaching_summary_text)
                st.info("Copia y pega este resumen para tu entrenador.")

            st.markdown("---")
            st.subheader("📈 Métricas Clave y Vistazo Rápido")
            m_col1, m_col2, m_col3 = st.columns(3)
            metrics = analysis.get('metrics', {})
            hrv, rhr, sleep = metrics.get('VFC (HRV)'), metrics.get('FC Reposo'), metrics.get('Puntuación Sueño')
            with m_col1: st.metric("VFC (HRV)", f"{hrv:.1f} ms" if pd.notna(hrv) else "N/A")
            with m_col2: st.metric("FC Reposo", f"{rhr:.0f} bpm" if pd.notna(rhr) else "N/A")
            with m_col3: st.metric("Puntuación Sueño", f"{sleep:.0f}" if pd.notna(sleep) else "N/A")
            col1, col2, col3 = st.columns(3)
            verdicts, points = analysis.get('verdicts', {}), analysis.get('points', {})
            with col1: st.markdown(f'<div class="card">🧬 **Análisis HRV:** {verdicts.get("hrv", "N/A")} ({points.get("hrv", 0)} ptos.)</div>', unsafe_allow_html=True)
            with col2: st.markdown(f'<div class="card">❤️ **Análisis RHR:** {verdicts.get("rhr", "N/A")} ({points.get("rhr", 0)} ptos.)</div>', unsafe_allow_html=True)
            with col3: st.markdown(f'<div class="card">🛌 **Análisis Sueño:** {verdicts.get("sleep", "N/A")} ({points.get("sleep", 0)} ptos.)</div>', unsafe_allow_html=True)

            with st.expander("Ver desglose y alertas del cálculo de Readiness"):
                st.markdown("##### Desglose de Puntos:")
                st.markdown("\n".join(f"- {item}" for item in analysis.get('score_breakdown', [])))
                if analysis.get('alerts'):
                    st.markdown("##### Alertas y Bonificaciones:")
                    st.markdown("\n".join(f"- {alert}" for alert in analysis.get('alerts')))

            with st.expander("📋 Resumen para Copiar al Coach"):
                metrics, baselines = analysis.get('metrics', {}), analysis.get('baselines', {})
                hrv_hoy, rhr_hoy, sleep_hoy = metrics.get('VFC (HRV)'), metrics.get('FC Reposo'), metrics.get('Puntuación Sueño')
                resumen_texto = f"**Resumen de Salud para el {selected_date.strftime('%d/%m/%Y')}**\n\n"
                resumen_texto += f"**Carga (Ayer):** CTL: {f'{ctl:.1f}' if pd.notna(ctl) else 'N/A'}, ATL: {f'{atl:.1f}' if pd.notna(atl) else 'N/A'}, TSB: {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}\n---\n"
                resumen_texto += f"**Veredicto y Puntuación:** {analysis.get('verdict', 'N/A')} ({analysis.get('readiness_score', 'N/A')} / 100)\n"
                resumen_texto += f"**Índice Estrés Recuperativo (IER):** {analysis.get('ier_recov_score', 'N/A')} / 100\n---\n"
                resumen_texto += f"**Métricas Clave:** HRV: {f'{hrv_hoy:.1f} ms' if pd.notna(hrv_hoy) else 'N/A'} | RHR: {f'{rhr_hoy:.0f} bpm' if pd.notna(rhr_hoy) else 'N/A'} | Sueño: {f'{sleep_hoy:.0f}' if pd.notna(sleep_hoy) else 'N/A'}\n---\n"
                resumen_texto += "**Desglose:**\n" + "\n".join(f"- {item}" for item in analysis.get('score_breakdown', []))
                if analysis.get('alerts'):
                    resumen_texto += "\n\n**Alertas y Bonificaciones:**\n" + "\n".join(f"- {alert}" for alert in analysis.get('alerts'))
                resumen_texto += "\n\n---\n**Líneas Basales:**\n"
                for key, name in baseline_types.items():
                    rhr_base, hrv_base, atl_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv'), baselines.get(key, {}).get('atl')
                    resumen_texto += f"- **{name}:** RHR: {f'{rhr_base:.1f}' if pd.notna(rhr_base) else 'N/A'}, HRV: {f'{hrv_base:.1f}' if pd.notna(hrv_base) else 'N/A'}, ATL: {f'{atl_base:.1f}' if pd.notna(atl_base) else 'N/A'}\n"
                st.code(resumen_texto, language='markdown')

        with tab2:
            st.header("❤️ Tus Líneas Basales de Referencia")
            baselines = analysis.get('baselines', {})
            b_col1, b_col2, b_col3 = st.columns(3)
            for col, (key, name) in zip([b_col1, b_col2, b_col3], baseline_types.items()):
                with col:
                    st.subheader(name)
                    rhr_base, hrv_base, atl_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv'), baselines.get(key, {}).get('atl')
                    st.metric("RHR", f"{rhr_base:.1f} bpm" if pd.notna(rhr_base) else "N/A")
                    st.metric("HRV", f"{hrv_base:.1f} ms" if pd.notna(hrv_base) else "N/A")
                    st.metric("ATL", f"{atl_base:.1f}" if pd.notna(atl_base) else "N/A")

        with tab3:
            st.header("🗓️ Resumen de Métricas por Rango")
            col_fecha1, col_fecha2 = st.columns(2)
            with col_fecha1: fecha_inicio = st.date_input("Fecha de inicio:", value=(datetime.now() - timedelta(days=7)).date(), key="fecha_inicio_rango")
            with col_fecha2: fecha_fin = st.date_input("Fecha de fin:", value=datetime.now().date(), key="fecha_fin_rango")
            if fecha_inicio <= fecha_fin:
                if st.button("🔄 Generar Resumen por Rango", type="primary"):
                    with st.spinner("Generando resumen..."):
                        resumen_rango = generate_health_summary_range(fecha_inicio, fecha_fin, df_full)
                        with st.expander("📋 Resumen por Rango - Copiar y Pegar", expanded=True):
                            st.code(resumen_rango, language='markdown')
            else:
                st.error("⚠️ La fecha de inicio debe ser anterior o igual a la fecha de fin.")

        with tab4:
            st.header("🔬 Validación del Modelo vs. Estándares Científicos")
            st.info("Esta sección contrasta las predicciones de tu modelo con marcos científicos publicados para asegurar su fiabilidad.")

            if st.button("🚀 Ejecutar Validación (últimos 60 días)", type="primary"):
                with st.spinner("Recalculando scores y ejecutando validaciones... (puede tardar un minuto)"):
                    validation_period = 60
                    start_val_date = datetime.now().date() - timedelta(days=validation_period)
                    end_val_date = datetime.now().date()
                    
                    df_val_wellness = get_wellness_data(start_val_date, end_val_date)
                    df_val_activity = get_activity_data(start_val_date, end_val_date)
                    df_val = df_val_wellness.join(df_val_activity)

                    readiness_scores = []
                    for day in df_val.index:
                        # Para la validación, no necesitamos la histeresis
                        daily_analysis = get_readiness_analysis_v16(day.date(), [], df_val)
                        readiness_scores.append(daily_analysis.get('readiness_score'))
                    df_val['readiness_score'] = readiness_scores
                    
                    buchheit_result = validate_buchheit(df_val.copy())
                    banister_result = validate_banister(df_val.copy())

                    st.subheader("Resultados de la Validación")
                    res_col1, res_col2 = st.columns(2)
                    with res_col1:
                        st.metric("TRIMP vs HRV (Buchheit)", buchheit_result)
                        st.caption("Mide si la carga interna (TRIMP) y la respuesta (HRV) están alineadas. Un valor >75% es excelente.")
                    with res_col2:
                        st.metric("Banister Performance Model (TSB vs Readiness)", banister_result)
                        st.caption("Mide la correlación entre la frescura (TSB) y tu score de Readiness. Un valor r > 0.7 es fuerte.")
                    
                    st.warning("El modelo de 'Compensated Fatigue' (HRV4Training) requiere una lógica más compleja y no se ha incluido en esta versión para simplificar.")