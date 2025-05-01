from flask import Flask
import subprocess
import os

app = Flask(__name__)

# Endpoint para UptimeRobot (solo para mantener el servicio despierto)
@app.route("/ping")
def ping():
    return "Pong"  # Respuesta simple, no ejecuta el script

# Endpoint para cron-job.org (ejecuta el script y envía el mensaje a Telegram)
@app.route("/")
def run_script():
    try:
        result = subprocess.run(["python3", "intervals_to_telegram.py"], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return "OK"
        else:
            return f"Error: Script failed with code {result.returncode}"
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    print("Iniciando servidor Flask...")
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
