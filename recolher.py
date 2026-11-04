"""Corre no GitHub Actions: vai buscar as odds da NBA e junta-as a odds/AAAA-MM-DD.csv."""
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

MERCADOS = sys.argv[1] if len(sys.argv) > 1 else "h2h,spreads,totals"
COLUNAS = ["recolhido_em", "jogo_id", "inicio_jogo", "casa", "fora", "casa_apostas",
           "atualizado_em", "mercado", "resultado", "odd", "linha"]

r = requests.get(
    "https://api.the-odds-api.com/v4/sports/basketball_nba/odds",
    params={"apiKey": os.environ["ODDS_API_KEY"], "regions": "eu",
            "markets": MERCADOS, "oddsFormat": "decimal"},
    timeout=30,
)
r.raise_for_status()
agora = datetime.now(timezone.utc)
recolhido = agora.strftime("%Y-%m-%dT%H:%M:%SZ")

linhas = []
for g in r.json():
    for b in g.get("bookmakers", []):
        for m in b.get("markets", []):
            for o in m.get("outcomes", []):
                linhas.append([recolhido, g["id"], g["commence_time"], g["home_team"],
                               g["away_team"], b["key"], b.get("last_update"), m["key"],
                               o["name"], o["price"], o.get("point", "")])

ficheiro = Path("odds") / f"{agora:%Y-%m-%d}.csv"
ficheiro.parent.mkdir(exist_ok=True)
novo = not ficheiro.exists()
with ficheiro.open("a", newline="") as f:
    w = csv.writer(f)
    if novo:
        w.writerow(COLUNAS)
    w.writerows(linhas)

print(f"{recolhido}: {len(linhas)} odds ({MERCADOS}). "
      f"Pedidos restantes: {r.headers.get('x-requests-remaining')}")
