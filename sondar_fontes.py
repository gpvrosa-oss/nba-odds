"""Teste: que sites de estatisticas avancadas gratis o GitHub consegue ler (1 pedido a cada um)."""
import requests

H = {"User-Agent": "nba-odds-research/1.0 (personal project)", "Accept": "application/json, text/html"}
T = {
    "basketball-reference": "https://www.basketball-reference.com/leagues/NBA_2026.html",
    "pbpstats-api": "https://api.pbpstats.com/get-totals/nba?Season=2025-26&SeasonType=Regular%2BSeason&Type=Team",
    "nba-stats": "https://stats.nba.com/stats/leaguedashteamstats?Season=2025-26&SeasonType=Regular%20Season&MeasureType=Advanced&PerMode=PerGame",
    "dunksandthrees": "https://dunksandthrees.com/epm",
    "craftednba": "https://craftednba.com/player-traits",
    "cleaningtheglass": "https://cleaningtheglass.com/stats/league/summary",
    "espn-summary": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909922",
}
for k, u in T.items():
    try:
        r = requests.get(u, headers=H, timeout=25)
        extra = ""
        if k == "espn-summary" and r.ok:
            j = r.json()
            pl = j.get("plays", [])
            extra = f"plays={len(pl)} exemplo={str(pl[5])[:250] if len(pl) > 5 else ''}"
            b = j.get("boxscore", {}).get("players", [{}])[0].get("statistics", [{}])[0]
            a = (b.get("athletes") or [{}])[0].get("athlete", {})
            extra += f" | posicao={a.get('position')}"
        if k == "pbpstats-api" and r.ok:
            extra = str(r.json())[:300]
        print(f"{k:22s} {r.status_code} {len(r.content):>8} {extra}")
    except Exception as e:
        print(f"{k:22s} ERRO {type(e).__name__} {str(e)[:100]}")
