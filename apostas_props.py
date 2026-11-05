"""Apostas virtuais em props (sem dinheiro real) e a sua avaliacao.

1. Para cada linha "cedo" da Pinnacle ainda nao vista: o modelo calcula os pontos previstos com as
   lesoes da ESPN DESSE momento, e decide over / under / passar.  -> props/avaliadas.csv, props/apostas.csv
2. Para as apostas cujo jogo ja acabou: resultado (anulada se o jogador nao jogou) e CLV contra a linha
   de fecho da Pinnacle.  -> props/apostas.csv e props/RESUMO_PROPS.md
"""
import json, glob
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import modelo_props as M

PASTA = Path("props")
BANCA = 100.0           # unidades virtuais
VALOR_MIN = 0.03        # EV minimo depois de misturar modelo e mercado
PESO_MODELO = 0.5       # a Pinnacle e afiada: confiamos metade nela
DISCORDANCIA_MAX = 0.20
FRACAO_KELLY = 0.25
STAKE_MAX = 0.01        # no maximo 1% da banca por aposta
MIN_JOGOS = 10
FALTAR_MAX = 0.25       # salta jogadores com duvidas de jogar
PROB_FALTAR = {"out": 1.0, "doubtful": 0.75, "questionable": 0.4, "day-to-day": 0.3, "probable": 0.1}

def ler_linhas():
    fs = sorted(glob.glob(str(PASTA / "20*.csv")))
    if not fs:
        return pd.DataFrame()
    L = pd.concat([pd.read_csv(f, dtype={"jogo_id": str}) for f in fs], ignore_index=True)
    L = L[L.casa_apostas == "pinnacle"]
    p = L.pivot_table(index=["recolhido_em", "momento", "jogo_id", "inicio_jogo", "casa", "fora", "mercado", "jogador", "linha"],
                      columns="lado", values="odd", aggfunc="last").reset_index()
    p = p.dropna(subset=["Over", "Under"])
    p["p_justa"] = (1 / p.Over) / (1 / p.Over + 1 / p.Under)
    return p

def lesoes_em(momento):
    t = datetime.strptime(momento, "%Y-%m-%dT%H:%M:%SZ")
    best = None
    for f in sorted((PASTA / "lesoes").glob("*.json")):
        ft = datetime.strptime(f.stem, "%Y-%m-%dT%H%MZ")
        if ft <= t + timedelta(minutes=10):
            best = f
    out = {}
    if best is None:
        return out
    for eq in json.loads(best.read_text()).get("injuries", []):
        for i in eq.get("injuries", []):
            est = i.get("status", "").lower()
            txt = (i.get("shortComment", "") + " " + i.get("longComment", "")).lower()
            p = PROB_FALTAR.get(est, 0.5)
            if est != "out" and ("game-time decision" in txt or "game time decision" in txt):
                p = 0.5
            out[M.nome_chave(i["athlete"]["displayName"])] = p
    return out

def novas_apostas(L, H):
    fa, fb = PASTA / "avaliadas.csv", PASTA / "apostas.csv"
    vistos = set(pd.read_csv(fa, dtype={"jogo_id": str})["chave"]) if fa.exists() else set()
    C = L[L.momento == "cedo"].copy()
    C["chave"] = C.jogo_id + "|" + C.mercado + "|" + C.jogador
    C = C[~C.chave.isin(vistos)]
    if C.empty:
        return
    aval, apostas = [], []
    for mercado, Cm in C.groupby("mercado"):
        s = M.STATS.get(mercado)
        if s is None:
            continue
        Hs = H[H.data < pd.to_datetime(Cm.inicio_jogo.min()).tz_localize(None).normalize()]
        par = M.treinar(Hs, s)
        E, norma, adv = M.estado_atual(Hs, s)
        E["chave_nome"] = E.nome.map(M.nome_chave)
        for (jid, rec), G in Cm.groupby(["jogo_id", "recolhido_em"]):
            les = lesoes_em(rec)
            pf = {pid: les.get(k, 0.0) for pid, k in E.chave_nome.items()}
            casa, fora = M.EQUIPAS.get(G.casa.iloc[0]), M.EQUIPAS.get(G.fora.iloc[0])
            R = pd.concat([M.prever(E, norma, adv, par, casa, fora, 1, pf),
                           M.prever(E, norma, adv, par, fora, casa, 0, pf)])
            R["chave_nome"] = R.nome.map(M.nome_chave)
            for row in G.itertuples():
                k = M.nome_chave(row.jogador)
                m = R[R.chave_nome == k]
                base = dict(chave=row.chave, recolhido_em=rec, jogo_id=jid, inicio_jogo=row.inicio_jogo, mercado=mercado,
                            jogador=row.jogador, linha=row.linha, odd_over=row.Over, odd_under=row.Under, p_justa=round(row.p_justa, 4))
                if m.empty:
                    aval.append({**base, "nota": "jogador nao encontrado"}); continue
                j = m.iloc[0]; prob_f = 1 - j.disp
                p = float(M.p_over([j.mu], [row.linha], par["r"], par["a"], par["b"])[0])
                pm = PESO_MODELO * p + (1 - PESO_MODELO) * row.p_justa
                ev_o, ev_u = pm * row.Over - 1, (1 - pm) * row.Under - 1
                lado, ev, odd, pl = ("Over", ev_o, row.Over, pm) if ev_o > ev_u else ("Under", ev_u, row.Under, 1 - pm)
                nota = ""
                if E.loc[j.name, "n"] < MIN_JOGOS: nota = "poucos jogos"
                elif prob_f > FALTAR_MAX: nota = "duvida se joga"
                elif abs(p - row.p_justa) > DISCORDANCIA_MAX: nota = "discorda demais do mercado"
                elif ev <= VALOR_MIN: nota = "sem valor"
                aval.append({**base, "previsto": round(j.mu, 2), "minutos": round(j.m_proj, 1), "p_modelo": round(p, 4),
                             "falta_equipa": round(j.falta_equipa, 3), "nota": nota or "APOSTA"})
                if not nota:
                    stake = round(min(FRACAO_KELLY * (pl * odd - 1) / (odd - 1), STAKE_MAX) * BANCA, 2)
                    apostas.append({**base, "lado": lado, "odd": odd, "previsto": round(j.mu, 2), "p_modelo": round(p, 4),
                                    "ev": round(ev, 4), "stake": stake})
    for f, rows in ((fa, aval), (fb, apostas)):
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(f, mode="a", header=not f.exists(), index=False)
    print(f"Linhas avaliadas: {len(aval)}, apostas novas: {len(apostas)}")

R_TIPICO = {"pts": 3, "reb": 8, "ast": 12}

def prob_na_linha(p_over_fecho, linha_fecho, linha, s):
    """Probabilidade justa de 'over' na NOSSA linha, deduzida da linha de fecho (se a linha mudou)."""
    if linha == linha_fecho:
        return p_over_fecho
    r, lo, hi = R_TIPICO[s], 0.1, 80.0
    for _ in range(60):                       # media que da P(over linha_fecho) = p_over_fecho
        mu = (lo + hi) / 2
        if M.p_over([mu], [linha_fecho], r)[0] < p_over_fecho: lo = mu
        else: hi = mu
    return float(M.p_over([mu], [linha], r)[0])

def avaliar(L, H):
    fb = PASTA / "apostas.csv"
    if not fb.exists():
        return
    A = pd.read_csv(fb, dtype={"jogo_id": str})
    for c in ["resultado", "real", "lucro", "linha_fecho", "clv"]:
        if c not in A:
            A[c] = np.nan
    A["resultado"] = A["resultado"].astype(object)
    F = L[L.momento == "fecho"]
    H = H.assign(k=H.nome.map(M.nome_chave), d=H.data.dt.date)
    for i, a in A[A.resultado.isna()].iterrows():
        dia = (pd.to_datetime(a.inicio_jogo) - pd.Timedelta(hours=6)).date()
        if pd.Timestamp(dia) >= H.data.max() + pd.Timedelta(days=1):
            continue                                    # ainda nao ha resultados desse dia
        s = M.STATS[a.mercado]
        h = H[(H.k == M.nome_chave(a.jogador)) & (H.d == dia)]
        f = F[(F.jogo_id == a.jogo_id) & (F.mercado == a.mercado) & (F.jogador == a.jogador)]
        if not f.empty:
            f = f.iloc[-1]; A.at[i, "linha_fecho"] = f.linha
            po = prob_na_linha(f.p_justa, f.linha, a.linha, s)
            pj = po if a.lado == "Over" else 1 - po
            A.at[i, "clv"] = round(a.odd * pj - 1, 4)
        if h.empty:
            A.at[i, "resultado"] = "anulada"; A.at[i, "lucro"] = 0.0; continue
        real = float(h[s].iloc[0]); A.at[i, "real"] = real
        ganhou = real > a.linha if a.lado == "Over" else real < a.linha
        A.at[i, "resultado"] = "ganhou" if ganhou else "perdeu"
        A.at[i, "lucro"] = round(a.stake * (a.odd - 1) if ganhou else -a.stake, 2)
    A.to_csv(fb, index=False)
    D = A[A.resultado.isin(["ganhou", "perdeu"])]
    linhas = ["# Apostas virtuais em props (sem dinheiro real)", "",
              f"Atualizado: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Casa de referencia: Pinnacle (linha ~3h antes do jogo).", ""]
    if len(D):
        linhas += [f"- Apostas decididas: **{len(D)}** (ganhas {(D.resultado == 'ganhou').mean():.0%}), anuladas: {(A.resultado == 'anulada').sum()}, por decidir: {A.resultado.isna().sum()}",
                   f"- Apostado: {D.stake.sum():.1f} unidades. Lucro: **{D.lucro.sum():+.1f} unidades** (ROI {D.lucro.sum() / D.stake.sum():+.1%})",
                   (f"- CLV medio (bater a linha de fecho; o melhor sinal de qualidade): **{A.clv.mean():+.1%}** em {A.clv.notna().sum()} apostas" if A.clv.notna().any() else "- CLV: ainda sem linhas de fecho"),
                   "", "Regra de bolso: so pensar em dinheiro real com 200+ apostas e CLV medio acima de +2%.", ""]
        ult = A.tail(15)[["inicio_jogo", "jogador", "lado", "linha", "odd", "previsto", "stake", "resultado", "real", "lucro", "clv"]]
        linhas += ["## Ultimas apostas", "", "```", ult.to_string(index=False), "```"]
    else:
        linhas += [f"Ainda sem apostas decididas. Por decidir: {A.resultado.isna().sum()}."]
    (PASTA / "RESUMO_PROPS.md").write_text("\n".join(linhas), encoding="utf-8")

if __name__ == "__main__":
    if not Path("dados/jogadores.csv").exists():
        print("Ainda nao ha historico (dados/jogadores.csv)."); raise SystemExit
    L = ler_linhas()
    if L.empty:
        print("Ainda nao ha linhas de props."); raise SystemExit
    H = M.carregar()
    novas_apostas(L, H)
    avaliar(L, H)
