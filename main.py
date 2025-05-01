from flask import Flask
import subprocess
import os

app = Flask(__name__)

@app.route("/")
def run_script():
    try:
        result = subprocess.run(["python3", "intervals_to_telegram.py"], capture_output=True, text=True, timeout=60)
        return f"✅ Script ejecutado:<br><pre>{result.stdout}</pre><br>❌ Errores:<br><pre>{result.stderr}</pre>"
    except Exception as e:
        return f"❌ Error al ejecutar: {e}"

if __name__ == "__main__":
    print("Iniciando servidor Flask...")
    port = int(os.getenv("PORT", 81))  # Usa el puerto de Render, o 81 por defecto
    app.run(host="0.0.0.0", port=port)
