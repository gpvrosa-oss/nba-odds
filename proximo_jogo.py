"""Proximo jogo de uma equipa (ESPN) e lesoes atuais. Uso: python proximo_jogo.py GS"""
import json, sys, requests
from datetime import datetime, timezone
from pathlib import Path
eq = sys.argv[1] if len(sys.argv) > 1 else "GS"
B = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
from datetime import timedelta
agora = datetime.now(timezone.utc)
achou = False
for i in range(0, 10):
    dia = (agora + timedelta(days=i)).strftime("%Y%m%d")
    for e in requests.get(f"{B}/scoreboard", params={"dates": dia}, timeout=30).json().get("events", []):
        c = e["competitions"][0]["competitors"]
        abs_ = [x["team"]["abbreviation"] for x in c]
        if eq in abs_ and not e["status"]["type"]["completed"]:
            print("PROXIMO:", e["date"], " | ".join(f'{x["team"]["abbreviation"]}({x["homeAway"]})' for x in c))
            achou = True; break
    if achou:
        break
Path("props/lesoes").mkdir(parents=True, exist_ok=True)
Path(f"props/lesoes/{agora:%Y-%m-%dT%H%MZ}.json").write_text(requests.get(f"{B}/injuries", timeout=30).text)
