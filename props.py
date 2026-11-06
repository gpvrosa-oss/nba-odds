"""Corre no GitHub Actions a cada 15 minutos: guarda as linhas de jogadores (props) da Pinnacle.

Para cada jogo guarda duas fotografias:
  cedo  -> entre 3h30 e 2h30 antes do inicio (o preco a que "apostariamos")
  fecho -> nos 45 minutos antes do inicio (a linha de fecho, para medir o CLV)
Junto com cada fotografia guarda as lesoes da ESPN nesse momento, para o teste ser justo
(o modelo so pode usar o que se sabia na altura).

Custo: 1 pedido por mercado por jogo por fotografia. A lista de jogos (/events) e gratis.
"""
import csv, json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
KEY = os.environ["ODDS_API_KEY"]
MERCADOS = os.environ.get("MERCADOS_PROPS", "player_points")
CASAS = "pinnacle"
JANELAS = {"cedo": (150, 210), "fecho": (0, 45)}   # minutos antes do inicio
PASTA = Path("props"); PASTA.mkdir(exist_ok=True)
ESTADO = PASTA / "estado.json"
COLUNAS = ["recolhido_em", "momento", "jogo_id", "inicio_jogo", "casa", "fora", "casa_apostas",
           "atualizado_em", "mercado", "jogador", "lado", "linha", "odd"]

agora = datetime.now(timezone.utc)
estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
ev = requests.get(f"{API}/events", params={"apiKey": KEY}, timeout=30)
ev.raise_for_status()

tarefas = []
for e in ev.json():
    falta = (datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - agora).total_seconds() / 60
    for momento, (a, b) in JANELAS.items():
        if a < falta <= b and momento not in estado.get(e["id"], []):
            tarefas.append((e, momento))
if not tarefas:
    print(f"{agora:%H:%M} UTC: nada a recolher.")
    sys.exit(0)

recolhido = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
linhas, restantes = [], None
for e, momento in tarefas:
    r = requests.get(f"{API}/events/{e['id']}/odds", params={"apiKey": KEY, "bookmakers": CASAS,
                     "markets": MERCADOS, "oddsFormat": "decimal"}, timeout=30)
    if r.status_code != 200:
        print("Erro", r.status_code, r.text[:200]); continue
    restantes = r.headers.get("x-requests-remaining")
    for bk in r.json().get("bookmakers", []):
        for m in bk.get("markets", []):
            for o in m.get("outcomes", []):
                linhas.append([recolhido, momento, e["id"], e["commence_time"], e["home_team"], e["away_team"],
                               bk["key"], m.get("last_update", bk.get("last_update")), m["key"],
                               o.get("description", ""), o["name"], o.get("point", ""), o["price"]])
    estado.setdefault(e["id"], []).append(momento)
    print(f"{momento}: {e['away_team']} @ {e['home_team']}")

ficheiro = PASTA / f"{agora:%Y-%m-%d}.csv"
novo = not ficheiro.exists()
with ficheiro.open("a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    if novo:
        w.writerow(COLUNAS)
    w.writerows(linhas)

# lesoes da ESPN no mesmo momento
try:
    inj = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries", timeout=30).json()
    les = PASTA / "lesoes" / f"{agora:%Y-%m-%dT%H%MZ}.json"
    les.parent.mkdir(exist_ok=True)
    les.write_text(json.dumps(inj))
except Exception as x:
    print("Lesoes ESPN falharam:", x)
# noticias da ESPN (mudancas de rotacao, titulares, etc.) para contexto no resumo da noite
try:
    nw = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news", params={"limit": 50}, timeout=30).json()
    nf = PASTA / "noticias" / f"{agora:%Y-%m-%dT%H%MZ}.json"
    nf.parent.mkdir(exist_ok=True)
    nf.write_text(json.dumps([{"titulo": a.get("headline"), "resumo": a.get("description"), "data": a.get("published")}
                              for a in nw.get("articles", [])], ensure_ascii=False))
except Exception as x:
    print("Noticias ESPN falharam:", x)

# esquecer jogos com mais de 2 dias
estado = {k: v for k, v in estado.items() if k in {e["id"] for e in ev.json()} or len(v) < 2}
ESTADO.write_text(json.dumps(estado))
print(f"{recolhido}: {len(linhas)} linhas. Pedidos restantes: {restantes}")
