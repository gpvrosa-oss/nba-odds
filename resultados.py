"""Um ficheiro por noite com o resumo das apostas virtuais: Resultados/Resultados(AAAA-MM-DD).md

A data e a da manha em Lisboa a seguir aos jogos (ex.: jogos da noite de 9 para 10 -> Resultados(2026-11-10).md).
Corre no fim de apostas_props.py; reescreve os ficheiros das noites com apostas (e barato e fica sempre certo).
"""
from pathlib import Path
import pandas as pd

PASTA = Path("Resultados")
CLV_MAX = 0.20   # valores de CLV acima de +-20% sao erros de leitura de linha: ficam fora da media
# Modelo B: o mesmo modelo com 3 regras extra (combinado a 12/11). Teste justo so a partir da noite de 13/11.
B_LINHA_MIN, B_EV_MIN, B_INICIO = 9.5, 0.05, "2026-11-13"


def _modelo_b(A):
    return (A.origem != "alerta") & (A.linha > B_LINHA_MIN) & (A.ev > B_EV_MIN)


def _clv(s):
    s = s.dropna()
    s = s[s.abs() <= CLV_MAX]
    return f"{s.mean():+.1%}" if len(s) else "-"


def _linha_resumo(G):
    d = G[G.resultado.isin(["ganhou", "perdeu"])]
    g, p = (d.resultado == "ganhou").sum(), (d.resultado == "perdeu").sum()
    return g, p, d.stake.sum(), d.lucro.sum()


def escrever():
    fb = Path("props/apostas.csv")
    if not fb.exists():
        return
    A = pd.read_csv(fb, dtype={"jogo_id": str})
    A["inicio"] = pd.to_datetime(A.inicio_jogo, utc=True)
    A["noite"] = (A.inicio + pd.Timedelta(hours=12)).dt.strftime("%Y-%m-%d")
    A["origem"] = A.origem.fillna("normal")
    A["b"] = _modelo_b(A)
    PASTA.mkdir(exist_ok=True)
    indice = []
    for noite, G in A.groupby("noite"):
        antes = A[A.noite <= noite]
        g, p, apostado, lucro = _linha_resumo(G)
        tg, tp, tap, tlu = _linha_resumo(antes)
        pendentes = G.resultado.isna().sum()
        anuladas = (G.resultado == "anulada").sum()
        dd = pd.Timestamp(noite)
        L = [f"# Resultados {dd:%d/%m/%Y}", "",
             f"Apostas virtuais (sem dinheiro real) dos jogos da noite de {dd - pd.Timedelta(days=1):%d/%m} para {dd:%d/%m}. "
             "Odds da Pinnacle, 1 unidade por aposta (menos quando o modelo aposta menos).", ""]
        if pendentes:
            L += [f"**Ainda ha {pendentes} apostas por decidir** (jogos a decorrer ou resultados por chegar).", ""]
        L += ["## Resumo da noite", "",
              f"- Apostas: **{len(G)}** (ganhas {g}, perdidas {p}" + (f", anuladas {anuladas}" if anuladas else "") + ")",
              f"- Apostado: {apostado:.1f} unidades",
              f"- Lucro: **{lucro:+.2f} unidades**" + (f" (ROI {lucro / apostado:+.1%})" if apostado else ""),
              f"- CLV medio: {_clv(G.clv)} (se o mercado se moveu a nosso favor depois de apostarmos)", ""]
        dec = G[G.resultado.isin(["ganhou", "perdeu"])]
        if len(dec):
            L += ["| Tipo | Apostas | Ganhas | Lucro |", "| --- | --- | --- | --- |"]
            for nome, S in [("Over", dec[dec.lado == "Over"]), ("Under", dec[dec.lado == "Under"]),
                            ("Alertas de ultima hora", dec[dec.origem == "alerta"])]:
                if len(S):
                    L.append(f"| {nome} | {len(S)} | {(S.resultado == 'ganhou').sum()} | {S.lucro.sum():+.2f} |")
            L.append("")
        bg, bp, bap, blu = _linha_resumo(G[G.b])
        ag_ = A[(A.noite >= B_INICIO) & (A.noite <= noite)]
        t_a, t_b = _linha_resumo(ag_), _linha_resumo(ag_[ag_.b])
        L += ["## Modelo A (atual) vs Modelo B (com as 3 regras)", "",
              "Modelo B = as mesmas apostas, mas sem linhas ate 9.5, so com valor acima de 5% e sem alertas de ultima hora.", "",
              "| | Apostas | Ganhas | Lucro | ROI |", "| --- | --- | --- | --- | --- |",
              f"| A esta noite | {g + p} | {g} | {lucro:+.2f} | " + (f"{lucro / apostado:+.1%}" if apostado else "-") + " |",
              f"| B esta noite | {bg + bp} | {bg} | {blu:+.2f} | " + (f"{blu / bap:+.1%}" if bap else "-") + " |"]
        if noite >= B_INICIO:
            L += [f"| A desde 13/11 | {t_a[0] + t_a[1]} | {t_a[0]} | {t_a[3]:+.2f} | " + (f"{t_a[3] / t_a[2]:+.1%}" if t_a[2] else "-") + " |",
                  f"| B desde 13/11 | {t_b[0] + t_b[1]} | {t_b[0]} | {t_b[3]:+.2f} | " + (f"{t_b[3] / t_b[2]:+.1%}" if t_b[2] else "-") + " |"]
        L += [""]
        L += ["## Total acumulado (desde 05/11)", "",
              f"- Apostas decididas: {tg + tp} (ganhas {tg}, {tg / max(tg + tp, 1):.0%})",
              f"- Lucro: **{tlu:+.2f} unidades** em {tap:.1f} apostadas" + (f" (ROI {tlu / tap:+.1%})" if tap else ""),
              f"- CLV medio: {_clv(antes.clv)}",
              f"- Com 4 EUR por aposta: {tlu * 4:+.0f} EUR (as odds da Pinnacle; na Betano seria menos)", ""]
        L += ["## Apostas", "",
              "| Jogo | Jogador | Aposta | Odd | Modelo | Pontos | Resultado | Lucro | B? |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in G.sort_values(["inicio", "jogador"]).itertuples():
            jogo = f"{r.fora} @ {r.casa}"
            res = {"ganhou": "ganhou", "perdeu": "perdeu", "anulada": "anulada"}.get(r.resultado, "por decidir")
            real = "" if pd.isna(r.real) else f"{r.real:.0f}"
            lu = "" if pd.isna(r.lucro) else f"{r.lucro:+.2f}"
            extra = " (alerta)" if r.origem == "alerta" else ""
            L.append(f"| {jogo} | {r.jogador}{extra} | {r.lado} {r.linha} | {r.odd} | {r.previsto:.1f} | {real} | {res} | {lu} | {'sim' if r.b else ''} |")
        L.append("")
        indice.append((noite, len(G), g, p, lucro, tlu, blu))
        f = PASTA / f"Resultados({noite}).md"
        txt = "\n".join(L)
        if not f.exists() or f.read_text(encoding="utf-8") != txt:
            f.write_text(txt, encoding="utf-8")
    # indice: todos os dias por ordem, com link para o ficheiro de cada noite
    I = ["# Resultados de todas as noites", "", "Apostas virtuais (sem dinheiro real), por ordem. Clica na data para ver todas as apostas dessa noite.", "",
         "| Noite | Apostas | Ganhas | Perdidas | Lucro da noite | Total acumulado | Lucro modelo B |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for noite, n, g, p, lu, tot, blu in indice:
        nome = f"Resultados({noite}).md"
        I.append(f"| [{pd.Timestamp(noite):%d/%m/%Y}](<{nome}>) | {n} | {g} | {p} | {lu:+.2f} | {tot:+.2f} | {blu:+.2f} |")
    (PASTA / "README.md").write_text("\n".join(I) + "\n", encoding="utf-8")


if __name__ == "__main__":
    escrever()
