"""Mantem dados/jogadores.csv com as estatisticas de cada jogador em cada jogo (fonte: ESPN, gratis).

  python historico.py                 -> acrescenta os dias que faltam ate ontem
  python historico.py 2024-10-22      -> (re)comeca a partir desta data (primeira vez)
Corre no GitHub Actions; nao precisa do PC.
"""
import csv, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

B = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
F = Path("dados") / "jogadores.csv"
COL = ["data", "jogo_id", "tipo", "equipa", "adversario", "casa", "jogador_id", "nome", "titular",
       "min", "pts", "reb", "ast", "fg3"]
F.parent.mkdir(exist_ok=True)
s = requests.Session()

def get(url, **p):
    for i in range(4):
        try:
            r = s.get(url, params=p, timeout=30)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None

feitos = set()
if F.exists():
    with F.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            feitos.add(row["jogo_id"])
if len(sys.argv) > 1:
    d = date.fromisoformat(sys.argv[1])
elif F.exists() and feitos:
    with F.open(encoding="utf-8") as f:
        d = max(date.fromisoformat(r["data"]) for r in csv.DictReader(f)) - timedelta(days=2)
else:
    d = date(2024, 10, 22)
ontem = (datetime.now(timezone.utc) - timedelta(hours=5)).date()   # dia de hoje nos EUA (so guarda jogos acabados)

novo = not F.exists()
out = F.open("a", newline="", encoding="utf-8"); w = csv.writer(out)
if novo:
    w.writerow(COL)
n_jogos = 0
while d <= ontem:
    sb = get(f"{B}/scoreboard", dates=d.strftime("%Y%m%d"), limit=50) or {}
    for e in sb.get("events", []):
        tipo = e.get("season", {}).get("type")          # 2 = epoca regular, 3 = playoffs, 5 = play-in
        if tipo not in (2, 3, 5) or e["id"] in feitos or not e.get("status", {}).get("type", {}).get("completed"):
            continue
        comp = e["competitions"][0]["competitors"]
        lado = {c["team"]["abbreviation"]: c["homeAway"] for c in comp}
        sm = get(f"{B}/summary", event=e["id"])
        if not sm:
            continue
        linhas = []
        for t in sm.get("boxscore", {}).get("players", []):
            ab = t["team"]["abbreviation"]; adv = [x for x in lado if x != ab]
            st = t["statistics"][0]; L = st["labels"]
            for a in st["athletes"]:
                v = a.get("stats") or []
                if not v or a.get("didNotPlay"):
                    continue
                x = dict(zip(L, v))
                try:
                    mins = float(x.get("MIN", "0") or 0)
                except ValueError:
                    mins = 0.0
                if mins <= 0:
                    continue
                linhas.append([d.isoformat(), e["id"], tipo, ab, adv[0] if adv else "", int(lado.get(ab) == "home"),
                               a["athlete"]["id"], a["athlete"]["displayName"], int(bool(a.get("starter"))),
                               mins, x.get("PTS", 0), x.get("REB", 0), x.get("AST", 0),
                               (x.get("3PT", "0-0") or "0-0").split("-")[0]])
        if linhas:
            w.writerows(linhas); feitos.add(e["id"]); n_jogos += 1
    d += timedelta(days=1)
    time.sleep(0.2)
out.close()
print(f"Jogos novos: {n_jogos}. Total no ficheiro: {len(feitos)}")
