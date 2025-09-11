import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Coach IA de Readiness v3.3",
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
    .score-secondary {{ font-size: 2.0em; font-weight: bold; line-height: 1.2; }}
    .tooltip-container {{ position: relative; display: inline-block; cursor: pointer; }}
    .tooltip-container .tooltip-text {{
        visibility: hidden; width: 220px; background-color: #333; color: #fff; text-align: center;
        border-radius: 6px; padding: 8px; position: absolute; z-index: 1;
        bottom: 115%; left: 50%; margin-left: -110px; opacity: 0; transition: opacity 0.3s;
    }}
    .tooltip-container:hover .tooltip-text {{ visibility: visible; opacity: 1; }}
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

# --- LÓGICA DE DATOS Y FUNCIONES HELPER ---
def get_score_interpretation(score):
    if score is None or pd.isna(score):
        return {"label": "N/A", "emoji": "❓", "color": "#a0a0a0", "description": "Datos no disponibles."}
    if score >= 85: return {"label": "Excelente", "emoji": "🟢✨", "color": "#00FF7F", "description": "Entreno clave / SST largo."}
    elif score >= 70: return {"label": "Bueno", "emoji": "🟢", "color": "#5cb85c", "description": "Entreno normal."}
    elif score >= 50: return {"label": "Medio", "emoji": "🟡", "color": "#f0ad4e", "description": "Entreno adaptado: ideal para Z2/Z3 y técnica, evitar picos."}
    elif score >= 40: return {"label": "Bajo", "emoji": "🟠", "color": "#E59434", "description": "Rodaje ligero, evitar calidad."}
    else: return {"label": "Muy bajo", "emoji": "🔴", "color": "#d9534f", "description": "Descanso / Z1 suave."}

def get_trend_arrow(today_score, yesterday_score):
    if today_score is None or yesterday_score is None or pd.isna(today_score) or pd.isna(yesterday_score): return ""
    diff = today_score - yesterday_score
    if diff > 2.5: return "↗️"
    elif diff < -2.5: return "↘️"
    else: return "↔️"

def generate_sparkline(data):
    if not data or len(data) < 2: return ""
    clean_data = [x for x in data if pd.notna(x)]
    if len(clean_data) < 2: return ""
    max_val, min_val = max(clean_data), min(clean_data)
    range_val = max_val - min_val if max_val > min_val else 1
    points = " ".join([f"{i * 100 / (len(clean_data) - 1)},{25 - ((val - min_val) / range_val * 20)}" for i, val in enumerate(clean_data)])
    return f"""<svg width="100" height="25" viewBox="0 0 100 25" xmlns="http://www.w3.org/2000/svg" style="margin-top: 5px;"><polyline points="{points}" fill="none" stroke="{st.session_state.primary_color}" stroke-width="2"/></svg>"""

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
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        return pd.DataFrame()
    except requests.exceptions.RequestException: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_activity_data(start_date, end_date):
    params = {'oldest': start_date.strftime('%Y-%m-%d'), 'newest': end_date.strftime('%Y-%m-%d')}
    activities_url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities"
    try:
        response = requests.get(activities_url, auth=('API_KEY', API_KEY), params=params)
        response.raise_for_status()
        if not response.json(): return pd.DataFrame(columns=['trimp', 'aerobic_efficiency'])
        activities = []
        for activity in response.json():
            date = pd.to_datetime(activity.get('start_date_local')).date()
            duration_min = activity.get('moving_time', 0) / 60
            avg_hr = activity.get('average_heartrate', 0)
            trimp = 0
            if duration_min > 0 and avg_hr is not None and avg_hr > 0: trimp = duration_min * avg_hr * 1.92
            aerobic_efficiency = np.nan
            if 'bike' in activity.get('type','').lower() and (activity.get('name', '').lower().find('z2') != -1 or activity.get('name', '').lower().find('endurance') != -1):
                norm_power = activity.get('icu_normalized_power')
                if norm_power and avg_hr: aerobic_efficiency = norm_power / avg_hr
            activities.append({'id': pd.to_datetime(date), 'trimp': trimp, 'aerobic_efficiency': aerobic_efficiency})
        if not activities: return pd.DataFrame(columns=['trimp', 'aerobic_efficiency'])
        df_act = pd.DataFrame(activities)
        df_act = df_act.groupby('id').sum(min_count=1)
        return df_act
    except requests.exceptions.RequestException: return pd.DataFrame(columns=['trimp', 'aerobic_efficiency'])

def calculate_baselines(daily_df):
    if daily_df.empty or len(daily_df) < 7:
        return {'recovery': pd.Series(dtype='float64'), 'chronic': pd.Series(dtype='float64'), 'historic': pd.Series(dtype='float64')}
    cols_to_avg = ['restingHR', 'hrv', 'atl']
    baselines = {}
    baselines['recovery'] = daily_df[daily_df['atl'] < daily_df['atl'].quantile(0.4)][cols_to_avg].mean()
    baselines['chronic'] = daily_df[cols_to_avg].tail(28).mean()
    baselines['historic'] = daily_df[cols_to_avg].tail(60).mean()
    return baselines

def calc_IER_v4_personal(rhr_today, tsb, df_history):
    if len(df_history) < 21: return 55.0
    hrv_ma7, hrv_ma21 = df_history['hrv'].rolling(window=7, min_periods=5).mean().iloc[-1], df_history['hrv'].rolling(window=21, min_periods=15).mean().iloc[-1]
    if pd.isna(hrv_ma7) or pd.isna(hrv_ma21): hrv_score = 60.0
    else:
        trend_ratio = (hrv_ma7 / hrv_ma21) if hrv_ma21 > 0 else 1
        if trend_ratio >= 1.0: hrv_score = 75 + (trend_ratio - 1) * 50
        else: hrv_score = 60 + (trend_ratio - 0.9) * 100
    hrv_score = max(0, min(100, hrv_score))
    rhr_ma21 = df_history['restingHR'].rolling(window=21, min_periods=15).mean().iloc[-1]
    if pd.isna(rhr_today) or pd.isna(rhr_ma21): rhr_score = 60.0
    else:
        deviation = rhr_today - rhr_ma21
        if deviation <= 1: rhr_score = 90
        elif deviation <= 2: rhr_score = 75
        elif deviation <= 3: rhr_score = 65
        else: rhr_score = 55
    rhr_score = max(0, min(100, rhr_score))
    sleep_ma7, sleep_ma21 = df_history['sleepScore'].tail(7).mean(), df_history['sleepScore'].tail(21).mean()
    if pd.isna(sleep_ma7) or pd.isna(sleep_ma21): sleep_score = 65.0
    else:
        ratio = sleep_ma7 / sleep_ma21 if sleep_ma21 > 0 else 1
        if ratio >= 1.0: sleep_score = 80 + (ratio - 1) * 40
        else: sleep_score = 65 + (ratio - 0.9) * 100
    sleep_score = max(0, min(100, sleep_score))
    if pd.isna(tsb): tsb_score = 70.0
    else:
        if tsb > -10: tsb_score = 75 + (tsb / 10) * 25
        else: tsb_score = 50
    tsb_score = max(0, min(100, tsb_score))
    IER = (0.40 * hrv_score + 0.20 * rhr_score + 0.25 * sleep_score + 0.15 * tsb_score)
    return round(IER, 1)

def _score_sleep(df_including_today, sleep_score_hoy):
    score, breakdown = 0, []
    if len(df_including_today) >= 28:
        sleep_data_7d = df_including_today['sleepScore'].tail(7)
        if sleep_data_7d.notna().sum() >= 5:
            sleep_ma7, sleep_ma28 = sleep_data_7d.mean(), df_including_today['sleepScore'].tail(28).mean()
            if pd.notna(sleep_ma7) and pd.notna(sleep_ma28):
                points = 0
                if sleep_ma7 >= sleep_ma28: points = 15
                elif sleep_ma7 > sleep_ma28 * 0.95: points = 12
                elif sleep_ma7 >= sleep_ma28 * 0.9: points = 7
                score += points; breakdown.append(f"P. Sueño (MA7 vs MA28) -> {points} ptos.")
    return score, breakdown
def _score_rhr(df_including_today, rhr_hoy, baselines):
    score, breakdown = 0, []
    rhr_baseline_rec = baselines.get('recovery', pd.Series()).get('restingHR')
    if pd.notna(rhr_hoy) and pd.notna(rhr_baseline_rec):
        rhr_deviation = rhr_hoy - rhr_baseline_rec
        points = 0
        if rhr_deviation <= 1: points = 35
        elif rhr_deviation <= 2: points = 25
        elif rhr_deviation <= 3: points = 15
        score += points; breakdown.append(f"FC Reposo (vs rec) -> {points} ptos.")
    return score, breakdown
def _score_hrv(df_including_today, hrv_hoy, historic_baseline_df):
    score, breakdown = 0, []
    hrv_data_7d = df_including_today['hrv'].tail(7)
    if hrv_data_7d.notna().sum() >= 5:
        hrv_ma7_today, hrv_baseline_hist_mean, hrv_baseline_hist_std = hrv_data_7d.mean(), historic_baseline_df['hrv'].mean(), historic_baseline_df['hrv'].std()
        if pd.notna(hrv_ma7_today) and pd.notna(hrv_baseline_hist_mean) and pd.notna(hrv_baseline_hist_std) and hrv_baseline_hist_std > 0:
            z_score = (hrv_ma7_today - hrv_baseline_hist_mean) / hrv_baseline_hist_std
            points = 0
            if z_score >= 0.5: points = 50
            elif -0.5 <= z_score < 0.5: points = 35
            elif -1.0 <= z_score < -0.5: points = 20
            score += points; breakdown.append(f"VFC (HRV Z-Score): {z_score:.2f} -> {points} ptos.")
    return score, breakdown

def get_readiness_analysis(selected_date, manual_context, df):
    if df.empty or pd.to_datetime(selected_date).strftime('%Y-%m-%d') not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}
    today_data, df_including_today = df.loc[selected_date.strftime('%Y-%m-%d')], df[df.index <= pd.to_datetime(selected_date)]
    hrv_hoy, rhr_hoy, sleep_score_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore')
    yesterday_str, ctl_ayer, atl_ayer, tsb_ayer = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d'), None, None, None
    if pd.to_datetime(yesterday_str) in df_including_today.index:
        yesterday_data = df_including_today.loc[yesterday_str]
        ctl_ayer, atl_ayer = yesterday_data.get('ctl'), yesterday_data.get('atl')
        if pd.notna(ctl_ayer) and pd.notna(atl_ayer): tsb_ayer = ctl_ayer - atl_ayer
    
    ier_recov_score = calc_IER_v4_personal(rhr_today=rhr_hoy, tsb=tsb_ayer, df_history=df_including_today)
    
    interp = get_score_interpretation(ier_recov_score)
    verdict_text = f"{interp['emoji']} {interp['label'].upper()}: {interp['description']}"
    
    past_df = df_including_today.iloc[:-1]
    R, breakdown = 50, []
    if not past_df.empty:
        baselines = calculate_baselines(past_df)
        historic_baseline_df = past_df.tail(min(60, len(past_df)))
        score_s, s_brk = _score_sleep(df_including_today, sleep_score_hoy)
        score_r, r_brk = _score_rhr(df_including_today, rhr_hoy, baselines)
        score_h, h_brk = _score_hrv(df_including_today, hrv_hoy, historic_baseline_df)
        # --- LÍNEA CORREGIDA ---
        R = max(0, min(100, int(score_s + score_r + score_h)))
        breakdown = s_brk + r_brk + h_brk

    return {
        "verdict": verdict_text, "readiness_score": R, "ier_recov_score": ier_recov_score,
        "metrics": {"VFC (HRV)": hrv_hoy, "FC Reposo": rhr_hoy, "Puntuación Sueño": sleep_score_hoy},
        "load_metrics": {"ctl": ctl_ayer, "atl": atl_ayer, "tsb": tsb_ayer},
        "breakdown": breakdown, "manual_context": manual_context
    }

def display_comparative_dashboard(readiness_score, ier_score, prev_readiness_score, prev_ier_score, df_history, selected_date):
    readiness_interp, ier_interp = get_score_interpretation(readiness_score), get_score_interpretation(ier_score)
    readiness_trend, ier_trend = get_trend_arrow(readiness_score, prev_readiness_score), get_trend_arrow(ier_score, prev_ier_score)
    ier_7d_scores = []
    for i in range(6, -1, -1):
        day = selected_date - timedelta(days=i)
        if day.strftime('%Y-%m-%d') in df_history.index:
            df_slice = df_history[df_history.index <= day.strftime('%Y-%m-%d')]
            if len(df_slice) >= 21:
                day_data = df_slice.loc[day.strftime('%Y-%m-%d')]
                rhr_val, tsb_val = day_data.get('restingHR'), day_data.get('tsb')
                if pd.isna(tsb_val):
                    ctl_val, atl_val = day_data.get('ctl', 0), day_data.get('atl', 0)
                    tsb_val = ctl_val - atl_val if pd.notna(ctl_val) and pd.notna(atl_val) else None
                ier_7d_scores.append(calc_IER_v4_personal(rhr_val, tsb_val, df_slice))
    sparkline_svg = generate_sparkline(ier_7d_scores)
    dashboard_html = f"""<div class="dashboard-container"><div class="row">
            <div class="col-md-7 dashboard-col" style="border-right: 1px solid {final_border_color}; padding-right: 20px;">
                <h3>Tu Recuperación (IER)</h3>{sparkline_svg}
                <div class="tooltip-container">
                    <span class="score" style="color: {ier_interp['color']};">{ier_score}</span>
                    <p style="font-size: 1.1em; margin-top: 5px; font-weight: bold;">{ier_interp['emoji']} {ier_interp['label']} {ier_trend}</p>
                    <span class="tooltip-text">{ier_interp['description']}</span></div></div>
            <div class="col-md-5 dashboard-col" style="padding-left: 20px;"><h3 style="font-size: 1.0em; color: #a0a0a0;">Readiness Global</h3>
                 <div class="tooltip-container" style="margin-top: 38px;">
                    <span class="score-secondary" style="color: {readiness_interp['color']};">{readiness_score}</span>
                    <p style="font-size: 1.0em; margin-top: 5px; font-weight: bold;">{readiness_interp['emoji']} {readiness_interp['label']} {readiness_trend}</p>
                    <span class="tooltip-text">{readiness_interp['description']}</span></div></div></div></div>"""
    st.markdown(dashboard_html, unsafe_allow_html=True)

def generate_coaching_summary(analysis):
    ier_score = analysis.get('ier_recov_score')
    interp = get_score_interpretation(ier_score)
    verdict = analysis.get('verdict', '')
    if pd.notna(ier_score):
        estado = f"{interp['emoji']} {verdict.split(':')[0]}"
        plan = interp['description']
        if ier_score >= 85: patron = "✅ Oportunidad Clara: Tu tendencia de recuperación es excelente. Luz verde para el máximo estímulo."
        elif ier_score >= 70: patron = "✅ Base Sólida: Vienes recuperando bien y el sistema está listo para asimilar carga."
        elif ier_score >= 50: patron = "🟡 Adaptación en Proceso: El cuerpo está asimilando la carga. No es día para forzar, sino para consolidar."
        elif ier_score >= 40: patron = "🟠 Señal de Carga: La fatiga acumulada es notable. Es crucial bajar la intensidad."
        else: patron = "🔴 Fatiga Elevada: El sistema nervioso pide una tregua."
    else: estado, patron, plan = "N/A", "N/A", "N/A"
    hrv_hoy, rhr_hoy = analysis.get('metrics', {}).get('VFC (HRV)'), analysis.get('metrics', {}).get('FC Reposo')
    hrv_text = f"{hrv_hoy:.1f} ms" if pd.notna(hrv_hoy) else "N/A"
    rhr_text = f"{rhr_hoy:.0f} bpm" if pd.notna(rhr_hoy) else "N/A"
    return f"**Estado:** {estado}\n**HRV/RHR Hoy:** {hrv_text} / {rhr_text}\n**Patrón:** {patron}\n**Plan del Día:** {plan}"

def quick_decision_visual(verdict):
    st.markdown(f"<h4>{verdict}</h4>", unsafe_allow_html=True)

def validate_buchheit(df):
    if 'trimp' not in df.columns or df['trimp'].isna().sum() > len(df) * 0.5: return "N/A (Faltan datos de TRIMP)"
    df['hrv_7d'] = df['hrv'].rolling(window=7, min_periods=5).mean()
    df['trimp_7d'] = df['trimp'].rolling(window=7, min_periods=5).mean()
    df['hrv_trend'] = df['hrv_7d'].diff()
    df['trimp_trend'] = df['trimp_7d'].diff()
    concordant_days = df[((df['hrv_trend'] >= 0) & (df['trimp_trend'] <= 0)) | ((df['hrv_trend'] <= 0) & (df['trimp_trend'] >= 0))]
    total_valid_days = df.dropna(subset=['hrv_trend', 'trimp_trend'])
    if len(total_valid_days) == 0: return "N/A"
    concordance = (len(concordant_days) / len(total_valid_days)) * 100
    return f"{concordance:.1f}%"
def validate_banister(df_val):
    if 'tsb' not in df_val.columns or 'readiness_score' not in df_val.columns: return "N/A"
    df_filtered = df_val[['tsb', 'readiness_score']].dropna()
    if len(df_filtered) < 3: return "N/A (datos insuf.)"
    correlation = df_filtered['tsb'].corr(df_filtered['readiness_score'])
    if pd.isna(correlation): return "N/A"
    return f"r = {correlation:.2f}"

# --- INTERFAZ PRINCIPAL ---
st.title("🧠 Coach IA de Readiness v3.3")
selected_date = st.date_input("Selecciona la fecha de análisis:", datetime.now().date())
context_options = st.multiselect("Contexto del Día (Opcional):", ["Calor Extremo", "Estrés Laboral/Personal", "Viaje", "Alcohol", "Mala Nutrición", "Enfermedad Leve", "Vacaciones", "Buen Descanso Extra"])
baseline_types = {'recovery': 'De Recuperación', 'chronic': 'Crónica (28d)', 'historic': 'Histórica (60d)'}

if selected_date:
    df_full = get_wellness_data(selected_date - timedelta(days=90), selected_date)
    analysis = get_readiness_analysis(selected_date, context_options, df_full)
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
            prev_readiness_score, prev_ier_score = None, None
            prev_date = selected_date - timedelta(days=1)
            if pd.to_datetime(prev_date).strftime('%Y-%m-%d') in df_full.index:
                prev_analysis_data = get_readiness_analysis(prev_date, [], df_full)
                if "error" not in prev_analysis_data:
                    prev_readiness_score, prev_ier_score = prev_analysis_data.get('readiness_score'), prev_analysis_data.get('ier_recov_score')
            display_comparative_dashboard(analysis.get('readiness_score'), analysis.get('ier_recov_score'), prev_readiness_score, prev_ier_score, df_full, selected_date)
            st.markdown(f"""<div class="card">
                <h5 style="margin-bottom: 10px; color: {st.session_state.primary_color};">📌 Leyenda de Interpretación</h5>
                <p style="font-size: 0.9em; margin-top: -5px; margin-bottom: 10px; color: #a0a0a0;">
                    <em><b>IER:</b> Tu tendencia de recuperación (Métrica Principal). | <b>Readiness:</b> Tu estado global del día (Métrica Secundaria).</em></p>
                <ul style="list-style-type: none; padding-left: 0; margin-bottom: 0;">
                <li style="margin-bottom: 5px;">🔴 <strong>0–39 → Muy bajo:</strong> Descanso / Z1 suave.</li>
                <li style="margin-bottom: 5px;">🟠 <strong>40–49 → Bajo:</strong> Rodaje ligero, evitar calidad.</li>
                <li style="margin-bottom: 5px;">🟡 <strong>50–69 → Medio:</strong> Entreno adaptado: ideal para Z2/Z3 y técnica, evitar picos.</li>
                <li style="margin-bottom: 5px;">🟢 <strong>70–84 → Bueno:</strong> Entreno normal.</li>
                <li>🟢✨ <strong>85–100 → Excelente:</strong> Entreno clave / SST largo.</li></ul></div>""", unsafe_allow_html=True)
            with st.expander("⚡️ Coaching Rápido IA (Análisis para José)"):
                coaching_summary_text = generate_coaching_summary(analysis)
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
            with st.expander("Ver desglose del Readiness (Score Secundario)"):
                st.markdown("\n".join(f"- {item}" for item in analysis.get('breakdown', [])))
            with st.expander("📋 Resumen para Copiar al Coach"):
                load, metrics = analysis.get('load_metrics', {}), analysis.get('metrics', {})
                ctl, atl, tsb = load.get('ctl'), load.get('atl'), load.get('tsb')
                hrv, rhr, sleep = metrics.get('VFC (HRV)'), metrics.get('FC Reposo'), metrics.get('Puntuación Sueño')
                hrv_text = f"{hrv:.1f}" if pd.notna(hrv) else "N/A"
                rhr_text = f"{rhr:.0f}" if pd.notna(rhr) else "N/A"
                sleep_text = f"{sleep:.0f}" if pd.notna(sleep) else "N/A"
                resumen_texto = f"**Resumen de Salud para el {selected_date.strftime('%d/%m/%Y')}**\n\n"
                resumen_texto += f"**Carga (Ayer):** CTL: {f'{ctl:.1f}' if pd.notna(ctl) else 'N/A'}, ATL: {f'{atl:.1f}' if pd.notna(atl) else 'N/A'}, TSB: {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}\n---\n"
                resumen_texto += f"**Veredicto:** {analysis.get('verdict', 'N/A')}\n"
                resumen_texto += f"**IER (Score Principal):** {analysis.get('ier_recov_score', 'N/A')} / 100\n"
                resumen_texto += f"**Readiness (Score Secundario):** {analysis.get('readiness_score', 'N/A')} / 100\n---\n"
                resumen_texto += f"**Métricas Clave:** HRV: {hrv_text} ms | RHR: {rhr_text} bpm | Sueño: {sleep_text}\n\n---\n**Líneas Basales:**\n"
                baselines = calculate_baselines(df_full[df_full.index < pd.to_datetime(selected_date)])
                for key, name in baseline_types.items():
                    rhr_base, hrv_base, atl_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv'), baselines.get(key, {}).get('atl')
                    resumen_texto += f"- **{name}:** RHR: {f'{rhr_base:.1f}' if pd.notna(rhr_base) else 'N/A'}, HRV: {f'{hrv_base:.1f}' if pd.notna(hrv_base) else 'N/A'}, ATL: {f'{atl_base:.1f}' if pd.notna(atl_base) else 'N/A'}\n"
                st.code(resumen_texto, language='markdown')
        
        with tab2:
            st.header("❤️ Tus Líneas Basales de Referencia")
            baselines = calculate_baselines(df_full[df_full.index < pd.to_datetime(selected_date)])
            b_col1, b_col2, b_col3 = st.columns(3)
            for col, (key, name) in zip([b_col1, b_col2, b_col3], baseline_types.items()):
                with col:
                    st.subheader(name)
                    rhr_base, hrv_base, atl_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv'), baselines.get(key, {}).get('atl')
                    st.metric("RHR", f"{rhr_base:.1f}" if pd.notna(rhr_base) else "N/A")
                    st.metric("HRV", f"{hrv_base:.1f}" if pd.notna(hrv_base) else "N/A")
                    st.metric("ATL", f"{atl_base:.1f}" if pd.notna(atl_base) else "N/A")

        with tab3:
            st.header("🗓️ Resumen de Métricas por Rango")
            col_fecha1, col_fecha2 = st.columns(2)
            with col_fecha1: fecha_inicio = st.date_input("Fecha de inicio:", value=(datetime.now() - timedelta(days=7)).date(), key="fecha_inicio_rango")
            with col_fecha2: fecha_fin = st.date_input("Fecha de fin:", value=datetime.now().date(), key="fecha_fin_rango")
            if fecha_inicio <= fecha_fin:
                if st.button("🔄 Generar Resumen por Rango", type="primary"):
                    st.warning("Esta función está siendo revisada para adaptarse a la nueva lógica.")
        
        with tab4:
            st.header("🔬 Validación del Modelo")
            st.info("Esta sección contrasta las predicciones de tu modelo con marcos científicos publicados.")
            if st.button("🚀 Ejecutar Validación (últimos 60 días)", type="primary"):
                with st.spinner("Ejecutando validaciones..."):
                    validation_period = 60
                    start_val_date, end_val_date = datetime.now().date() - timedelta(days=validation_period), datetime.now().date()
                    df_val_wellness = get_wellness_data(start_val_date, end_val_date)
                    df_val_activity = get_activity_data(start_val_date, end_val_date)
                    df_val = df_val_wellness.join(df_val_activity)
                    if 'ctl' in df_val.columns and 'atl' in df_val.columns: df_val['tsb'] = df_val['ctl'] - df_val['atl']
                    else: df_val['tsb'] = np.nan
                    readiness_scores = []
                    for day in df_val.index:
                        daily_analysis = get_readiness_analysis(day.date(), [], df_val)
                        readiness_scores.append(daily_analysis.get('readiness_score'))
                    df_val['readiness_score'] = readiness_scores
                    buchheit_result, banister_result = validate_buchheit(df_val.copy()), validate_banister(df_val.copy())
                    st.subheader("Resultados de la Validación")
                    res_col1, res_col2 = st.columns(2)
                    with res_col1:
                        st.metric("TRIMP vs HRV (Buchheit)", buchheit_result)
                        st.caption("Alineación Carga/Respuesta. >75%: Excelente ✅, 50-75%: Regular ⚠️, <50%: Pobre 🚫.")
                    with res_col2:
                        st.metric("Banister Performance Model (TSB vs Readiness)", banister_result)
                        st.caption("Mide la correlación entre la frescura (TSB) y tu score de Readiness. Un valor r > 0.7 es fuerte.")