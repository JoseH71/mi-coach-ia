from flask import Flask
import subprocess
import os

app = Flask(__name__)

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
    port = int(os.getenv("PORT", 8080))  # Usa el puerto de Render, o 8080 por defecto
    app.run(host="0.0.0.0", port=port)
