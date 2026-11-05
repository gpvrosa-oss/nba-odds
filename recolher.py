"""Corre no GitHub Actions: vai buscar as odds da NBA e junta-as a odds/AAAA-MM-DD.csv.

Modos:
  python recolher.py completo   -> vencedor, handicap e totais (3 pedidos)
  python recolher.py fecho      -> so vencedor, e so se houver um jogo a comecar em breve (1 pedido)

No modo fecho, primeiro consulta a lista de jogos (/events), que nao gasta pedidos.
"""
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
KEY = os.environ["ODDS_API_KEY"]
COLUNAS = ["recolhido_em", "jogo_id", "inicio_jogo", "casa", "fora", "casa_apostas",
           "atualizado_em", "mercado", "resultado", "odd", "linha"]
JANELA_MIN = 45        # recolhe o fecho se um jogo comeca nos proximos 45 minutos
INTERVALO_MIN = 40     # e se a ultima recolha de fecho foi ha mais de 40 minutos
ESTADO = Path("odds") / "ultimo_fecho.txt"

modo = sys.argv[1] if len(sys.argv) > 1 else "completo"
agora = datetime.now(timezone.utc)

if modo == "fecho":
    eventos = requests.get(f"{API}/events", params={"apiKey": KEY}, timeout=30)
    eventos.raise_for_status()
    print(f"Lista de jogos: custou {eventos.headers.get('x-requests-last')} pedidos "
          f"(restantes {eventos.headers.get('x-requests-remaining')})")
    proximos = [e for e in eventos.json()
                if timedelta(0) < datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - agora
                <= timedelta(minutes=JANELA_MIN)]
    ultimo = datetime.fromisoformat(ESTADO.read_text().strip()) if ESTADO.exists() else None
    if not proximos:
        print(f"{agora:%H:%M} UTC: nenhum jogo nos proximos {JANELA_MIN} minutos. Nada a fazer.")
        sys.exit(0)
    if ultimo and agora - ultimo < timedelta(minutes=INTERVALO_MIN):
        print(f"{agora:%H:%M} UTC: ultima recolha de fecho ha menos de {INTERVALO_MIN} minutos.")
        sys.exit(0)
    mercados = "h2h"
else:
    mercados = "h2h,spreads,totals"

r = requests.get(f"{API}/odds", params={"apiKey": KEY, "regions": "eu", "markets": mercados,
                                        "oddsFormat": "decimal"}, timeout=30)
r.raise_for_status()
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
if modo == "fecho":
    ESTADO.write_text(agora.isoformat())

print(f"{recolhido}: {len(linhas)} odds ({mercados}). "
      f"Pedidos restantes: {r.headers.get('x-requests-remaining')}")
