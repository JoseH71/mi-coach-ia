import requests
import base64
from datetime import datetime, timedelta

print("🏃 Script de Jose listo para correr")

# Configuración de Intervals.icu
api_key = "27i9azt55smmhvg1ogc5gmn7x"
athlete_id = "i10474"
base_url = "https://intervals.icu/api/v1"
auth_str = f"API_KEY:{api_key}"
encoded_auth = base64.b64encode(auth_str.encode()).decode()
headers = {"Authorization": f"Basic {encoded_auth}"}

# Configuración de Telegram
telegram_token = "7783495659:AAHw0NOvktsz_IxQQJl3SmKiWWDm92gCNZk"
chat_id = "720749629"

def send_telegram_message(message):
    telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    response = requests.post(telegram_url, json=payload)
    print("📬 Mensaje enviado" if response.status_code == 200 else f"❌ Error: {response.status_code}")

def fetch_wellness_data(start, end):
    url = f"{base_url}/athlete/{athlete_id}/wellness?oldest={start}&newest={end}"
    response = requests.get(url, headers=headers)
    return response.json() if response.status_code == 200 else []

def process_data(data):
    if not data:
        return None
    d = data[-1]
    return {
        'RHR': d.get('restingHR', 0) or 0,
        'HRV': d.get('hrv', 0) or 0,
        'SleepScore': d.get('sleepScore', 0) or 0,
        'BodyBatteryMax': d.get('BodyBatteryMax', 0) or 0,
        'BodyBatteryMin': d.get('BodyBatteryMin', 0) or 0
    }

def generate_alerts(latest, baselines):
    alerts = []
    rhr = latest['RHR']
    hrv = latest['HRV']
    sleep = latest['SleepScore']
    bb_max = latest['BodyBatteryMax']
    bb_min = latest['BodyBatteryMin']

    if rhr >= 50 and rhr > baselines['RHR_7d'] + 5:
        alerts.append(f"⚠️ RHR {rhr} bpm (+5 sobre basal {baselines['RHR_7d']})")

    hrv_drop = (baselines['HRV_7d'] - hrv) / baselines['HRV_7d'] * 100
    if hrv_drop >= 15:
        alerts.append(f"⚠️ HRV {hrv} ms (-{hrv_drop:.1f}% de basal {baselines['HRV_7d']})")

    if sleep <= 64 and sleep < baselines['Sleep_7d'] - 10:
        alerts.append(f"⚠️ Sleep Score {sleep} (< basal {baselines['Sleep_7d']} - 10)")

    if bb_max <= 70 and bb_max < baselines['BBMax_7d'] - 10:
        alerts.append(f"⚠️ BB Max {bb_max} (< basal {baselines['BBMax_7d']} - 10)")

    if bb_min < 25:
        alerts.append(f"⚠️ BB Min {bb_min} (< 25)")

    return alerts

def calculate_baselines(data_7d, data_14d, data_60d):
    def avg(metric, data):
        values = [d.get(metric, 0) or 0 for d in data if d.get(metric) is not None]
        return round(sum(values) / len(values)) if values else 0

    return {
        'RHR_7d': avg('restingHR', data_7d),
        'HRV_7d': avg('hrv', data_7d),
        'Sleep_7d': avg('sleepScore', data_7d),
        'BBMax_7d': avg('BodyBatteryMax', data_7d),
        'BBMin_7d': avg('BodyBatteryMin', data_7d)
    }

# Main
today = datetime.now()
newest = today.strftime("%Y-%m-%d")
oldest = newest

data_1d = fetch_wellness_data(oldest, newest)
data_7d = fetch_wellness_data((today - timedelta(days=7)).strftime("%Y-%m-%d"), newest)
data_14d = fetch_wellness_data((today - timedelta(days=14)).strftime("%Y-%m-%d"), newest)
data_60d = fetch_wellness_data((today - timedelta(days=60)).strftime("%Y-%m-%d"), newest)

latest = process_data(data_1d)
baselines = calculate_baselines(data_7d, data_14d, data_60d)

message = f"📊 *Wellness ({newest})*\n"
if not latest:
    message += "No hay datos."
    print(f"❌ Sin datos en Intervals.icu para {newest}")
else:
    message += (
        f"RHR: {latest['RHR']} bpm\n"
        f"HRV: {latest['HRV']} ms\n"
        f"Sleep: {latest['SleepScore']}\n"
        f"BB Max: {latest['BodyBatteryMax']}\n"
        f"BB Min: {latest['BodyBatteryMin']}\n"
    )
    print(f"✅ Datos procesados para {newest}")

alerts = generate_alerts(latest, baselines) if latest else []
if alerts:
    message += "\n*Alertas:*\n" + "\n".join(alerts)
    print("🚨 Alertas generadas")
else:
    message += "\n✅ *Sin alertas*"
    print("✅ Sin alertas")

send_telegram_message(message)
