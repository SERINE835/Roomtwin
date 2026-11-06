from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import subprocess
import os
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MATLAB_PATH   = r"C:\Program Files\Polyspace\R2020a\bin\matlab.exe"
SCRIPT_PATH   = r"C:\Users\user\Desktop\pfe\data.mlx"
JSON_PATH     = r"C:\Users\HP\OneDrive\Dokumente\pfe\smartroom_results.json"
SETTINGS_PATH = r"C:\Users\HP\OneDrive\Dokumente\pfe\smartroom_settings.json"

# ── Max points envoyés au frontend ──
# sessionStorage est limité à ~5MB → 500 points suffisent pour les graphes
MAX_POINTS = 500

class Settings(BaseModel):
    T_setpoint: float
    PLIGHTING:  float
    PDEVICE:    float
    T_EXT:      float = 30
    CO2_EXT2:   float = 500
    H_EXT:      float = 0.01


def downsample(data: dict, n: int = MAX_POINTS) -> dict:
    """
    Réduit tous les tableaux à n points max.
    Sans ça : 864 046 points → sessionStorage plante → données disparaissent.
    """
    result = {}
    for key, val in data.items():
        if isinstance(val, list) and len(val) > n:
            step = len(val) // n
            result[key] = val[::step][:n]
        else:
            result[key] = val
    return result


@app.post("/settings")
def save_and_run(settings: Settings):
    print("\n🔥 ===== /SETTINGS APPELÉ =====")
    print("📥 DATA REÇUE :", settings.dict())

    # 1 — Sauvegarde paramètres
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings.dict(), f, indent=2)
    print("💾 SETTINGS SAUVEGARDÉS")

    # 2 — Lancer MATLAB (ne pas supprimer le JSON avant)
    matlab_cmd = [
        MATLAB_PATH,
        "-nosplash", "-nodesktop", "-batch",
        f"run('{SCRIPT_PATH}')"
    ]

    try:
        result = subprocess.run(
            matlab_cmd,
            timeout=300,
            capture_output=True,
            text=True,
            encoding='latin-1',
            errors='ignore'
        )

        if result.returncode != 0:
            print("❌ MATLAB ERROR :", result.stderr)
            return JSONResponse(
                status_code=500,
                content={"error": "MATLAB error", "details": result.stderr}
            )
        print("✅ MATLAB exécuté avec succès")

    except subprocess.TimeoutExpired:
        return JSONResponse(status_code=500, content={"error": "MATLAB timeout"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    # 3 — Attendre le JSON
    print("⏳ Attente du fichier JSON...")
    for i in range(60):
        if os.path.exists(JSON_PATH):
            try:
                with open(JSON_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                data = downsample(raw)
                print(f"📊 JSON chargé — {len(raw.get('time', []))} pts → {MAX_POINTS} pts")
                return JSONResponse(content={"message": "Simulation terminée !", "data": data})
            except:
                time.sleep(1)
        else:
            time.sleep(1)

    return JSONResponse(status_code=500, content={"error": "JSON non généré après simulation"})


@app.get("/data")
def get_data():
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return JSONResponse(content=downsample(raw))
    except Exception as e:
        return JSONResponse(status_code=404, content={"error": str(e)})


@app.get("/status")
def get_status():
    return {"status": "running", "json_exists": os.path.exists(JSON_PATH)}


app.mount("/", StaticFiles(directory=".", html=True), name="static")