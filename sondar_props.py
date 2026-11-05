"""Teste unico: que mercados de jogadores (props) existem e em que casas. Gasta ~4 pedidos. Nao guarda nada."""
import os, requests
API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
KEY = os.environ["ODDS_API_KEY"]
ev = requests.get(f"{API}/events", params={"apiKey": KEY}, timeout=30).json()
e = ev[0]
print("Jogo:", e["home_team"], "vs", e["away_team"], e["commence_time"])
m = requests.get(f"{API}/events/{e['id']}/markets", params={"apiKey": KEY, "regions": "us,eu,uk"}, timeout=30)
print("markets custo", m.headers.get("x-requests-last"), "restantes", m.headers.get("x-requests-remaining"))
for b in m.json().get("bookmakers", []):
    print(" ", b["key"], ",".join(sorted(x["key"] for x in b["markets"] if x["key"].startswith("player"))))
o = requests.get(f"{API}/events/{e['id']}/odds", params={"apiKey": KEY, "regions": "eu,uk",
                 "markets": "player_points", "oddsFormat": "decimal"}, timeout=30)
print("odds eu,uk custo", o.headers.get("x-requests-last"), "restantes", o.headers.get("x-requests-remaining"))
for b in o.json().get("bookmakers", []):
    for mk in b["markets"]:
        print(" ", b["key"], mk["key"], len(mk["outcomes"]), "linhas; ex:", mk["outcomes"][:2])
