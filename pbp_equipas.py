"""Estatisticas avancadas por equipa e por jogo (posses, lancamentos junto ao cesto, meia distancia, triplos)
a partir da API gratis do PBP Stats -> dados/pbp_equipas.csv. A defesa de cada equipa = o que o adversario fez
nesse jogo. ~60 pedidos (30 equipas x 2 epocas), com pausa entre eles.
"""
import time
from pathlib import Path
import pandas as pd
import requests

H = {"User-Agent": "nba-odds-research/1.0 (personal project)"}
API = "https://api.pbpstats.com"
F = Path("dados") / "pbp_equipas.csv"

eq = requests.get(f"{API}/get-teams/nba", headers=H, timeout=30).json()
equipas = eq.get("teams", eq)
print("equipas:", len(equipas), "exemplo:", str(equipas[0])[:200])
antigos = pd.read_csv(F, low_memory=False) if F.exists() else pd.DataFrame()
feitos = set(zip(antigos.get("Epoca", []), antigos.get("TeamId", []).astype(str) if len(antigos) else [], antigos.get("Tipo", []) if "Tipo" in antigos else []))
linhas = antigos.to_dict("records") if len(antigos) else []
for epoca in ["2024-25", "2025-26", "2026-27"]:
    for t in equipas:
        tid = t.get("id") or t.get("TeamId")
        for tipo in ["Regular Season", "Playoffs"]:
            if (epoca, str(tid), tipo) in feitos:
                continue
            for tent in range(5):
                r = requests.get(f"{API}/get-game-logs/nba", headers=H, timeout=30,
                                 params={"Season": epoca, "SeasonType": tipo, "EntityType": "Team", "EntityId": tid})
                time.sleep(3.0)
                if r.status_code == 200:
                    break
                time.sleep(10 * (tent + 1))
            if r.status_code != 200:
                print("erro", epoca, tid, tipo, r.status_code); continue
            j = r.json()
            rows = j.get("multi_row_table_data", [])
            for x in rows:
                x["TeamId"] = tid; x["Tipo"] = tipo; x["TeamAbbr"] = t.get("text") or t.get("abbreviation"); x["Epoca"] = epoca
            linhas += rows
    print(epoca, "linhas ate agora:", len(linhas))
df = pd.DataFrame(linhas)
F.parent.mkdir(exist_ok=True)
df.to_csv(F, index=False)
print("colunas:", list(df.columns)[:80])
print(df.head(2).T.head(40))
