"""Proximo jogo de uma equipa (ESPN) e lesoes atuais. Uso: python proximo_jogo.py GS"""
import json, sys, requests
from datetime import datetime, timezone
from pathlib import Path
eq = sys.argv[1] if len(sys.argv) > 1 else "GS"
B = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
times = requests.get(f"{B}/teams", timeout=30).json()["sports"][0]["leagues"][0]["teams"]
tid = next(t["team"]["id"] for t in times if t["team"]["abbreviation"] == eq)
sch = requests.get(f"{B}/teams/{tid}/schedule", timeout=30).json()
agora = datetime.now(timezone.utc)
for e in sch.get("events", []):
    d = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
    if d > agora:
        c = e["competitions"][0]["competitors"]
        print("PROXIMO:", e["date"], " | ".join(f'{x["team"]["abbreviation"]}({x["homeAway"]})' for x in c))
        break
Path("props/lesoes").mkdir(parents=True, exist_ok=True)
Path(f"props/lesoes/{agora:%Y-%m-%dT%H%MZ}.json").write_text(requests.get(f"{B}/injuries", timeout=30).text)
