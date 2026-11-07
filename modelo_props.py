"""Modelo de props (pontos, ressaltos, assistencias) a partir de dados/jogadores.csv.

Ideia: pontos previstos = minutos previstos x pontos por minuto do jogador
  - minutos: media recente (com mais peso aos ultimos jogos), x participacao nos ultimos 10 jogos,
    x probabilidade de jogar (lesoes ESPN), e reajustados para a equipa somar 240 minutos;
  - quando faltam colegas, os que jogam ganham parte dos lancamentos (coeficiente "falta");
  - adversario: quanto concede face a media da liga.
A distribuicao e uma binomial negativa (os pontos variam mais do que uma Poisson) e a probabilidade
final e recalibrada com os dados da epoca anterior.
Testado na epoca 2025-26 (dados nba_api): erro medio 4,6 pontos vs 4,7 da media dos ultimos 10 jogos.
"""
import math, unicodedata, re
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

HL = 12            # meia-vida em jogos para as medias do jogador
K_PRIOR = 60       # minutos "imaginarios" com a media da liga (para jogadores com poucos jogos)
STATS = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast"}

def nome_chave(n):
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z ]", " ", n)
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", n)
    return " ".join(n.split())

EQUIPAS = {"Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
           "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
           "Detroit Pistons": "DET", "Golden State Warriors": "GS", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
           "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
           "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NO",
           "New York Knicks": "NY", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
           "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
           "Sacramento Kings": "SAC", "San Antonio Spurs": "SA", "Toronto Raptors": "TOR", "Utah Jazz": "UTAH",
           "Washington Wizards": "WSH"}

def carregar(f="dados/jogadores_v2.csv"):
    import os
    if not os.path.exists(f) and os.path.exists("dados/jogadores.csv"):
        f = "dados/jogadores.csv"                       # versao antiga, enquanto a v2 nao existe
    H = pd.read_csv(f, dtype={"jogo_id": str, "jogador_id": str})
    H["data"] = pd.to_datetime(H["data"])
    for c in ["fga", "fta", "tov"]:
        if c not in H:
            H[c] = 0
    for c in ["min", "pts", "reb", "ast", "fga", "fta", "tov"]:
        H[c] = pd.to_numeric(H[c], errors="coerce").fillna(0)
    nba = set(EQUIPAS.values())                      # tira o jogo das estrelas e outros jogos de exibicao
    H = H[H.equipa.isin(nba) & H.adversario.isin(nba)]
    H = H[H["min"] > 0].sort_values(["data", "jogo_id"]).reset_index(drop=True)
    return H

PESO_EPOCA = 0.4    # jogos de epocas anteriores contam 40%
PESO_EQUIPA = 0.3   # jogos por outra equipa contam 30% (trocas). Teste 2025-26: erro -0.6% em geral,
                    # -1.3% nas primeiras semanas da epoca e -3.6% em jogadores que mudaram de equipa

def _epoca(datas):
    return np.where(datas.dt.month >= 8, datas.dt.year, datas.dt.year - 1)

def _ew_contexto(H, cols, shift=True):
    """Media exponencial (meia-vida HL jogos) em que cada jogo antigo pesa menos se for de outra epoca ou
    de outra equipa, relativamente ao jogo atual. shift=True: estado ANTES de cada jogo."""
    Hr = H.reset_index(drop=True)
    o = Hr.sort_values(["jogador_id", "data"], kind="stable").index.values
    G = pd.DataFrame({"p": Hr.jogador_id.values[o], "e": _epoca(Hr.data)[o], "t": Hr.equipa.values[o]})
    j = G.groupby("p").cumcount().values.astype(float)
    sc = (0.5 ** (1 / HL)) ** (-j)
    a, b = PESO_EQUIPA, PESO_EPOCA
    def soma(x):
        G["x"] = x * sc
        S = {}
        for nm, keys in (("all", ["p"]), ("e", ["p", "e"]), ("t", ["p", "t"]), ("et", ["p", "e", "t"])):
            cs = G.groupby(keys)["x"].cumsum().values
            S[nm] = cs - G["x"].values if shift else cs
        return S["et"] + a * (S["t"] - S["et"]) + b * (S["e"] - S["et"]) + a * b * (S["all"] - S["e"] - S["t"] + S["et"])
    den = soma(np.ones(len(o)))
    den = np.where(den > 0, den, np.nan)
    out = {}
    for c in cols:
        v = np.empty(len(o)); v[o] = soma(Hr[c].astype(float).values[o]) / den
        out[c] = pd.Series(v, index=H.index)
    return out

def _ew(x, shift):
    x = x.shift() if shift else x
    return x.ewm(halflife=HL).mean()

def caracteristicas(H, s, shift=True):
    """Para cada linha de H: estado do jogador ANTES do jogo (shift=True) -> usado para treinar."""
    g = H.groupby("jogador_id")
    D = pd.DataFrame(index=H.index)
    D["n"] = g.cumcount()
    W = _ew_contexto(H, ["min", s, "fga", "fta", "tov"], shift)
    D["m_ew"] = W["min"]
    lg = H[s].sum() / H["min"].sum()
    taxa = W[s] / D.m_ew
    w = np.minimum(D.n, 2 * HL) * D.m_ew.fillna(0)
    D["taxa"] = (taxa.fillna(0) * w + lg * K_PRIOR) / (w + K_PRIOR)
    D["m0"] = D.m_ew.fillna(12.0)
    chave = [H.jogo_id, H.equipa]
    D["m_proj"] = (D.m0 * 240 / D.groupby(chave).m0.transform("sum")).clip(upper=42)
    D["prod"] = D.taxa * D.m0
    dia = D.groupby(chave)["prod"].transform("sum")
    td = pd.DataFrame({"jogo_id": H.jogo_id, "equipa": H.equipa, "data": H.data, "dia": dia}).drop_duplicates(["jogo_id", "equipa"]).sort_values("data")
    td["norma"] = td.groupby("equipa")["dia"].transform(lambda x: x.shift().ewm(halflife=10).mean())
    D["falta"] = (1 - dia / H[["jogo_id", "equipa"]].merge(td, on=["jogo_id", "equipa"], how="left")["norma"].values).clip(-0.3, 0.6).fillna(0)
    D["adv"] = fator_adversario(H, s).reindex(list(zip(H.jogo_id, H.adversario))).values
    D["adv"] = D.adv.fillna(1.0)
    D["casa"] = H.casa.values
    # "usage": quanto do ataque passa pelo jogador (lancamentos + lances livres + perdas de bola por minuto)
    u = sum(W[c] * k for c, k in (("fga", 1), ("fta", 0.44), ("tov", 1)))
    D["usg"] = (u / D.m0.clip(lower=1)).fillna(0)
    # tendencia de minutos: media dos ultimos 3 jogos vs media habitual (apanha jogadores a perder/ganhar
    # espaco na rotacao; no teste 2025-26 reduziu o erro ~1.5% e tirou o vies nos que estao a perder minutos)
    l3 = g["min"].transform(lambda x: (x.shift() if shift else x).rolling(3, min_periods=2).mean())
    D["tend"] = np.log((l3 / D.m0).clip(0.4, 2.5)).fillna(0)
    D["m_live"] = D.m0.clip(upper=42)
    D["estrela"] = _estrela(H, D.taxa, D.n, s)
    sup = fator_estrelas(H, s, D.taxa * H["min"].clip(lower=0), D.estrela, D.n)
    D["sup"] = sup.reindex(list(zip(H.jogo_id, H.adversario))).fillna(0).values
    return D

def _estrela(H, taxa, n, s):
    """Base de pontos (G) com >= 0.72 pontos por minuto: os jogadores que as defesas tentam tirar do jogo."""
    if s != "pts":
        return pd.Series(0, index=H.index)
    return ((taxa >= 0.72) & (n >= 10) & (H.pos.fillna("").str[-1] == "G")).astype(int)

def fator_estrelas(H, s, esperado, estrela, n, final=False, K=120):
    """Quanto cada defesa trava as estrelas (bases) face ao que concede aos outros, em log.
    Aproxima defesas que fazem blitz/dobras (ex.: Kings, Hornets) vs as que defendem 1x1 (ex.: Wolves).
    Teste 2025-26: erro -0.5% nas estrelas (coef ~0.3); a historia jogador-vs-equipa nao ajudou."""
    ok = (n >= 10).values
    A = pd.DataFrame({"jogo_id": H.jogo_id, "data": H.data, "adversario": H.adversario, "st": estrela.values,
                      "p": H[s].values, "e": np.asarray(esperado)})[ok]
    A = A.groupby(["jogo_id", "data", "adversario", "st"])[["p", "e"]].sum().unstack("st", fill_value=0)
    A.columns = [f"{a}{b}" for a, b in A.columns]
    for c in ["p0", "e0", "p1", "e1"]:
        if c not in A:
            A[c] = 0.0
    A = A.reset_index().sort_values("data")
    g = A.groupby("adversario")
    if final:
        c = g[["p0", "e0", "p1", "e1"]].sum()
        return np.log(((c.p1 + K) / (c.e1 + K)) / ((c.p0 + 4 * K) / (c.e0 + 4 * K)))
    c = {k: g[k].transform(lambda x: x.shift().fillna(0).cumsum()) for k in ["p0", "e0", "p1", "e1"]}
    A["sup"] = np.log(((c["p1"] + K) / (c["e1"] + K)) / ((c["p0"] + 4 * K) / (c["e0"] + 4 * K)))
    return A.set_index(["jogo_id", "adversario"])["sup"]

def fator_adversario(H, s, final=False):
    ta = H.groupby(["jogo_id", "adversario", "data"])[s].sum().reset_index().sort_values("data")
    media = ta[s].mean()
    if final:
        return ta.groupby("adversario")[s].apply(lambda x: x.ewm(halflife=15).mean().iloc[-1]) / media
    ta["f"] = ta.groupby("adversario")[s].transform(lambda x: x.shift().ewm(halflife=15).mean()) / media
    return ta.set_index(["jogo_id", "adversario"])["f"]

def _X(D, usg_media):
    # testado em 2025-26: so "colegas em falta x usage" melhorou; ritmo, perfil de lancamento vs defesa,
    # defesa por posicao, cansaco (back-to-back, 3 em 4) e risco de goleada nao ajudaram (ficaram de fora)
    ur = (D.usg / usg_media) if usg_media > 0 else 1.0
    return np.c_[np.ones(len(D)), D.falta, np.log(D.adv.clip(0.5, 2)), D.casa, D.falta * ur, D.tend, D.estrela * D.sup]

def _nb_cdf(mu, r, K=90):
    """Binomial negativa; r pode ser um valor por linha."""
    mu = np.asarray(mu, float); r = np.broadcast_to(np.asarray(r, float), mu.shape)
    k = np.arange(K)[None, :]
    lg = np.vectorize(math.lgamma)
    lp = lg(k + r[:, None]) - lg(r)[:, None] - lg(k + 1) \
        + r[:, None] * np.log(r[:, None] / (r[:, None] + mu[:, None])) + k * np.log(mu[:, None] / (r[:, None] + mu[:, None]))
    return np.cumsum(np.exp(lp), axis=1)

def p_over(mu, linha, phi, a=1.0, b=0.0):
    """P(estatistica > linha). phi = variancia / media (os pontos variam ~3x a media; ressaltos ~1.5x)."""
    mu = np.asarray(mu, float).clip(0.05); linha = np.asarray(linha, float)
    r = mu / max(phi - 1, 0.05)
    k = np.floor(linha).astype(int).clip(0, 89)
    p = 1 - _nb_cdf(mu, r)[np.arange(len(mu)), k]
    p = p.clip(1e-4, 1 - 1e-4)
    z = a * np.log(p / (1 - p)) + b
    return 1 / (1 + np.exp(-z))

def treinar(H, s):
    """Ajusta os coeficientes com o historico (cada jogo usando so o que se sabia antes)."""
    D = caracteristicas(H, s)
    ok = (D.n >= 5).values
    usg_media = float(D.usg[ok].mean())
    y = H[s].values[ok]; X = _X(D, usg_media)[ok]; off = np.log((D.m_live * D.taxa).clip(0.05)).values[ok]   # minutos como ao vivo
    w = np.zeros(X.shape[1])
    for _ in range(30):
        mu = np.exp(off + X @ w)
        w += np.linalg.solve((X * mu[:, None]).T @ X + 1e-6 * np.eye(X.shape[1]), X.T @ (y - mu))
    mu = np.exp(off + X @ w)
    # dispersao (phi) e pequeno ajuste (b) escolhidos com linhas perto da previsao, nos jogadores com papel
    # relevante (os que tem linhas nas casas de apostas)
    lim = {"pts": 12, "reb": 4, "ast": 3}.get(s, 3)
    m = mu > lim
    mm, yy = mu[m][-30000:], y[m][-30000:]
    linhas = np.concatenate([np.floor(mm) + o for o in (-2.5, -0.5, 0.5, 2.5)])
    mu4, h = np.tile(mm, 4), (np.tile(yy, 4) > linhas).astype(float)
    def perda(phi, b=0.0):
        p = p_over(mu4, linhas, phi, 1.0, b)
        return -np.mean(h * np.log(p) + (1 - h) * np.log(1 - p))
    r = min([1.1, 1.2, 1.3, 1.45, 1.6, 1.8, 2.0, 2.3, 2.6, 2.9, 3.2, 3.6, 4.0], key=perda)
    a, b = 1.0, min(np.arange(-0.3, 0.31, 0.02), key=lambda bb: perda(r, bb))
    return {"coef": w.tolist(), "r": r, "a": float(a), "b": float(b), "usg_media": usg_media}

def estado_atual(H, s):
    """Estado de cada jogador depois do ultimo jogo (para prever o proximo)."""
    g = H.groupby("jogador_id")
    lg = H[s].sum() / H["min"].sum()
    W = _ew_contexto(H, ["min", s, "fga", "fta", "tov"], shift=False)
    ult = H.assign(_i=np.arange(len(H))).sort_values("data", kind="stable").groupby("jogador_id")["_i"].last()
    pega = lambda c: pd.Series(W[c].values[ult.values], index=ult.index)
    E = pd.DataFrame({"m_ew": pega("min"), "s_ew": pega(s),
                      "n": g.size(), "equipa": g["equipa"].last(), "nome": g["nome"].last(),
                      "ultima": g["data"].max(),
                      "u_ew": pega("fga") + 0.44 * pega("fta") + pega("tov")})
    E["usg"] = (E.u_ew / E.m_ew.clip(lower=1)).fillna(0)
    E["min3"] = g["min"].apply(lambda x: x.tail(3).mean())
    E["tend"] = np.log((E.min3 / E.m_ew).clip(0.4, 2.5)).fillna(0)
    w = np.minimum(E.n, 2 * HL) * E.m_ew
    E["taxa"] = ((E.s_ew / E.m_ew).fillna(0) * w + lg * K_PRIOR) / (w + K_PRIOR)
    # participacao: fracao dos ultimos 10 jogos da equipa em que jogou
    E["part"] = 0.0
    for t, Ht in H.groupby("equipa"):
        ult = Ht.drop_duplicates("jogo_id").sort_values("data")["jogo_id"].tail(10)
        jog = Ht[Ht.jogo_id.isin(ult)].groupby("jogador_id").size() / len(ult)
        idx = E.index[(E.equipa == t)]
        E.loc[idx, "part"] = jog.reindex(idx).fillna(0).values
    # producao "normal" da equipa (EW das somas por jogo)
    D = caracteristicas(H, s, shift=False)
    dia = pd.DataFrame({"jogo_id": H.jogo_id, "equipa": H.equipa, "data": H.data, "p": D.taxa * D.m0})
    dia = dia.groupby(["jogo_id", "equipa", "data"])["p"].sum().reset_index().sort_values("data")
    norma = dia.groupby("equipa")["p"].apply(lambda x: x.ewm(halflife=10).mean().iloc[-1])
    E["estrela"] = ((E.taxa >= 0.72) & (E.n >= 10) & (g["pos"].last().fillna("").str[-1] == "G")).astype(int) \
        if s == "pts" else 0
    adv = fator_adversario(H, s, final=True)
    Dt = caracteristicas(H, s)   # estado ANTES de cada jogo, como no treino
    adv.attrs["sup"] = fator_estrelas(H, s, Dt.taxa * H["min"].clip(lower=0), Dt.estrela, Dt.n, final=True).to_dict()
    return E, norma, adv

FALTA_BASE = 0.12
CORR_FALTA, CORR_VOLTA20, CORR_VOLTA8, CORR_ALTO, LIMIAR_ALTO = 0.7, 0.75, 0.85, 0.2, 20.0

def prever(E, norma, adv, par, equipa, adversario, casa, prob_faltar, data=None):
    """Pontos previstos para cada jogador de 'equipa'. prob_faltar: {jogador_id: 0..1}."""
    R = E[(E.equipa == equipa) & (E.part > 0)].copy()
    R["disp"] = 1 - R.index.map(lambda p: prob_faltar.get(p, 0.0))
    R["m_esp"] = R.m_ew * R.part * R.disp
    tot = R.m_esp.sum() or 1
    # minutos SE jogar = a media recente. Testei aumentar os minutos dos outros quando alguem falta, mas num
    # teste "ao vivo" em 2025-26 isso previa +4.6 minutos e +2.8 pontos a mais; o efeito das ausencias ja
    # entra pelo coeficiente "falta" (e a media recente ja reflete ausencias longas).
    R["m_proj"] = R.m_ew.clip(upper=42)
    # "falta" = parte da producao habitual (ultimos 10 jogos) que esta noite nao vai jogar, menos o que falta
    # num jogo normal (FALTA_BASE). Antes comparava com 'norma' e dava falta ~0.15 em quase todos os jogos:
    # num teste "ao vivo" (3.474 jogos, 2025-26 e 2026-27) isso punha os pontos +2 a +3.5 acima da realidade.
    S1 = (R.taxa * R.m_ew * R.part).sum()
    falta = float(np.clip(1 - (R.taxa * R.m_ew * R.part * R.disp).sum() / S1 - FALTA_BASE, -0.3, 0.6)) if S1 > 0 else 0.0
    c = par["coef"]
    um = par.get("usg_media", 0)
    ur = (R.usg / um) if um > 0 else 1.0
    f = np.exp(c[0] + c[1] * falta + c[2] * math.log(min(max(adv.get(adversario, 1.0), 0.5), 2)) + c[3] * casa
               + (c[4] * falta * ur if len(c) > 4 else 0) + (c[5] * R.tend if len(c) > 5 else 0)
               + (c[6] * R.estrela * adv.attrs.get("sup", {}).get(adversario, 0.0) if len(c) > 6 else 0))
    # correcoes do teste "noite a noite" (ajustadas em 2025-26, confirmadas em 2026-27: erro 4.92 -> 4.60):
    # 1) o bonus por colegas em falta era grande demais; 2) quem volta de ausencia longa joga menos;
    # 3) projecoes muito altas (estrelas) exageravam.
    f = f * math.exp(-CORR_FALTA * max(falta, 0.0))
    hoje = pd.Timestamp(datetime.now(ZoneInfo("America/New_York")).date()) if data is None else pd.Timestamp(data)
    dias = (hoje - pd.to_datetime(R.ultima)).dt.days
    f = f * np.where(dias > 20, CORR_VOLTA20, np.where(dias > 7, CORR_VOLTA8, 1.0))
    mu = R.m_proj * R.taxa * f
    R["mu"] = mu - CORR_ALTO * (mu - LIMIAR_ALTO).clip(lower=0)
    R["falta_equipa"] = falta
    return R
