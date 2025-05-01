from flask import Flask
import subprocess
import threading
import requests
import time

app = Flask(__name__)

def keep_alive():
    while True:
        try:
            requests.get("https://2f157143-8fca-4101-9afd-e18cff3014f1-00-1uczx4z8868kv.picard.replit.dev/")
            print("Ping interno enviado")
        except:
            print("Error en ping interno")
        time.sleep(300)  # Ping cada 5 minutos

@app.route("/")
def run_script():
    try:
        result = subprocess.run(["python3", "intervals_to_telegram.py"], capture_output=True, text=True, timeout=60)
        return f"✅ Script ejecutado:<br><pre>{result.stdout}</pre><br>❌ Errores:<br><pre>{result.stderr}</pre>"
    except Exception as e:
        return f"❌ Error al ejecutar: {e}"

if __name__ == "__main__":
    threading.Thread(target=keep_alive, daemon=True).start()  # Inicia el keep-alive en segundo plano
    app.run(host="0.0.0.0", port=81)
