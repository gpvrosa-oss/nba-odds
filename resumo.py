"""Escreve RESUMO.md: as odds mais recentes de cada jogo, numa tabela facil de ler no GitHub."""
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ficheiros = sorted(Path("odds").glob("*.csv"))[-2:]
df = pd.concat(pd.read_csv(f) for f in ficheiros)
df = df[(df["mercado"] == "h2h") & (df["inicio_jogo"] > datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))]
df = df[df["recolhido_em"] == df.groupby("jogo_id")["recolhido_em"].transform("max")]
bolsas = {"betfair_ex_eu", "betfair_ex_uk", "matchbook", "smarkets"}

linhas = ["# Odds NBA (vencedor do jogo)", "",
          f"Atualizado: {datetime.now(ZoneInfo('Europe/Lisbon')):%d/%m %H:%M} (hora de Lisboa). "
          "Odd tipica = mediana das casas de apostas; melhor = a mais alta (sem bolsas de apostas).", ""]
if df.empty:
    linhas.append("Nao ha jogos com odds de momento.")
else:
    linhas += ["| Inicio (Lisboa) | Jogo | Fora: tipica / melhor | Casa: tipica / melhor | Casas |",
               "|---|---|---|---|---|"]
    for jid, g in sorted(df.groupby("jogo_id"), key=lambda x: x[1]["inicio_jogo"].iloc[0]):
        casa, fora = g["casa"].iloc[0], g["fora"].iloc[0]
        inicio = pd.Timestamp(g["inicio_jogo"].iloc[0]).tz_convert("Europe/Lisbon")
        cel = []
        for eq in (fora, casa):
            o = g[(g["resultado"] == eq) & ~g["casa_apostas"].isin(bolsas)]
            if o.empty:
                cel.append("-")
                continue
            m = o.loc[o["odd"].idxmax()]
            cel.append(f"{o['odd'].median():.2f} / {m['odd']:.2f} ({m['casa_apostas']})")
        linhas.append(f"| {inicio:%d/%m %H:%M} | {fora} @ {casa} | {cel[0]} | {cel[1]} | {g['casa_apostas'].nunique()} |")
Path("RESUMO.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
print("RESUMO.md atualizado")
