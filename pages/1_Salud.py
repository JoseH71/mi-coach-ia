import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Coach IA de Readiness v3.8 - MFI", # Versión actualizada
    page_icon="🧠",
    layout="wide"
)

# --- INICIALIZACIÓN DEL ESTADO DE LA SESIÓN ---
if 'primary_color' not in st.session_state: st.session_state.primary_color = "#00aaff"
if 'background_color' not in st.session_state: st.session_state.background_color = "#0E1117"
if 'secondary_background_color' not in st.session_state: st.session_state.secondary_background_color = "#1C1E26"
if 'text_color' not in st.session_state: st.session_state.text_color = "#83D0E8"
if 'card_border_base_color' not in st.session_state: st.session_state.card_border_base_color = "#00aaff"
if 'card_border_alpha' not in st.session_state: st.session_state.card_border_alpha = 34
# --- INICIALIZACIÓN MFI ---
if 'mfi_score' not in st.session_state: st.session_state.mfi_score = 1 # Default a Neutro

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
    /* Estilo para mensaje MFI */
    .mfi-warning {{
        background-color: #F39C12; /* Naranja */
        color: #FFFFFF; /* Texto blanco */
        padding: 10px;
        border-radius: 5px;
        text-align: center;
        font-weight: bold;
        margin-top: 10px;
        margin-bottom: 10px; /* Añadido margen inferior */
    }}

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

baseline_types = {
    'recovery': 'Recuperación (Días de baja fatiga)',
    'chronic': 'Crónico (Últimos 28 días)',
    'historic': 'Histórico (Últimos 60 días)'
}

def get_score_interpretation(score):
    if score is None or pd.isna(score):
        return {"label": "N/A", "emoji": "❓", "color": "#a0a0a0", "description": "Datos no disponibles."}
    if score >= 85: return {"label": "Excelente", "emoji": "🟢✨", "color": "#00FF7F", "description": "Entreno clave / SST largo."}
    elif score >= 70: return {"label": "Bueno", "emoji": "🟢", "color": "#5cb85c", "description": "Entreno normal."}
    elif score >= 50: return {"label": "Medio", "emoji": "🟡", "color": "#f0ad4e", "description": "Entreno adaptado: ideal para Z2/Z3 y técnica, evitar picos."}
    elif score >= 40: return {"label": "Bajo", "emoji": "🟠", "color": "#E59434", "description": "Rodaje ligero, evitar calidad."}
    else: return {"label": "Muy bajo", "emoji": "🔴", "color": "#d9534f", "description": "Descanso / Z1 suave."}

# --- NUEVA FUNCIÓN INTERPRETACIÓN MFI ---
def get_mfi_interpretation(mfi_score):
    if mfi_score == 0: return "😄 Motivado"
    elif mfi_score == 1: return "🙂 Neutro"
    elif mfi_score == 2: return "😕 Saturado"
    elif mfi_score == 3: return "😩 Bloqueado"
    else: return "❓ N/A"

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
    # ... (resto de la función sin cambios) ...
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
    # ... (sin cambios) ...
    if daily_df.empty or len(daily_df) < 7:
        return {'recovery': pd.Series(dtype='float64'), 'chronic': pd.Series(dtype='float64'), 'historic': pd.Series(dtype='float64')}
    cols_to_avg = ['restingHR', 'hrv', 'atl']
    baselines = {}
    baselines['recovery'] = daily_df[daily_df['atl'] < daily_df['atl'].quantile(0.4)][cols_to_avg].mean()
    baselines['chronic'] = daily_df[cols_to_avg].tail(28).mean()
    baselines['historic'] = daily_df[cols_to_avg].tail(60).mean()
    return baselines


def calc_IER_v4_personal(rhr_today, tsb, df_history):
    # ... (sin cambios) ...
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
    # ... (sin cambios) ...
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
    # ... (sin cambios) ...
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
    # ... (sin cambios) ...
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


@st.cache_data(ttl=3600)
def calculate_normality_bands(df_60d_history):
    # ... (sin cambios) ...
    if df_60d_history.empty or len(df_60d_history) < 21:
        return {
            'hrv_mean': None, 'hrv_std': None, 'hrv_upper': None, 'hrv_lower': None,
            'rhr_mean': None, 'rhr_std': None, 'rhr_upper': None, 'rhr_lower': None
        }
    hrv_data = df_60d_history['hrv'].dropna()
    rhr_data = df_60d_history['restingHR'].dropna()
    bands = {}
    if len(hrv_data) >= 21:
        bands['hrv_mean'] = hrv_data.mean()
        bands['hrv_std'] = hrv_data.std()
        if pd.notna(bands['hrv_std']) and bands['hrv_std'] > 0:
            bands['hrv_lower'] = bands['hrv_mean'] - (0.75 * bands['hrv_std'])
            bands['hrv_upper'] = bands['hrv_mean'] + (0.75 * bands['hrv_std'])
        else:
            bands['hrv_lower'] = bands['hrv_mean'] * 0.9
            bands['hrv_upper'] = bands['hrv_mean'] * 1.1
    else:
        bands.update({'hrv_mean': None, 'hrv_std': None, 'hrv_upper': None, 'hrv_lower': None})
    if len(rhr_data) >= 21:
        bands['rhr_mean'] = rhr_data.mean()
        bands['rhr_std'] = rhr_data.std()
        if pd.notna(bands['rhr_std']) and bands['rhr_std'] > 0:
            bands['rhr_lower'] = bands['rhr_mean'] - (0.75 * bands['rhr_std'])
            bands['rhr_upper'] = bands['rhr_mean'] + (0.75 * bands['rhr_std'])
        else:
            bands['rhr_lower'] = bands['rhr_mean'] * 0.9
            bands['rhr_upper'] = bands['rhr_mean'] * 1.1
    else:
        bands.update({'rhr_mean': None, 'rhr_std': None, 'rhr_upper': None, 'rhr_lower': None})
    return bands


def check_bands_status(hrv_ma7, rhr_ma7, bands_data):
    # ... (sin cambios) ...
    hrv_status, rhr_status = "DENTRO", "DENTRO"
    hrv_color, rhr_color = "🟢", "🟢"
    is_outside = False
    if pd.notna(hrv_ma7) and pd.notna(bands_data.get('hrv_lower')):
        if hrv_ma7 < bands_data['hrv_lower']:
            hrv_status, hrv_color, is_outside = "FUERA (Bajo)", "🔴", True
        elif pd.notna(bands_data.get('hrv_upper')) and hrv_ma7 > bands_data['hrv_upper']:
            hrv_status, hrv_color = "FUERA (Alto)", "🟡"
    elif pd.isna(hrv_ma7):
        hrv_status, hrv_color = "N/A", "⚪"
    if pd.notna(rhr_ma7) and pd.notna(bands_data.get('rhr_upper')):
        if rhr_ma7 > bands_data['rhr_upper']:
            rhr_status, rhr_color, is_outside = "FUERA (Alto)", "🔴", True
        elif pd.notna(bands_data.get('rhr_lower')) and rhr_ma7 < bands_data['rhr_lower']:
            rhr_status, rhr_color = "FUERA (Bajo)", "🟡"
    elif pd.isna(rhr_ma7):
        rhr_status, rhr_color = "N/A", "⚪"
    return {
        'is_outside': is_outside,
        'hrv_status_text': f"{hrv_color} {hrv_status}",
        'rhr_status_text': f"{rhr_color} {rhr_status}"
    }

# --- FUNCIÓN MODIFICADA PARA ACEPTAR MFI ---
def get_readiness_analysis(selected_date, df, mfi_score): # Añadido mfi_score
    if df.empty or pd.to_datetime(selected_date).strftime('%Y-%m-%d') not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}

    today_data, df_including_today = df.loc[selected_date.strftime('%Y-%m-%d')], df[df.index <= pd.to_datetime(selected_date)]
    hrv_hoy, rhr_hoy, sleep_score_hoy = today_data.get('hrv'), today_data.get('restingHR'), today_data.get('sleepScore')
    yesterday_str = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    ctl_ayer, atl_ayer, tsb_ayer = None, None, None
    if pd.to_datetime(yesterday_str) in df_including_today.index:
        yesterday_data = df_including_today.loc[yesterday_str]
        ctl_ayer, atl_ayer = yesterday_data.get('ctl'), yesterday_data.get('atl')
        if pd.notna(ctl_ayer) and pd.notna(atl_ayer):
            tsb_ayer = ctl_ayer - atl_ayer

    ier_recov_score = calc_IER_v4_personal(rhr_today=rhr_hoy, tsb=tsb_ayer, df_history=df_including_today)

    past_df = df_including_today.iloc[:-1]
    R, breakdown = 50, []
    if not past_df.empty:
        baselines = calculate_baselines(past_df)
        historic_baseline_df = past_df.tail(min(60, len(past_df)))
        score_s, s_brk = _score_sleep(df_including_today, sleep_score_hoy)
        score_r, r_brk = _score_rhr(df_including_today, rhr_hoy, baselines)
        score_h, h_brk = _score_hrv(df_including_today, hrv_hoy, historic_baseline_df)
        R = max(0, min(100, int(score_s + score_r + score_h)))
        breakdown = s_brk + r_brk + h_brk

    # --- LÓGICA VEREDICTO PRIMARIO v3.7 (CON FILTRO TSB) ---
    df_60d_history = past_df.tail(min(60, len(past_df)))
    bands_data = calculate_normality_bands(df_60d_history)
    hrv_ma7 = df_including_today['hrv'].tail(7).mean()
    rhr_ma7 = df_including_today['restingHR'].tail(7).mean()
    bands_status = check_bands_status(hrv_ma7, rhr_ma7, bands_data)
    is_bands_outside = bands_status['is_outside']

    primary_verdict_text = "" # Texto base: ALARMA, PRECAUCION, OPTIMO
    primary_verdict_emoji = ""
    primary_verdict_color = ""
    base_recommendation = "" # Recomendación fisiológica base

    condition_bands_alarm = is_bands_outside and (tsb_ayer is None or tsb_ayer < 10)

    if R < 45 or condition_bands_alarm:
        primary_verdict_text = "ALARMA"
        primary_verdict_emoji = "🔴"
        primary_verdict_color = "#d9534f"
        base_recommendation = "Descanso total o Z1 regenerativo."
    elif ier_recov_score >= 70 and R >= 70:
        primary_verdict_text = "ÓPTIMO"
        primary_verdict_emoji = "🟢"
        primary_verdict_color = "#00FF7F"
        base_recommendation = "Luz verde para entrenar (calidad o volumen)."
    else:
        primary_verdict_text = "PRECAUCIÓN"
        primary_verdict_emoji = "🟡"
        primary_verdict_color = "#f0ad4e"
        base_recommendation = "Adaptar entreno (Z2 o recortar)."

    # --- MODULACIÓN DE LA RECOMENDACIÓN POR MFI v3.8 ---
    final_recommendation = base_recommendation # Empezar con la recomendación base

    if primary_verdict_text == "ALARMA":
        # Permitir Z1 regenerativo MUY CORTO solo si MFI alto y TSB muy positivo
        if mfi_score >= 2 and (tsb_ayer is not None and tsb_ayer > 5):
             final_recommendation = "Descanso total o Z1 regenerativo MUY CORTO (<30min, <105bpm) si MFI>=2."
        else:
             final_recommendation = "Descanso total." # Más seguro si TSB no es muy alto o MFI bajo
    elif primary_verdict_text == "PRECAUCIÓN":
        # Ofrecer Z1 terapéutico si MFI alto y TSB positivo
        if mfi_score >= 2 and (tsb_ayer is None or tsb_ayer > 0):
             final_recommendation = "Z1 terapéutico 30–45min (<110 bpm) para descompresión mental O Z2 suave/recortado."
        # Si no hay fatiga mental, mantener la recomendación estándar
        # else: final_recommendation = base_recommendation # Ya es "Adaptar (Z2 o recortar)"
    elif primary_verdict_text == "ÓPTIMO":
        # Priorizar bienestar si MFI muy alto
        if mfi_score == 3:
            final_recommendation = "Sesión corta y placentera (Z1/Z2). Prioriza bienestar hoy."
        # Si no, mantener recomendación estándar
        # else: final_recommendation = base_recommendation # Ya es "Luz verde..."

    # --- FIN MODULACIÓN MFI ---

    return {
        "readiness_score": R, "ier_recov_score": ier_recov_score,
        "metrics": {"VFC (HRV)": hrv_hoy, "FC Reposo": rhr_hoy, "Puntuación Sueño": sleep_score_hoy},
        "load_metrics": {"ctl": ctl_ayer, "atl": atl_ayer, "tsb": tsb_ayer},
        "breakdown": breakdown,
        "primary_verdict": f"{primary_verdict_emoji} {primary_verdict_text}", # El veredicto no cambia
        "primary_color": primary_verdict_color,
        "primary_recommendation": final_recommendation, # Devolver la recomendación modulada
        "bands_data": bands_data,
        "bands_status": bands_status,
        "hrv_ma7": hrv_ma7,
        "rhr_ma7": rhr_ma7,
        "mfi_score": mfi_score # Devolver el MFI usado
    }

# --- Resto de funciones (generate_range_analysis, etc.) SIN CAMBIOS ---
def generate_range_analysis(fecha_inicio, fecha_fin):
    extended_start = fecha_inicio - timedelta(days=90)
    df_wellness = get_wellness_data(extended_start, fecha_fin)
    if df_wellness.empty:
        return {"error": "No se encontraron datos de bienestar para el rango especificado"}
    range_start, range_end = pd.to_datetime(fecha_inicio), pd.to_datetime(fecha_fin)
    range_wellness = df_wellness[(df_wellness.index >= range_start) & (df_wellness.index <= range_end)]
    if range_wellness.empty:
        return {"error": "No hay datos de bienestar en el rango seleccionado"}
    daily_analysis = []
    # --- Modificado para pasar un MFI por defecto (e.g., 1) para el análisis de rango ---
    default_mfi_for_range = 1
    for date in range_wellness.index:
        try:
            # Pasar MFI por defecto aquí
            analysis = get_readiness_analysis(date.date(), df_wellness, default_mfi_for_range)
            if "error" not in analysis:
                daily_analysis.append({
                    'date': date, 'ier_score': analysis.get('ier_recov_score'), 'readiness_score': analysis.get('readiness_score'),
                    'hrv': analysis.get('metrics', {}).get('VFC (HRV)'), 'rhr': analysis.get('metrics', {}).get('FC Reposo'),
                    'sleep_score': analysis.get('metrics', {}).get('Puntuación Sueño'), 'ctl': analysis.get('load_metrics', {}).get('ctl'),
                    'atl': analysis.get('load_metrics', {}).get('atl'), 'tsb': analysis.get('load_metrics', {}).get('tsb'),
                    'primary_verdict': analysis.get('primary_verdict', 'N/A')
                })
        except Exception:
            continue
    # --- Fin Modificación Rango ---
    if not daily_analysis:
        return {"error": "No se pudieron procesar los análisis diarios"}
    df_analysis = pd.DataFrame(daily_analysis)
    stats = {
        'total_days': len(df_analysis), 'avg_ier': df_analysis['ier_score'].mean(),
        'avg_readiness': df_analysis['readiness_score'].mean(),
        'avg_hrv': df_analysis['hrv'].dropna().mean() if not df_analysis['hrv'].dropna().empty else 0,
        'avg_rhr': df_analysis['rhr'].dropna().mean() if not df_analysis['rhr'].dropna().empty else 0,
        'avg_sleep': df_analysis['sleep_score'].dropna().mean() if not df_analysis['sleep_score'].dropna().empty else 0,
        'avg_tsb': df_analysis['tsb'].dropna().mean() if not df_analysis['tsb'].dropna().empty else None
    }
    distribution = {
        'excelente': len(df_analysis[df_analysis['ier_score'] >= 85]), 'bueno': len(df_analysis[(df_analysis['ier_score'] >= 70) & (df_analysis['ier_score'] < 85)]),
        'medio': len(df_analysis[(df_analysis['ier_score'] >= 50) & (df_analysis['ier_score'] < 70)]),
        'bajo': len(df_analysis[(df_analysis['ier_score'] >= 40) & (df_analysis['ier_score'] < 50)]),
        'muy_bajo': len(df_analysis[df_analysis['ier_score'] < 40])
    }
    first_week, last_week = df_analysis.head(7)['ier_score'].mean(), df_analysis.tail(7)['ier_score'].mean()
    trend = "Mejorando" if last_week > first_week + 2 else "Empeorando" if last_week < first_week - 2 else "Estable"
    problem_days = df_analysis[df_analysis['ier_score'] < 50]
    return {
        'df_analysis': df_analysis, 'stats': stats, 'distribution': distribution,
        'trend': trend, 'problem_days': problem_days
    }


def create_range_charts(analysis_result):
    # ... (sin cambios) ...
    df_analysis = analysis_result['df_analysis']
    charts = {}
    fig_timeline = go.Figure()
    fig_timeline.add_trace(go.Scatter(x=df_analysis['date'], y=df_analysis['ier_score'], mode='lines+markers', name='IER Score', line=dict(color='#00aaff', width=3), marker=dict(size=6)))
    fig_timeline.add_trace(go.Scatter(x=df_analysis['date'], y=df_analysis['readiness_score'], mode='lines+markers', name='Readiness Score', line=dict(color='#ff6b6b', width=2), marker=dict(size=4)))
    fig_timeline.add_hline(y=70, line_dash="dash", line_color="green", annotation_text="Bueno")
    fig_timeline.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text="Medio")
    fig_timeline.update_layout(title='Evolución de Scores de Recuperación', xaxis_title='Fecha', yaxis_title='Score', height=500, yaxis=dict(range=[0, 100]))
    charts['timeline'] = fig_timeline
    distribution = analysis_result['distribution']
    labels = ['Excelente (85+)', 'Bueno (70-84)', 'Medio (50-69)', 'Bajo (40-49)', 'Muy Bajo (<40)']
    values = [distribution['excelente'], distribution['bueno'], distribution['medio'], distribution['bajo'], distribution['muy_bajo']]
    colors = ['#00FF7F', '#5cb85c', '#f0ad4e', '#E59434', '#d9534f']
    fig_dist = go.Figure(data=go.Pie(labels=labels, values=values, hole=0.4, marker_colors=colors))
    fig_dist.update_layout(title='Distribución de Estados de IER', height=550)
    charts['distribution'] = fig_dist
    if not df_analysis['hrv'].dropna().empty and not df_analysis['rhr'].dropna().empty:
        fig_corr = go.Figure()
        fig_corr.add_trace(go.Scatter(x=df_analysis['hrv'], y=df_analysis['rhr'], mode='markers', marker=dict(size=8, color=df_analysis['ier_score'], colorscale='RdYlGn', showscale=True, colorbar=dict(title="IER Score")), text=df_analysis['date'].dt.strftime('%d/%m'), hovertemplate='<b>%{text}</b><br>HRV: %{x}<br>RHR: %{y}<extra></extra>'))
        fig_corr.update_layout(title='Relación HRV vs FC Reposo', xaxis_title='HRV (ms)', yaxis_title='FC Reposo (bpm)', height=550)
        charts['correlation'] = fig_corr
    return charts


def create_visual_metrics_table(df_analysis):
    # ... (sin cambios, ya usaba primary_verdict) ...
    table_data = []
    dias_es = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
    for _, row in df_analysis.iterrows():
        dia_semana = dias_es.get(row['date'].strftime('%A'), row['date'].strftime('%A'))
        table_data.append({
            'Fecha': row['date'].strftime('%d/%m/%Y'), 'Día': dia_semana,
            'Estado': row['primary_verdict'],
            'IER': f"{row['ier_score']:.1f}",
            'Readiness': f"{row['readiness_score']:.0f}",
            'HRV': f"{row['hrv']:.1f}" if pd.notna(row['hrv']) else "N/A",
            'FC Reposo': f"{row['rhr']:.0f}" if pd.notna(row['rhr']) else "N/A",
            'Sueño': f"{row['sleep_score']:.0f}" if pd.notna(row['sleep_score']) else "N/A",
            'TSB': f"{row['tsb']:.1f}" if pd.notna(row['tsb']) else "N/A"
        })
    return pd.DataFrame(table_data)


def display_comparative_dashboard(readiness_score, ier_score, prev_readiness_score, prev_ier_score, df_history, selected_date):
    # ... (sin cambios) ...
    readiness_interp, ier_interp = get_score_interpretation(readiness_score), get_score_interpretation(ier_score)
    readiness_trend, ier_trend = get_trend_arrow(readiness_score, prev_readiness_score), get_trend_arrow(ier_score, prev_ier_score)
    ier_7d_scores = []
    for i in range(6, -1, -1):
        day = selected_date - timedelta(days=i)
        if day.strftime('%Y-%m-%d') in df_history.index:
            df_slice = df_history[df_history.index <= pd.to_datetime(day)]
            if len(df_slice) >= 21:
                day_data = df_slice.loc[day.strftime('%Y-%m-%d')]
                rhr_val = day_data.get('restingHR')
                ctl_val, atl_val = day_data.get('ctl', 0), day_data.get('atl', 0)
                tsb_val = ctl_val - atl_val if pd.notna(ctl_val) and pd.notna(atl_val) else None
                ier_7d_scores.append(calc_IER_v4_personal(rhr_val, tsb_val, df_slice))
    sparkline_svg = generate_sparkline(ier_7d_scores)
    dashboard_html = f"""<div class="dashboard-container"><div class="row">
        <div class="col-md-7 dashboard-col" style="border-right: 1px solid {final_border_color}; padding-right: 20px;">
            <h3>Tu Recuperación (IER)</h3>{sparkline_svg}
            <div class="tooltip-container">
                <span class="score" style="color: {ier_interp['color']};">{ier_score:.1f}</span>
                <p style="font-size: 1.1em; margin-top: 5px; font-weight: bold;">{ier_interp['emoji']} {ier_interp['label']} {ier_trend}</p>
                <span class="tooltip-text">{ier_interp['description']}</span></div></div>
        <div class="col-md-5 dashboard-col" style="padding-left: 20px;"><h3 style="font-size: 1.0em; color: #a0a0a0;">Readiness Global</h3>
                <div class="tooltip-container" style="margin-top: 38px;">
                <span class="score-secondary" style="color: {readiness_interp['color']};">{readiness_score}</span>
                <p style="font-size: 1.0em; margin-top: 5px; font-weight: bold;">{readiness_interp['emoji']} {readiness_interp['label']} {readiness_trend}</p>
                <span class="tooltip-text">{readiness_interp['description']}</span></div></div></div></div>"""
    st.markdown(dashboard_html, unsafe_allow_html=True)


# --- FUNCIÓN MODIFICADA PARA USAR RECOMENDACIÓN FINAL ---
def generate_coaching_summary(analysis):
    # Usar el veredicto y la recomendación FINAL (modulada por MFI)
    primary_verdict = analysis.get('primary_verdict', 'N/A')
    final_recommendation = analysis.get('primary_recommendation', '...') # Esta ya incluye la modulación MFI

    hrv_hoy, rhr_hoy = analysis.get('metrics', {}).get('VFC (HRV)'), analysis.get('metrics', {}).get('FC Reposo')
    hrv_text = f"{hrv_hoy:.1f} ms" if pd.notna(hrv_hoy) else "N/A"
    rhr_text = f"{rhr_hoy:.0f} bpm" if pd.notna(rhr_hoy) else "N/A"
    readiness_interp = get_score_interpretation(analysis.get('readiness_score'))
    ier_interp = get_score_interpretation(analysis.get('ier_recov_score'))
    bands_status = analysis.get('bands_status', {})
    hrv_status_raw = bands_status.get('hrv_status_text', 'N/A')
    rhr_status_raw = bands_status.get('rhr_status_text', 'N/A')
    hrv_status_clean = hrv_status_raw.split(' ', 1)[-1] if ' ' in hrv_status_raw else hrv_status_raw
    rhr_status_clean = rhr_status_raw.split(' ', 1)[-1] if ' ' in rhr_status_raw else rhr_status_raw
    # --- Añadir MFI al patrón ---
    mfi_score_val = analysis.get('mfi_score', 'N/A')
    mfi_interp_text = get_mfi_interpretation(mfi_score_val) # Incluye emoji
    patron = f"Pilar 1 (Agudo): {readiness_interp['label']} ({analysis.get('readiness_score', 0):.0f}) | Pilar 2 (Tendencia): {ier_interp['label']} ({analysis.get('ier_recov_score', 0):.1f}) | Pilar 3 (Estabilidad): {hrv_status_clean} & {rhr_status_clean} | Mente (MFI): {mfi_interp_text}"

    # Devolver el resumen usando la recomendación FINAL
    return f"**Veredicto IA:** {primary_verdict} ({final_recommendation})\n**HRV/RHR Hoy:** {hrv_text} / {rhr_text}\n**Patrón de Pilares:** {patron}"

# --- INTERFAZ PRINCIPAL ---
st.title("🧠 Coach IA de Readiness v3.8 - MFI") # Título actualizado
selected_date = st.date_input("Selecciona la fecha de análisis:", datetime.now().date(), max_value=datetime.now().date())

# --- INICIO: WIDGET MFI (Opción 1: st.radio) ---
mfi_options = {0: "😄 Motivado", 1: "🙂 Neutro", 2: "😕 Saturado", 3: "😩 Bloqueado"}

# 1. Invertimos el diccionario para poder buscar el "score" (0, 1, 2)
#    a partir del "label" ("😄 Motivado", "🙂 Neutro", etc.)
mfi_labels_to_scores = {v: k for k, v in mfi_options.items()}

# 2. Creamos la lista de opciones (los labels) en el orden correcto
mfi_labels_list = list(mfi_options.values())

# 3. Creamos el widget st.radio
selected_label = st.radio(
    "🧠 ¿Cómo te sientes mentalmente hoy? (MFI)",
    options=mfi_labels_list,
    index=st.session_state.mfi_score, # El score (0, 1, 2, 3) sirve como índice
    horizontal=True, # La clave para que se vea bien
    key="mfi_radio"
)

# 4. Actualizamos el session_state con el score numérico correspondiente
st.session_state.mfi_score = mfi_labels_to_scores[selected_label]
# --- FIN: WIDGET MFI ---

df_full = get_wellness_data(selected_date - timedelta(days=90), selected_date)

if df_full.empty:
    st.warning("No se han podido cargar los datos de bienestar. Revisa la conexión o el rango de fechas.")
else:
    # --- PASAR MFI AL ANÁLISIS ---
    analysis = get_readiness_analysis(selected_date, df_full, st.session_state.mfi_score)

    if "error" in analysis:
        st.error(analysis["error"])
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Readiness Diario", "❤️ Líneas Basales", "🗓️ Resumen por Rango", "🔬 Validación del Modelo"])
        with tab1:
            st.subheader("Nivel 1: Veredicto del Coach IA")
            primary_html = f"""
            <div class="card" style="border: 2px solid {analysis.get('primary_color', '#a0a0a0')}; text-align: center; padding: 25px;">
                <h1 style="color: {analysis.get('primary_color', '#FAFAFA')}; font-size: 2.8em; margin-bottom: 5px; font-weight: bold;">
                    {analysis.get('primary_verdict', 'N/A')}
                </h1>
                <p style="font-size: 1.2em; margin-top: 5px;">
                    {analysis.get('primary_recommendation')}
                </p>
            </div>
            """
            st.markdown(primary_html, unsafe_allow_html=True)

            # --- INICIO: MENSAJE MFI CONDICIONAL ---
            mfi_score_today = analysis.get('mfi_score', 1)
            if mfi_score_today >= 2:
                st.markdown('<div class="mfi-warning">⚠️ Movimiento terapéutico (Z1 corto, <110 bpm, 30–45 min) sugerido si el veredicto lo permite.</div>', unsafe_allow_html=True)
            # --- FIN: MENSAJE MFI CONDICIONAL ---

            st.subheader("Nivel 2: Los 3 Pilares del Veredicto + MFI") # Título actualizado
            ier_interp = get_score_interpretation(analysis.get('ier_recov_score'))
            readiness_interp = get_score_interpretation(analysis.get('readiness_score'))
            bands_status = analysis.get('bands_status', {})
            hrv_status_text = bands_status.get('hrv_status_text', 'N/A')
            rhr_status_text = bands_status.get('rhr_status_text', 'N/A')

            # --- Añadida 4ª columna para MFI ---
            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            with p_col1:
                st.markdown(f"""<div class="card">
                    <h5 style="text-align: center; color: {st.session_state.primary_color};">Pilar 1: Agudo</h5>
                    <p style="font-size: 2.2em; text-align: center; font-weight: bold; color: {readiness_interp['color']}; margin-bottom: 0;">
                        {analysis.get('readiness_score', 0):.0f}
                    </p>
                    <p style="font-size: 1.1em; text-align: center; margin-top: 0;">{readiness_interp['emoji']} {readiness_interp['label']}</p>
                </div>""", unsafe_allow_html=True)
            with p_col2:
                st.markdown(f"""<div class="card">
                    <h5 style="text-align: center; color: {st.session_state.primary_color};">Pilar 2: Tendencia</h5>
                    <p style="font-size: 2.2em; text-align: center; font-weight: bold; color: {ier_interp['color']}; margin-bottom: 0;">
                        {analysis.get('ier_recov_score', 0):.1f}
                    </p>
                    <p style="font-size: 1.1em; text-align: center; margin-top: 0;">{ier_interp['emoji']} {ier_interp['label']}</p>
                </div>""", unsafe_allow_html=True)
            with p_col3:
                st.markdown(f"""<div class="card">
                    <h5 style="text-align: center; color: {st.session_state.primary_color};">Pilar 3: Estabilidad</h5>
                     <p style="font-size: 1.1em; text-align: center; font-weight: bold; margin-bottom: 0; margin-top: 5px;">
                        HRV: {hrv_status_text}
                    </p>
                    <p style="font-size: 1.1em; text-align: center; font-weight: bold; margin-top: 0; margin-bottom: 5px;">
                        RHR: {rhr_status_text}
                    </p>
                </div>""", unsafe_allow_html=True)
            # --- INICIO: Columna MFI ---
            with p_col4:
                mfi_text = get_mfi_interpretation(mfi_score_today)
                st.markdown(f"""<div class="card">
                    <h5 style="text-align: center; color: {st.session_state.primary_color};">Pilar 4: Mente</h5>
                    <p style="font-size: 2.2em; text-align: center; font-weight: bold; color: {st.session_state.text_color}; margin-bottom: 0;">
                         {mfi_score_today}
                    </p>
                    <p style="font-size: 1.1em; text-align: center; margin-top: 0;">{mfi_text}</p>
                </div>""", unsafe_allow_html=True)
            # --- FIN: Columna MFI ---


            st.markdown("---")
            load = analysis.get("load_metrics", {})
            ctl, atl, tsb = load.get('ctl'), load.get('atl'), load.get('tsb')
            g_col1, g_col2, g_col3 = st.columns(3)
            with g_col1: st.metric(label="Forma (CTL) Ayer", value=f"{ctl:.1f}" if pd.notna(ctl) else "N/A")
            with g_col2: st.metric(label="Fatiga (ATL) Ayer", value=f"{atl:.1f}" if pd.notna(atl) else "N/A")
            with g_col3: st.metric(label="Frescura (TSB) Ayer", value=f"{tsb:.1f}" if pd.notna(tsb) else "N/A")
            st.markdown("---")

            st.subheader("Nivel 3: Desglose de Scores (IER vs Readiness)")
            # ... (resto de la interfaz sin cambios, excepto Resumen Coach) ...
            prev_readiness_score, prev_ier_score = None, None
            prev_date = selected_date - timedelta(days=1)
            if prev_date.strftime('%Y-%m-%d') in df_full.index:
                # Need to pass a default MFI for previous day analysis comparison
                prev_analysis_data = get_readiness_analysis(prev_date, df_full, 1) # Using MFI=1 for prev day
                if "error" not in prev_analysis_data:
                    prev_readiness_score = prev_analysis_data.get('readiness_score')
                    prev_ier_score = prev_analysis_data.get('ier_recov_score')
            display_comparative_dashboard(analysis.get('readiness_score'), analysis.get('ier_recov_score'), prev_readiness_score, prev_ier_score, df_full, selected_date)

            st.markdown(f"""<div class="card">
                <h5 style="margin-bottom: 10px; color: {st.session_state.primary_color};">📌 Leyenda de Interpretación</h5>
                <p style="font-size: 0.9em; margin-top: -5px; margin-bottom: 10px; color: #a0a0a0;">
                    <em><b>IER:</b> Tu tendencia de recuperación (Métrica Principal). | <b>Readiness:</b> Tu estado del día (Métrica Secundaria).</em></p>
                <ul style="list-style-type: none; padding-left: 0; margin-bottom: 0;">
                <li style="margin-bottom: 5px;">🔴 <strong>0–39 → Muy bajo:</strong> Descanso / Z1 suave.</li>
                <li style="margin-bottom: 5px;">🟠 <strong>40–49 → Bajo:</strong> Rodaje ligero, evitar calidad.</li>
                <li style="margin-bottom: 5px;">🟡 <strong>50–69 → Medio:</strong> Entreno adaptado: ideal para Z2/Z3 y técnica, evitar picos.</li>
                <li style="margin-bottom: 5px;">🟢 <strong>70–84 → Bueno:</strong> Entreno normal.</li>
                <li>🟢✨ <strong>85–100 → Excelente:</strong> Entreno clave / SST largo.</li></ul></div>""", unsafe_allow_html=True)

            with st.expander("⚡️ Coaching Rápido IA (Análisis para José)"):
                # Esta función usa la recomendación FINAL modulada por MFI
                coaching_summary_text = generate_coaching_summary(analysis)
                st.markdown(coaching_summary_text)

            st.subheader("📈 Métricas Clave y Desglose")
            m_col1, m_col2, m_col3 = st.columns(3)
            metrics = analysis.get('metrics', {})
            with m_col1: st.metric("VFC (HRV)", f"{metrics.get('VFC (HRV)', 0):.1f} ms" if pd.notna(metrics.get('VFC (HRV)')) else "N/A")
            with m_col2: st.metric("FC Reposo", f"{metrics.get('FC Reposo', 0):.0f} bpm" if pd.notna(metrics.get('FC Reposo')) else "N/A")
            with m_col3: st.metric("Puntuación Sueño", f"{metrics.get('Puntuación Sueño', 0):.0f}" if pd.notna(metrics.get('Puntuación Sueño')) else "N/A")

            with st.expander("Ver desglose del Readiness (Score Secundario)"):
                st.markdown("\n".join(f"- {item}" for item in analysis.get('breakdown', [])))

            # --- RESUMEN COACH MODIFICADO v3.8 ---
            with st.expander("📋 Resumen para Copiar al Coach"):
                load, metrics = analysis.get('load_metrics', {}), analysis.get('metrics', {})
                ctl, atl, tsb = load.get('ctl'), load.get('atl'), load.get('tsb')
                hrv, rhr, sleep = metrics.get('VFC (HRV)'), metrics.get('FC Reposo'), metrics.get('Puntuación Sueño')
                hrv_text = f"{hrv:.1f}" if pd.notna(hrv) else "N/A"
                rhr_text = f"{rhr:.0f}" if pd.notna(rhr) else "N/A"
                sleep_text = f"{sleep:.0f}" if pd.notna(sleep) else "N/A"
                mfi_score_val = analysis.get('mfi_score', 'N/A') # Get MFI score
                mfi_interp_text = get_mfi_interpretation(mfi_score_val).split(' ', 1)[-1] # Get text part

                resumen_texto = f"**Resumen de Salud para el {selected_date.strftime('%d/%m/%Y')}**\n\n"
                resumen_texto += f"**Carga (Ayer):** CTL: {f'{ctl:.1f}' if pd.notna(ctl) else 'N/A'}, ATL: {f'{atl:.1f}' if pd.notna(atl) else 'N/A'}, TSB: {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}\n"
                # Añadir MFI al resumen
                resumen_texto += f"**MFI (Fatiga Mental):** {mfi_score_val} ({mfi_interp_text})\n---\n"

                verdict_with_emoji = analysis.get('primary_verdict', 'N/A')
                verdict_text_only = verdict_with_emoji.split(' ', 1)[-1] if ' ' in verdict_with_emoji else verdict_with_emoji
                # Usar la recomendación FINAL (modulada)
                final_recommendation = analysis.get('primary_recommendation', '...')
                resumen_texto += f"**VEREDICTO IA:** {verdict_text_only} ({final_recommendation})\n---\n"

                bands_status = analysis.get('bands_status', {})
                hrv_status_raw = bands_status.get('hrv_status_text', 'N/A')
                rhr_status_raw = bands_status.get('rhr_status_text', 'N/A')
                hrv_status_clean = hrv_status_raw.split(' ', 1)[-1] if ' ' in hrv_status_raw else hrv_status_raw
                rhr_status_clean = rhr_status_raw.split(' ', 1)[-1] if ' ' in rhr_status_raw else rhr_status_raw
                resumen_texto += f"**Pilar 1 (Estado Agudo):** Readiness: {analysis.get('readiness_score', 'N/A'):.0f}\n"
                resumen_texto += f"**Pilar 2 (Tendencia):** IER: {analysis.get('ier_recov_score', 'N/A'):.1f}\n"
                resumen_texto += f"**Pilar 3 (Estabilidad):** HRV: {hrv_status_clean} | RHR: {rhr_status_clean} (MA7 vs Banda 60d)\n---\n"
                resumen_texto += f"**Métricas Clave:** HRV: {hrv_text} ms | RHR: {rhr_text} bpm | Sueño: {sleep_text}\n\n---\n**Líneas Basales:**\n"
                baselines = calculate_baselines(df_full[df_full.index < pd.to_datetime(selected_date)])
                for key, name in baseline_types.items():
                    rhr_base, hrv_base, atl_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv'), baselines.get(key, {}).get('atl')
                    resumen_texto += f"- **{name}:** RHR: {f'{rhr_base:.1f}' if pd.notna(rhr_base) else 'N/A'}, HRV: {f'{hrv_base:.1f}' if pd.notna(hrv_base) else 'N/A'}, ATL: {f'{atl_base:.1f}' if pd.notna(atl_base) else 'N/A'}\n"
                st.code(resumen_texto, language='markdown')
            # --- FIN RESUMEN COACH MODIFICADO v3.8 ---


        # --- Resto de pestañas (tab2, tab3, tab4) SIN CAMBIOS ---
        with tab2:
            st.header("❤️ Tus Líneas Basales de Referencia")
            st.info("Estas son tus medias de referencia calculadas a partir de tu historial. Son clave para entender tus datos diarios en contexto.", icon="ℹ️")
            df_para_baselines = df_full[df_full.index < pd.to_datetime(selected_date)]
            if len(df_para_baselines) < 7:
                st.warning("Se necesitan al menos 7 días de historial para calcular las líneas basales.")
            else:
                baselines = calculate_baselines(df_para_baselines)
                b_col1, b_col2, b_col3 = st.columns(3)
                for col, (key, name) in zip([b_col1, b_col2, b_col3], baseline_types.items()):
                    with col:
                        st.subheader(name)
                        rhr_base = baselines.get(key, {}).get('restingHR')
                        hrv_base = baselines.get(key, {}).get('hrv')
                        atl_base = baselines.get(key, {}).get('atl')
                        st.metric("FC Reposo Media", f"{rhr_base:.1f}" if pd.notna(rhr_base) else "N/A")
                        st.metric("VFC (HRV) Media", f"{hrv_base:.1f}" if pd.notna(hrv_base) else "N/A")
                        st.metric("Fatiga (ATL) Media", f"{atl_base:.1f}" if pd.notna(atl_base) else "N/A")
            st.markdown("---")
            st.header("📊 Tus Bandas de Normalidad (Lógica del Vídeo)")
            st.info("Calculadas sobre tu historial de 60 días. El 'Pilar 3' comprueba si tu media de 7 días (MA7) se sale de estas bandas.", icon="ℹ️")
            bands_data = analysis.get('bands_data', {})
            hrv_ma7 = analysis.get('hrv_ma7')
            rhr_ma7 = analysis.get('rhr_ma7')
            band_col1, band_col2 = st.columns(2)
            with band_col1:
                st.subheader("VFC (HRV)")
                if pd.notna(hrv_ma7):
                    st.metric(label="Tu MA7 Actual", value=f"{hrv_ma7:.1f} ms")
                else:
                    st.metric(label="Tu MA7 Actual", value="N/A")
                hrv_lower_band = bands_data.get('hrv_lower')
                hrv_mean_band = bands_data.get('hrv_mean')
                hrv_upper_band = bands_data.get('hrv_upper')
                st.markdown(f"""
                - **Banda Inferior (Alarma):** `{hrv_lower_band:.1f} ms` if pd.notna(hrv_lower_band) else "N/A"
                - **Media (60d):** `{hrv_mean_band:.1f} ms` if pd.notna(hrv_mean_band) else "N/A"
                - **Banda Superior:** `{hrv_upper_band:.1f} ms` if pd.notna(hrv_upper_band) else "N/A"
                """)
            with band_col2:
                st.subheader("FC Reposo (RHR)")
                if pd.notna(rhr_ma7):
                    st.metric(label="Tu MA7 Actual", value=f"{rhr_ma7:.1f} bpm")
                else:
                    st.metric(label="Tu MA7 Actual", value="N/A")
                rhr_lower_band = bands_data.get('rhr_lower')
                rhr_mean_band = bands_data.get('rhr_mean')
                rhr_upper_band = bands_data.get('rhr_upper')
                st.markdown(f"""
                - **Banda Inferior:** `{rhr_lower_band:.1f} bpm` if pd.notna(rhr_lower_band) else "N/A"
                - **Media (60d):** `{rhr_mean_band:.1f} bpm` if pd.notna(rhr_mean_band) else "N/A"
                - **Banda Superior (Alarma):** `{rhr_upper_band:.1f} bpm` if pd.notna(rhr_upper_band) else "N/A"
                """)

        with tab3:
            st.header("🗓️ Análisis por Rango de Fechas")
            today = datetime.now().date()
            col1, col2 = st.columns(2)
            with col1:
                fecha_inicio = st.date_input("Fecha de Inicio", today - timedelta(days=29))
            with col2:
                fecha_fin = st.date_input("Fecha de Fin", today)
            if st.button("Analizar Rango"):
                if fecha_inicio > fecha_fin:
                    st.error("La fecha de inicio no puede ser posterior a la fecha de fin.")
                else:
                    with st.spinner("Generando análisis del rango..."):
                        analysis_result = generate_range_analysis(fecha_inicio, fecha_fin)
                        if "error" in analysis_result:
                            st.error(analysis_result["error"])
                        else:
                            st.subheader("Resumen Estadístico del Periodo")
                            stats = analysis_result['stats']
                            s_col1, s_col2, s_col3 = st.columns(3)
                            s_col1.metric("IER Score Medio", f"{stats['avg_ier']:.1f}")
                            s_col2.metric("Readiness Medio", f"{stats['avg_readiness']:.1f}")
                            s_col3.metric("Tendencia General", analysis_result['trend'])
                            charts = create_range_charts(analysis_result)
                            st.plotly_chart(charts['timeline'], use_container_width=True)
                            c_col1, c_col2 = st.columns(2)
                            with c_col1:
                                st.plotly_chart(charts['distribution'], use_container_width=True)
                            with c_col2:
                                if 'correlation' in charts:
                                    st.plotly_chart(charts['correlation'], use_container_width=True)
                            st.subheader("Datos Detallados del Periodo")
                            df_visual = create_visual_metrics_table(analysis_result['df_analysis'])
                            st.dataframe(df_visual, use_container_width=True)
                            with st.expander("📋 Copiar datos de la tabla"):
                                markdown_table = df_visual.to_markdown(index=False)
                                st.code(markdown_table, language='markdown')

        with tab4:
            st.header("🔬 Validación del Modelo (IER vs Readiness)")
            st.info("Esta pestaña compara la evolución de los dos scores para validar su comportamiento. El IER (azul) debe ser más estable y marcar tendencias, mientras que el Readiness (rojo) puede ser más volátil y reflejar el estado del día.", icon="ℹ️")
            with st.spinner("Calculando datos históricos para validación..."):
                df_hist_full = get_wellness_data(datetime.now().date() - timedelta(days=90), datetime.now().date())
                validation_data = []
                default_mfi_for_validation = 1 # Usar MFI neutro para validación histórica
                for date in df_hist_full.index:
                    try:
                        # Pasar MFI por defecto aquí también
                        analysis_day = get_readiness_analysis(date.date(), df_hist_full, default_mfi_for_validation)
                        if "error" not in analysis_day:
                            validation_data.append({
                                'Fecha': date,
                                'IER Score': analysis_day.get('ier_recov_score'),
                                'Readiness Score': analysis_day.get('readiness_score')
                            })
                    except Exception:
                        continue
                df_validation = pd.DataFrame(validation_data).set_index('Fecha')
                fig_val = go.Figure()
                fig_val.add_trace(go.Scatter(x=df_validation.index, y=df_validation['IER Score'], mode='lines', name='IER Score (Tendencia)', line=dict(color=st.session_state.primary_color, width=3)))
                fig_val.add_trace(go.Scatter(x=df_validation.index, y=df_validation['Readiness Score'], mode='lines', name='Readiness Score (Diario)', line=dict(color='#ff6b6b', width=1.5)))
                fig_val.update_layout(title='Comparativa Histórica de Scores', yaxis_title='Score', yaxis=dict(range=[0, 100]))
                st.plotly_chart(fig_val, use_container_width=True)
                with st.expander("Ver datos tabulados"):
                    st.dataframe(df_validation.style.format("{:.1f}"), use_container_width=True)