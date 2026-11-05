"""Teste: o GitHub consegue ler resultados e estatisticas de jogadores da ESPN? Nao gasta pedidos."""
import requests
B = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
s = requests.get(f"{B}/scoreboard", params={"dates": "20261104"}, timeout=30)
print("scoreboard", s.status_code, len(s.content))
ev = s.json().get("events", [])
print("jogos", len(ev))
if ev:
    gid = ev[0]["id"]; print("exemplo", ev[0]["name"], gid)
    b = requests.get(f"{B}/summary", params={"event": gid}, timeout=30); print("summary", b.status_code)
    bs = b.json().get("boxscore", {}).get("players", [])
    for t in bs[:1]:
        st = t["statistics"][0]; print(t["team"]["abbreviation"], st["labels"])
        for a in st["athletes"][:3]: print(" ", a["athlete"]["displayName"], a["athlete"]["id"], a["stats"])
r = requests.get(f"{B}/injuries", timeout=30); print("injuries", r.status_code, len(r.content))
