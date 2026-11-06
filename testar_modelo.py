"""Teste fixo do modelo de pontos: corre-se depois de QUALQUER mudanca ao modelo.
Treina so com jogos antes de 2025-10-01 e avalia a epoca 2025-26 em diante como se fosse ao vivo.
Compara com props/teste_referencia.json e diz se a mudanca melhorou ou piorou.
  python testar_modelo.py            -> mostra resultados e compara
  python testar_modelo.py --guardar  -> grava estes resultados como nova referencia
"""
import json, sys
from pathlib import Path
import numpy as np
import modelo_props as M

REF = Path("props/teste_referencia.json")
H = M.carregar("dados/jogadores_v2.csv"); s = "pts"
par = M.treinar(H[H.data < "2025-10-01"], s)
D = M.caracteristicas(H, s); H = H.reset_index(drop=True); D = D.reset_index(drop=True)
mu = np.exp(np.log((D.m_live * D.taxa).clip(0.05)) + M._X(D, par["usg_media"]) @ np.array(par["coef"]))
te = ((H.data >= "2025-10-01") & (D.n >= 10) & (H["min"] > 0)).values
m, y = mu[te], H[s].values[te]
rel = (mu > 12)[te]
r = {"jogos": int(te.sum()), "erro_medio": float(np.abs(y - m).mean()),
     "erro_medio_titulares": float(np.abs(y - m)[rel].mean()),
     "vies": float((m - y).mean()), "vies_estrelas": float((m - y)[m > 24].mean())}
cal = []
for o in (-4.5, -2.5, -0.5, 0.5, 2.5, 4.5):
    L = np.floor(m[rel]) + o
    p = M.p_over(m[rel], L, par["r"], par["a"], par["b"])
    cal.append(abs(p.mean() - (y[rel] > L).mean()))
r["erro_calibracao"] = float(np.mean(cal))
p = M.p_over(m[rel], np.floor(m[rel]) + 0.5, par["r"], par["a"], par["b"]).clip(1e-4, 1 - 1e-4)
h = (y[rel] > np.floor(m[rel]) + 0.5)
r["log_loss_linha"] = float(-np.mean(h * np.log(p) + (1 - h) * np.log(1 - p)))
ref = json.loads(REF.read_text()) if REF.exists() else {}
melhor_se_menor = ["erro_medio", "erro_medio_titulares", "erro_calibracao", "log_loss_linha"]
for k, v in r.items():
    extra = ""
    if k in ref and k != "jogos":
        d = v - ref[k]
        if k in melhor_se_menor:
            extra = f"  ({d:+.4f} {'MELHOR' if d < -1e-4 else 'PIOR' if d > 1e-4 else 'igual'})"
        else:
            extra = f"  (antes {ref[k]:+.3f})"
    print(f"{k:22s} {v:.4f}{extra}")
if "--guardar" in sys.argv:
    REF.write_text(json.dumps(r, indent=1)); print("referencia gravada")
