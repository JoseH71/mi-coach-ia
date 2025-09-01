import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Coach IA de Readiness v2.7.1",
    page_icon="🧠",
    layout="wide"
)

# --- INICIALIZACIÓN DEL ESTADO DE LA SESIÓN (Para el editor de tema) ---
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
    .card, [data-testid="stExpander"], .gauge-container {{ background-color: {st.session_state.secondary_background_color} !important; border: 1px solid {final_border_color} !important; border-radius: 10px; padding: 10px; margin-bottom: 10px;}}
    [data-testid="stExpander"] summary, .st-emotion-cache-10trblm a {{ color: {st.session_state.primary_color} !important; }}
    .st-emotion-cache-18e3th9 {{ background-color: {st.session_state.background_color} !important; }}
    .gauge-container {{ background-color: #f1f1f1; border-radius: 5px; padding: 2px; }}
    .gauge-fill {{ height: 24px; border-radius: 5px; text-align: center; color: white; font-weight: bold; line-height: 24px; }}
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
            return df
        return pd.DataFrame()
    except requests.exceptions.RequestException:
        return pd.DataFrame()

def calculate_baselines(daily_df):
    if daily_df.empty or len(daily_df) < 7:
        return {'recovery': pd.Series(dtype='float64'), 'chronic': pd.Series(dtype='float64'), 'historic': pd.Series(dtype='float64')}

    baselines = {}
    baselines['recovery'] = daily_df[daily_df['atl'] < daily_df['atl'].quantile(0.4)][['restingHR', 'hrv']].mean()
    baselines['chronic'] = daily_df[['restingHR', 'hrv']].tail(28).mean()
    baselines['historic'] = daily_df[['restingHR', 'hrv']].tail(60).mean()

    return baselines

def get_readiness_analysis_v11(selected_date, manual_context):
    start_date = selected_date - timedelta(days=90)
    end_date = selected_date
    df = get_wellness_data(start_date, end_date)

    if df.empty or pd.to_datetime(selected_date).strftime('%Y-%m-%d') not in df.index:
        return {"error": f"No hay datos de bienestar para el día {selected_date.strftime('%d-%m-%Y')}"}

    today_data = df.loc[selected_date.strftime('%Y-%m-%d')]
    df_including_today = df[df.index <= pd.to_datetime(selected_date)]
    
    hrv_hoy = today_data.get('hrv')
    rhr_hoy = today_data.get('restingHR')
    sleep_score_hoy = today_data.get('sleepScore')

    yesterday_str = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    ctl_ayer, atl_ayer, tsb_ayer = None, None, None
    if pd.to_datetime(yesterday_str) in df_including_today.index:
        yesterday_data = df_including_today.loc[yesterday_str]
        ctl_ayer = yesterday_data.get('ctl')
        atl_ayer = yesterday_data.get('atl')
        if pd.notna(ctl_ayer) and pd.notna(atl_ayer):
            tsb_ayer = ctl_ayer - atl_ayer

    score, breakdown, alerts = 0, [], []
    hrv_verdict, rhr_verdict, sleep_verdict = "N/A", "N/A", "N/A"
    hrv_points, rhr_points, sleep_points = 0, 0, 0
    
    past_df = df_including_today.iloc[:-1]
    historic_baseline = past_df.tail(min(60, len(past_df)))
    baselines = calculate_baselines(past_df)
    
    # --- INICIO: LÓGICA DE PUNTUACIÓN MEJORADA (v11) ---
    
    # 1. SUEÑO (MÁS GRANULAR)
    if len(df_including_today) >= 28:
        sleep_ma7 = df_including_today['sleepScore'].tail(7).mean()
        sleep_ma28 = df_including_today['sleepScore'].tail(28).mean()
        if pd.notna(sleep_ma7) and pd.notna(sleep_ma28):
            if sleep_ma7 >= sleep_ma28: sleep_points = 15
            elif sleep_ma7 > sleep_ma28 * 0.95: sleep_points = 12
            elif sleep_ma7 >= sleep_ma28 * 0.9: sleep_points = 7
            
            if len(df_including_today) > 1 and pd.notna(sleep_score_hoy) and sleep_score_hoy < 70 and df_including_today['sleepScore'].iloc[-2] < 70:
                score -= 5
                alerts.append("Penalización: 2 noches seguidas de mal sueño.")
            
            if len(df_including_today) > 2 and (df_including_today['sleepScore'].tail(3) > 80).all():
                score += 2
                alerts.append("Bonus: 3 noches seguidas de buen sueño.")

            score += sleep_points
            breakdown.append(f"P. Sueño (MA7 vs MA28) -> {sleep_points} ptos.")
            sleep_verdict = "✅ Bueno" if sleep_points >= 12 else "⚠️ Regular" if sleep_points >= 7 else "🚫 Pobre"

    # 2. RHR (ESCALA FINA Y TENDENCIA)
    rhr_baseline_rec = baselines.get('recovery', pd.Series()).get('restingHR')
    if pd.notna(rhr_hoy) and pd.notna(rhr_baseline_rec):
        rhr_deviation = rhr_hoy - rhr_baseline_rec
        if rhr_deviation <= 1: rhr_points = 35
        elif rhr_deviation <= 2: rhr_points = 25
        elif rhr_deviation <= 3: rhr_points = 15
        
        score += rhr_points
        breakdown.append(f"FC Reposo (vs rec) -> {rhr_points} ptos.")
        rhr_verdict = "✅ Óptimo" if rhr_points >= 25 else "⚠️ Ligeramente Elevado" if rhr_points >= 15 else "🚫 Elevado"
        
        if len(df_including_today) >= 7:
            rhr_ma7_today = df_including_today['restingHR'].tail(7).mean()
            rhr_ma7_3days_ago = df_including_today.head(-3)['restingHR'].tail(7).mean()
            if pd.notna(rhr_ma7_today) and pd.notna(rhr_ma7_3days_ago) and rhr_ma7_today > rhr_ma7_3days_ago * 1.03:
                score -= 5
                alerts.append("Penalización: Tendencia RHR MA7 al alza (>3% en 3 días).")

    # 3. HRV (TENDENCIA SENSIBLE Y VOLATILIDAD)
    hrv_baseline_hist_mean = historic_baseline['hrv'].mean()
    hrv_baseline_hist_std = historic_baseline['hrv'].std()
    hrv_ma7_today = df_including_today['hrv'].tail(7).mean()
    
    if len(df_including_today) >= 10:
        hrv_ma7_3days_ago = df_including_today.head(-3)['hrv'].tail(7).mean()
        if pd.notna(hrv_ma7_today) and pd.notna(hrv_ma7_3days_ago):
            decline_percentage = (1 - (hrv_ma7_today / hrv_ma7_3days_ago)) * 100
            if decline_percentage > 10:
                score -= 10; alerts.append(f"Penalización Fuerte: HRV MA7 en caída >10%.")
            elif decline_percentage > 5:
                score -= 5; alerts.append(f"Penalización: HRV MA7 en caída >5%.")

    if len(df_including_today) >= 7:
        hrv_std_7d = df_including_today['hrv'].tail(7).std()
        if pd.notna(hrv_std_7d) and pd.notna(hrv_baseline_hist_std) and hrv_std_7d > hrv_baseline_hist_std * 1.5:
            alerts.append("Aviso: Volatilidad de HRV reciente es alta.")

    if pd.notna(hrv_hoy) and pd.notna(hrv_baseline_hist_mean) and pd.notna(hrv_baseline_hist_std) and hrv_baseline_hist_std > 0:
        z_score = (hrv_ma7_today - hrv_baseline_hist_mean) / hrv_baseline_hist_std
        if z_score >= 0.5: hrv_points = 50
        elif -0.5 <= z_score < 0.5: hrv_points = 35
        elif -1.0 <= z_score < -0.5: hrv_points = 20
        score += hrv_points
        breakdown.append(f"VFC (HRV Z-Score): {z_score:.2f} -> {hrv_points} ptos.")
    
    is_hrv_low = hrv_points <= 20
    is_rhr_low = rhr_points >= 35

    # 4. MODIFICADORES DE CARGA (CTL/ATL/TSB)
    if atl_ayer is not None and historic_baseline['atl'].mean() is not None:
        if atl_ayer > historic_baseline['atl'].mean() and is_hrv_low:
            score -= 5; alerts.append("Penalización: Carga aguda (ATL) alta con HRV bajo.")
            
    if tsb_ayer is not None:
        if tsb_ayer < -20: score -= 10
        elif 0 <= tsb_ayer <= 10: score += 5; alerts.append("Bonus: TSB en 'zona dulce'.")
        elif tsb_ayer > 10: score += 5
    
    # 5. VEREDICTOS Y COMBINACIONES
    verdict_text = ""
    is_rhr_high = rhr_points <= 15
    is_hrv_high = hrv_points >= 50
    is_hrv_declining = any("HRV MA7 en caída" in s for s in alerts)

    if is_hrv_low and is_rhr_high and is_hrv_declining:
        score = min(score, 30); verdict_text = "🚫 TRIPLE ALARMA: HRV bajo, RHR alto y tendencia negativa."
    elif is_hrv_low and is_rhr_high:
        score = min(score, 40); verdict_text = "🚫 LUZ ROJA: Fatiga Sistémica (HRV bajo + RHR alto)."
    elif is_hrv_low and is_rhr_low:
        verdict_text = "⚠️ PRECAUCIÓN: Posible fatiga parasimpática (HRV y RHR bajos)."
    elif is_hrv_high and is_rhr_low:
        score += 5; alerts.append("Bonus: Recuperación óptima (HRV alto + RHR bajo).")
    
    hrv_verdict = "✅ Óptimo" if hrv_points >= 35 else "⚠️ Estable" if hrv_points >= 20 else "🚫 Bajo"
    if hrv_hoy > hrv_baseline_hist_mean + (2 * hrv_baseline_hist_std):
        if is_rhr_high: hrv_verdict = "🚫 Incoherente"
        else: hrv_verdict = "✅ Pico Positivo"

    # 6. MODIFICADORES DE CONTEXTO Y VEREDICTO FINAL
    if "Estrés Laboral/Personal" in manual_context: score -= 5
    if "Calor Extremo" in manual_context: score -= 5
    if "Alcohol" in manual_context: score -= 7
    if "Enfermedad Leve" in manual_context: score -= 10
    
    score = max(0, min(100, int(score)))

    if not verdict_text:
        if score >= 80: verdict_text = "✅ LUZ VERDE: Estado óptimo para entrenar."
        elif score >= 60: verdict_text = "⚠️ LUZ AMARILLA: Estado aceptable. Considerar modificar."
        else: verdict_text = "🚫 LUZ ROJA: Señales de fatiga significativa."
     
    return {
        "verdict": verdict_text, "readiness_score": score, "score_breakdown": breakdown, "alerts": alerts,
        "metrics": { "VFC (HRV)": hrv_hoy, "FC Reposo": rhr_hoy, "Puntuación Sueño": sleep_score_hoy },
        "verdicts": {"hrv": hrv_verdict, "rhr": rhr_verdict, "sleep": sleep_verdict},
        "points": {"hrv": hrv_points, "rhr": rhr_points, "sleep": sleep_points},
        "baselines": baselines,
        "load_metrics": {"ctl": ctl_ayer, "atl": atl_ayer, "tsb": tsb_ayer},
        "manual_context": manual_context
    }

def generate_health_summary_range(start_date, end_date):
    extended_start = start_date - timedelta(days=84)
    df = get_wellness_data(extended_start, end_date)
    if df.empty: return "No hay datos disponibles para el rango seleccionado."
    numeric_cols = ['hrv', 'restingHR', 'sleepScore', 'ctl', 'atl']
    for col in numeric_cols:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    range_df = df.loc[start_date.strftime('%Y-%m-%d'):end_date.strftime('%Y-%m-%d')]
    if range_df.empty: return "No hay datos disponibles para el rango seleccionado."
    
    summary_text = f"**📊 RESUMEN DE MÉTRICAS DE SALUD**\n**Período:** {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}\n\n"
    for date_idx, row in range_df.iterrows():
        date_str = date_idx.strftime('%d/%m/%Y')
        hrv, rhr, sleep_score = row.get('hrv'), row.get('restingHR'), row.get('sleepScore')
        ctl, atl = row.get('ctl'), row.get('atl')
        tsb = ctl - atl if pd.notna(ctl) and pd.notna(atl) else None
        summary_text += f"**{date_str}:** HRV: {f'{hrv:.1f}' if pd.notna(hrv) else 'N/A'} | RHR: {f'{rhr:.0f}' if pd.notna(rhr) else 'N/A'} | Sueño: {f'{sleep_score:.0f}' if pd.notna(sleep_score) else 'N/A'} | TSB: {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}\n"
    summary_text += "\n---\n**📊 ESTADÍSTICAS DEL PERÍODO:**\n"
    def get_stats(series):
        if series.isna().all(): return "N/A"
        stats = series.describe()
        return f"Media: {stats['mean']:.1f}, Mín: {stats['min']:.1f}, Máx: {stats['max']:.1f}"
    summary_text += f"- **HRV:** {get_stats(range_df['hrv'])}\n- **FC Reposo:** {get_stats(range_df['restingHR'])}\n- **Sueño:** {get_stats(range_df['sleepScore'])}\n"
    return summary_text

# --- FUNCIONES DE LA INTERFAZ ---
def display_gauge(score):
    score_color = "#d9534f" if score < 60 else "#f0ad4e" if score < 80 else "#5cb85c"
    gauge_html = f"""<div class="gauge-container"><div class="gauge-fill" style="background-color: {score_color}; width: {min(score, 100)}%;">{score} / 100</div></div>"""
    st.markdown(gauge_html, unsafe_allow_html=True)

# --- INTERFAZ PRINCIPAL ---
st.title("🧠 Coach IA de Readiness v2.7.1")
selected_date = st.date_input("Selecciona la fecha de análisis:", datetime.now().date())
context_options = st.multiselect("Contexto del Día (Opcional):", ["Calor Extremo", "Estrés Laboral/Personal", "Viaje", "Alcohol", "Mala Nutrición", "Enfermedad Leve"])

if selected_date:
    analysis = get_readiness_analysis_v11(selected_date, context_options)
    if "error" in analysis:
        st.error(analysis["error"])
    else:
        tab1, tab2, tab3 = st.tabs(["📊 Readiness Diario", "❤️ Líneas Basales", "🗓️ Resumen por Rango"])
        with tab1:
            load = analysis.get("load_metrics", {})
            ctl, atl, tsb = load.get('ctl'), load.get('atl'), load.get('tsb')
            st.markdown('<div class="card-grid">', unsafe_allow_html=True)
            g_col1, g_col2, g_col3 = st.columns(3)
            with g_col1: st.metric(label="Forma (CTL) Ayer", value=f"{ctl:.1f}" if pd.notna(ctl) else "N/A")
            with g_col2: st.metric(label="Fatiga (ATL) Ayer", value=f"{atl:.1f}" if pd.notna(atl) else "N/A")
            with g_col3: st.metric(label="Frescura (TSB) Ayer", value=f"{tsb:.1f}" if pd.notna(tsb) else "N/A")
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---"); st.subheader("💡 Veredicto y Coaching del Día")
            if analysis.get("manual_context"):
                st.warning(f"**Contexto Manual:** {', '.join(analysis['manual_context'])}. Penalización aplicada.")
            st.info(f"**{analysis.get('verdict', 'Análisis no disponible')}**")

            st.markdown("##### Vistazo Rápido del Día")
            col1, col2, col3 = st.columns(3)
            verdicts, points = analysis.get('verdicts', {}), analysis.get('points', {})
            with col1: st.markdown(f'<div class="card">🧬 **HRV:** {verdicts.get("hrv", "N/A")} ({points.get("hrv", 0)} ptos.)</div>', unsafe_allow_html=True)
            with col2: st.markdown(f'<div class="card">❤️ **RHR:** {verdicts.get("rhr", "N/A")} ({points.get("rhr", 0)} ptos.)</div>', unsafe_allow_html=True)
            with col3: st.markdown(f'<div class="card">🛌 **Sueño:** {verdicts.get("sleep", "N/A")} ({points.get("sleep", 0)} ptos.)</div>', unsafe_allow_html=True)
            
            st.markdown("---"); st.subheader("📈 Puntuación y Métricas Detalladas del Día")
            d_col1, d_col2 = st.columns([1, 2])
            with d_col1:
                st.markdown(f"**Puntuación de Readiness:**"); display_gauge(analysis.get('readiness_score', 0))
            with d_col2:
                metrics = analysis.get('metrics', {})
                hrv, rhr, sleep = metrics.get('VFC (HRV)'), metrics.get('FC Reposo'), metrics.get('Puntuación Sueño')
                sub_col1, sub_col2, sub_col3 = st.columns(3)
                with sub_col1: st.metric("VFC (HRV)", f"{hrv:.1f} ms" if pd.notna(hrv) else "N/A")
                with sub_col2: st.metric("FC Reposo", f"{rhr:.0f} bpm" if pd.notna(rhr) else "N/A")
                with sub_col3: st.metric("Puntuación Sueño", f"{sleep:.0f}" if pd.notna(sleep) else "N/A")
            
            with st.expander("Ver desglose y alertas del cálculo"):
                 st.markdown("##### Desglose de Puntos:"); st.markdown("\n".join(f"- {item}" for item in analysis.get('score_breakdown', [])))
                 if analysis.get('alerts'):
                     st.markdown("##### Alertas y Bonificaciones:"); st.markdown("\n".join(f"- {alert}" for alert in analysis.get('alerts')))

            with st.expander("📋 Resumen para Copiar al Coach"):
                metrics = analysis.get('metrics', {})
                hrv_hoy = metrics.get('VFC (HRV)')
                rhr_hoy = metrics.get('FC Reposo')
                sleep_hoy = metrics.get('Puntuación Sueño')
                baselines = analysis.get('baselines', {})
                baseline_types = {'recovery': 'De Recuperación', 'chronic': 'Crónica (28d)', 'historic': 'Histórica (60d)'}
                
                resumen_texto = f"**Resumen de Salud para el {selected_date.strftime('%d/%m/%Y')}**\n\n"
                resumen_texto += f"**Carga (Ayer):** CTL: {f'{ctl:.1f}' if pd.notna(ctl) else 'N/A'}, ATL: {f'{atl:.1f}' if pd.notna(atl) else 'N/A'}, TSB: {f'{tsb:.1f}' if pd.notna(tsb) else 'N/A'}\n---\n"
                resumen_texto += f"**Veredicto y Puntuación:** {analysis.get('verdict', 'N/A')} ({analysis.get('readiness_score', 'N/A')} / 100)\n---\n"
                resumen_texto += f"**Métricas Clave:** HRV: {f'{hrv_hoy:.1f} ms' if pd.notna(hrv_hoy) else 'N/A'} | RHR: {f'{rhr_hoy:.0f} bpm' if pd.notna(rhr_hoy) else 'N/A'} | Sueño: {f'{sleep_hoy:.0f}' if pd.notna(sleep_hoy) else 'N/A'}\n---\n"
                resumen_texto += "**Desglose:**\n" + "\n".join(f"- {item}" for item in analysis.get('score_breakdown', []))
                if analysis.get('alerts'):
                    resumen_texto += "\n\n**Alertas y Bonificaciones:**\n" + "\n".join(f"- {alert}" for alert in analysis.get('alerts'))
                resumen_texto += "\n\n---\n**Líneas Basales:**\n"
                for key, name in baseline_types.items():
                    rhr_base, hrv_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv')
                    resumen_texto += f"- **{name}:** RHR: {f'{rhr_base:.1f}' if pd.notna(rhr_base) else 'N/A'}, HRV: {f'{hrv_base:.1f}' if pd.notna(hrv_base) else 'N/A'}\n"
                st.code(resumen_texto, language='markdown')

        with tab2:
            st.header("❤️ Tus Líneas Basales de Referencia")
            baselines = analysis.get('baselines', {})
            b_col1, b_col2, b_col3 = st.columns(3)
            for col, (key, name) in zip([b_col1, b_col2, b_col3], baseline_types.items()):
                with col:
                    st.subheader(name)
                    rhr_base, hrv_base = baselines.get(key, {}).get('restingHR'), baselines.get(key, {}).get('hrv')
                    st.metric("RHR", f"{rhr_base:.1f} bpm" if pd.notna(rhr_base) else "N/A")
                    st.metric("HRV", f"{hrv_base:.1f} ms" if pd.notna(hrv_base) else "N/A")

        with tab3:
            st.header("🗓️ Resumen de Métricas por Rango")
            col_fecha1, col_fecha2 = st.columns(2)
            with col_fecha1: fecha_inicio = st.date_input("Fecha de inicio:", value=(datetime.now() - timedelta(days=7)).date(), key="fecha_inicio_rango")
            with col_fecha2: fecha_fin = st.date_input("Fecha de fin:", value=datetime.now().date(), key="fecha_fin_rango")
            if fecha_inicio <= fecha_fin:
                if st.button("🔄 Generar Resumen por Rango", type="primary"):
                    with st.spinner("Generando resumen..."):
                        resumen_rango = generate_health_summary_range(fecha_inicio, fecha_fin)
                        with st.expander("📋 Resumen por Rango - Copiar y Pegar", expanded=True):
                            st.code(resumen_rango, language='markdown')
            else:
                st.error("⚠️ La fecha de inicio debe ser anterior o igual a la fecha de fin.")