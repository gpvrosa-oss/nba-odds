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

def _ew(x, shift):
    x = x.shift() if shift else x
    return x.ewm(halflife=HL).mean()

def caracteristicas(H, s, shift=True):
    """Para cada linha de H: estado do jogador ANTES do jogo (shift=True) -> usado para treinar."""
    g = H.groupby("jogador_id")
    D = pd.DataFrame(index=H.index)
    D["n"] = g.cumcount()
    D["m_ew"] = g["min"].transform(lambda x: _ew(x, shift))
    lg = H[s].sum() / H["min"].sum()
    taxa = g[s].transform(lambda x: _ew(x, shift)) / D.m_ew
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
    u = sum(g[c].transform(lambda x: _ew(x, shift)) * k for c, k in (("fga", 1), ("fta", 0.44), ("tov", 1)))
    D["usg"] = (u / D.m0.clip(lower=1)).fillna(0)
    return D

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
    return np.c_[np.ones(len(D)), D.falta, np.log(D.adv.clip(0.5, 2)), D.casa, D.falta * ur]

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
    y = H[s].values[ok]; X = _X(D, usg_media)[ok]; off = np.log((D.m_proj * D.taxa).clip(0.05)).values[ok]
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
    E = pd.DataFrame({"m_ew": g["min"].apply(lambda x: x.ewm(halflife=HL).mean().iloc[-1]),
                      "s_ew": g[s].apply(lambda x: x.ewm(halflife=HL).mean().iloc[-1]),
                      "n": g.size(), "equipa": g["equipa"].last(), "nome": g["nome"].last(),
                      "ultima": g["data"].max(),
                      "u_ew": sum(g[c].apply(lambda x: x.ewm(halflife=HL).mean().iloc[-1]) * k
                                  for c, k in (("fga", 1), ("fta", 0.44), ("tov", 1)))})
    E["usg"] = (E.u_ew / E.m_ew.clip(lower=1)).fillna(0)
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
    return E, norma, fator_adversario(H, s, final=True)

def prever(E, norma, adv, par, equipa, adversario, casa, prob_faltar):
    """Pontos previstos para cada jogador de 'equipa'. prob_faltar: {jogador_id: 0..1}."""
    R = E[(E.equipa == equipa) & (E.part > 0)].copy()
    R["disp"] = 1 - R.index.map(lambda p: prob_faltar.get(p, 0.0))
    R["m_esp"] = R.m_ew * R.part * R.disp
    tot = R.m_esp.sum() or 1
    # minutos SE jogar = a media recente. Testei aumentar os minutos dos outros quando alguem falta, mas num
    # teste "ao vivo" em 2025-26 isso previa +4.6 minutos e +2.8 pontos a mais; o efeito das ausencias ja
    # entra pelo coeficiente "falta" (e a media recente ja reflete ausencias longas).
    R["m_proj"] = R.m_ew.clip(upper=42)
    falta = float(np.clip(1 - (R.taxa * R.m_ew * R.part * R.disp).sum() / norma.get(equipa, np.nan), -0.3, 0.6)) \
        if equipa in norma else 0.0
    c = par["coef"]
    um = par.get("usg_media", 0)
    ur = (R.usg / um) if um > 0 else 1.0
    f = np.exp(c[0] + c[1] * falta + c[2] * math.log(min(max(adv.get(adversario, 1.0), 0.5), 2)) + c[3] * casa
               + (c[4] * falta * ur if len(c) > 4 else 0))
    R["mu"] = R.m_proj * R.taxa * f
    R["falta_equipa"] = falta
    return R
