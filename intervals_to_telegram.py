import requests
import base64
from datetime import datetime, timedelta

# ✅ Mensaje inicial para confirmar ejecución
print("🏃 Script de Jose listo para correr")

# 🔐 Configuración de Intervals.icu
api_key = "27i9azt55smmhvg1ogc5gmn7x"
athlete_id = "i10474"
base_url = "https://intervals.icu/api/v1"
auth_str = f"API_KEY:{api_key}"
encoded_auth = base64.b64encode(auth_str.encode()).decode()
headers = {"Authorization": f"Basic {encoded_auth}"}

# 🔐 Configuración de Telegram
telegram_token = "7783495659:AAHw0NOvktsz_IxQQJl3SmKiWWDm92gCNZk"
chat_id = "720749629"

# ✅ Función para enviar mensaje a Telegram
def send_telegram_message(message):
    telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(telegram_url, json=payload)
    if response.status_code == 200:
        print("📬 Mensaje enviado a Telegram")
    else:
        print(f"❌ Error al enviar mensaje: {response.status_code} - {response.text}")

# 📅 Fecha dinámica
today = datetime.now()
newest = (today - timedelta(days=1)).strftime("%Y-%m-%d")
oldest = newest

# 📥 Obtener datos de wellness
def fetch_wellness_data(start, end):
    url = f"{base_url}/athlete/{athlete_id}/wellness?oldest={start}&newest={end}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json() or []
    print(f"❌ Error al obtener datos: {response.status_code} - {response.text}")
    return []

# 📊 Procesar datos de un día
def process_data(data):
    if not data:
        return None
    d = data[-1]
    return {
        'BodyBatteryMax': d.get('BodyBatteryMax', 'N/A'),
        'BodyBatteryMin': d.get('BodyBatteryMin', 'N/A'),
        'RHR': d.get('restingHR', 'N/A'),
        'HRV': d.get('hrv', 'N/A'),
        'SleepScore': d.get('sleepScore', 'N/A')
    }

# 🚨 Generar alertas
def generate_alerts(data_1d, data_14d):
    alerts = []
    if not data_1d or not data_14d:
        return alerts

    latest = data_1d[-1]
    latest_hrv = latest.get('hrv', 0) or 0
    latest_rhr = latest.get('restingHR', 0) or 0

    valid_hrv = [d.get('hrv') for d in data_14d if d.get('hrv') is not None]
    valid_rhr = [d.get('restingHR') for d in data_14d if d.get('restingHR') is not None]

    if valid_hrv:
        hrv_avg = sum(valid_hrv) / len(valid_hrv)
        if hrv_avg and latest_hrv:
            drop = (hrv_avg - latest_hrv) / hrv_avg * 100
            if drop > 15:
                alerts.append(f"⚠️ HRV bajó {drop:.1f}% (Promedio 14d: {hrv_avg:.1f}, Hoy: {latest_hrv:.1f})")

    if valid_rhr:
        rhr_avg = sum(valid_rhr) / len(valid_rhr)
        rise = latest_rhr - rhr_avg
        if rise > 5:
            alerts.append(f"⚠️ RHR subió {rise:.1f} bpm (Promedio 14d: {rhr_avg:.1f}, Hoy: {latest_rhr:.1f})")

    if latest_rhr > 50:
        alerts.append(f"🚨 RHR {latest_rhr:.1f} bpm supera umbral de FA (>50 bpm)")
    if latest_rhr > 90:
        alerts.append(f"🚨 RHR {latest_rhr:.1f} bpm supera límite crítico FA (>90 bpm)")

    return alerts

# 🧠 Main
data_1d = fetch_wellness_data(oldest, newest)
data_14d = fetch_wellness_data((today - timedelta(days=14)).strftime("%Y-%m-%d"), newest)
metrics = process_data(data_1d)

message = f"📊 *Datos de Wellness ({newest})*\n"
if not metrics:
    message += "No hay datos para este día."
else:
    message += (
        f"Body Battery - Máx: {metrics['BodyBatteryMax']}, Mín: {metrics['BodyBatteryMin']}\n"
        f"RHR: {metrics['RHR']} bpm\n"
        f"HRV: {metrics['HRV']} ms\n"
        f"Sleep Score: {metrics['SleepScore']}\n"
    )

alerts = generate_alerts(data_1d, data_14d)
if alerts:
    message += "\n*Alertas:*\n" + "\n".join(alerts)
else:
    message += "\n✅ *No hay alertas*"

# 📬 Enviar mensaje final
send_telegram_message(message)
