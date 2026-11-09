# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify
import pandas as pd
import requests
from pathlib import Path

app = Flask(__name__)
BASE = Path(__file__).resolve().parent
CACHE = BASE / "municipios_cache.csv"
URL_MUNICIPIOS = "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/main/csv/municipios.csv"
URL_ESTADOS = "https://raw.githubusercontent.com/kelvins/Municipios-Brasileiros/main/csv/estados.csv"

def carregar_municipios():
    if CACHE.exists():
        return pd.read_csv(CACHE, dtype={"codigo_ibge": str, "codigo_uf": str})
    municipios = pd.read_csv(URL_MUNICIPIOS, dtype=str)
    estados = pd.read_csv(URL_ESTADOS, dtype=str)
    municipios.columns = [c.strip().lower() for c in municipios.columns]
    estados.columns = [c.strip().lower() for c in estados.columns]
    municipios = municipios.rename(columns={"nome": "municipio"})
    estados = estados.rename(columns={"nome": "estado"})
    municipios["codigo_uf"] = municipios["codigo_uf"].str.replace(".0", "", regex=False).str.zfill(2)
    estados["codigo_uf"] = estados["codigo_uf"].str.replace(".0", "", regex=False).str.zfill(2)
    df = municipios.merge(estados[["codigo_uf", "uf", "estado"]], on="codigo_uf", how="left")
    df["codigo_ibge"] = df["codigo_ibge"].str.replace(".0", "", regex=False).str.zfill(7)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["municipio", "uf", "latitude", "longitude"])
    df = df[["codigo_ibge", "municipio", "uf", "estado", "latitude", "longitude"]].drop_duplicates("codigo_ibge")
    try:
        df.to_csv(CACHE, index=False, encoding="utf-8-sig")
    except OSError:
        pass
    return df

MUNICIPIOS = carregar_municipios()

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/api/cidades")
def cidades():
    termo = request.args.get("q", "").strip().lower()
    if len(termo) < 2:
        return jsonify([])
    mask = (MUNICIPIOS["municipio"].str.lower().str.contains(termo, regex=False) |
            MUNICIPIOS["uf"].str.lower().str.contains(termo, regex=False))
    dados = MUNICIPIOS.loc[mask].sort_values(["municipio", "uf"]).head(20)
    return jsonify([{"id": r.codigo_ibge, "nome": r.municipio, "uf": r.uf, "estado": r.estado,
                     "latitude": r.latitude, "longitude": r.longitude} for r in dados.itertuples()])

@app.get("/api/previsao")
def previsao():
    codigo = request.args.get("codigo", "").strip()
    cidade = MUNICIPIOS[MUNICIPIOS["codigo_ibge"] == codigo]
    if cidade.empty:
        return jsonify({"erro": "Municipio nao encontrado."}), 404
    c = cidade.iloc[0]
    params = {
        "latitude": float(c.latitude), "longitude": float(c.longitude),
        "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset",
        "timezone": "America/Sao_Paulo", "forecast_days": 15,
        "models": "ecmwf_ifs025", "wind_speed_unit": "kmh", "precipitation_unit": "mm"
    }
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=60)
        r.raise_for_status()
        d = r.json().get("daily", {})
        previsoes=[]
        for i, data in enumerate(d.get("time", [])):
            previsoes.append({
                "data": data,
                "temp_max": d["temperature_2m_max"][i], "temp_min": d["temperature_2m_min"][i],
                "sensacao_max": d["apparent_temperature_max"][i], "sensacao_min": d["apparent_temperature_min"][i],
                "chuva_mm": d["precipitation_sum"][i], "chance_chuva": d["precipitation_probability_max"][i],
                "vento_max": d["wind_speed_10m_max"][i], "rajada_max": d["wind_gusts_10m_max"][i],
                "nascer_sol": d["sunrise"][i], "por_sol": d["sunset"][i]
            })
        return jsonify({"cidade": c.municipio, "uf": c.uf, "estado": c.estado,
                        "latitude": c.latitude, "longitude": c.longitude,
                        "modelo": "ECMWF IFS 0.25°", "previsoes": previsoes})
    except requests.RequestException as e:
        return jsonify({"erro": f"Falha ao consultar a previsao: {e}"}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
