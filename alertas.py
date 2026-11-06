"""Alerta de ultima hora: um jogador importante passa a "Out"/"Doubtful" depois da fotografia "cedo".

Corre a cada ciclo do vigia (10 min). So faz alguma coisa se houver jogos a comecar nas proximas 2h30:
1. le as lesoes da ESPN (gratis) e compara com a ultima fotografia guardada;
2. se um jogador com papel grande (>= 22 min de media) passou a provavel ausente, recalcula os colegas
   com o modelo e pede a linha ATUAL da Pinnacle para esse jogo (1 credito; no maximo 4 por dia);
3. se a Pinnacle ainda nao ajustou e ha valor, regista apostas virtuais (origem "alerta") em props/apostas.csv;
4. escreve props/ALERTAS.md e abre um "issue" no GitHub (chega como notificacao/email ao dono do repo).
"""
import csv, json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
import modelo_props as M
import apostas_props as AP

API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
KEY = os.environ.get("ODDS_API_KEY", "")
PASTA = Path("props")
EST = PASTA / "alertas_estado.json"
JANELA = (5, 150)          # minutos antes do inicio (depois da fotografia "cedo")
MIN_MINUTOS = 22           # so jogadores com papel grande
MAX_CREDITOS_DIA = 4

def parse(inj):
    """{(equipa, nome_chave): (nome, estado, prob_faltar)}"""
    out = {}
    for eq in inj.get("injuries", []):
        team = M.EQUIPAS.get(eq.get("displayName", ""))
        for i in eq.get("injuries", []):
            est = i.get("status", "").lower()
            txt = (i.get("shortComment", "") + " " + i.get("longComment", "")).lower()
            p = AP.PROB_FALTAR.get(est, 0.5)
            if est != "out" and ("game-time decision" in txt or "game time decision" in txt):
                p = 0.5
            nome = i["athlete"]["displayName"]
            out[(team, M.nome_chave(nome))] = (nome, i.get("status", ""), p)
    return out

def main():
    agora = datetime.now(timezone.utc)
    ev = requests.get(f"{API}/events", params={"apiKey": KEY}, timeout=30).json()   # gratis
    jogos = []
    for e in ev:
        falta = (datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) - agora).total_seconds() / 60
        if JANELA[0] < falta <= JANELA[1]:
            jogos.append(e)
    if not jogos:
        return
    inj = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries", timeout=30).json()
    fot = sorted((PASTA / "lesoes").glob("*.json"))
    antes = parse(json.loads(fot[-1].read_text())) if fot else {}
    agora_l = parse(inj)
    if agora_l != antes:   # guarda a nova fotografia (o resumo e as apostas usam-na)
        (PASTA / "lesoes" / f"{agora:%Y-%m-%dT%H%MZ}.json").write_text(json.dumps(inj))
    est = json.loads(EST.read_text()) if EST.exists() else {}
    hoje = f"{agora:%Y-%m-%d}"
    est.setdefault("creditos", {}); est.setdefault("vistos", [])
    H = M.carregar()
    ult = H[H.data >= H.data.max() - pd.Timedelta(days=21)]
    mins = ult.assign(k=ult.nome.map(M.nome_chave)).groupby(["equipa", "k"])["min"].mean()
    for e in jogos:
        casa, fora = M.EQUIPAS.get(e["home_team"]), M.EQUIPAS.get(e["away_team"])
        mud = []
        for (t, k), (nome, status, p) in agora_l.items():
            if t not in (casa, fora) or p < 0.75:
                continue
            p0 = antes.get((t, k), (None, None, 0.0))[2]
            chave = f"{e['id']}|{k}"
            if p - p0 >= 0.4 and mins.get((t, k), 0) >= MIN_MINUTOS and chave not in est["vistos"]:
                mud.append((t, k, nome, status, p, p0, round(float(mins.get((t, k))), 1)))
                est["vistos"].append(chave)
        if not mud:
            continue
        # modelo: colegas com e sem a noticia
        par = M.treinar(H, "pts")
        E, norma, adv = M.estado_atual(H, "pts")
        E["k"] = E.nome.map(M.nome_chave)
        pf_antes = {pid: antes.get((E.at[pid, "equipa"], k), (0, 0, 0.0))[2] for pid, k in E.k.items()}
        pf_agora = {pid: agora_l.get((E.at[pid, "equipa"], k), (0, 0, 0.0))[2] for pid, k in E.k.items()}
        R0 = pd.concat([M.prever(E, norma, adv, par, casa, fora, 1, pf_antes), M.prever(E, norma, adv, par, fora, casa, 0, pf_antes)])
        R1 = pd.concat([M.prever(E, norma, adv, par, casa, fora, 1, pf_agora), M.prever(E, norma, adv, par, fora, casa, 0, pf_agora)])
        R1["antes"] = R0.mu.reindex(R1.index)
        R1 = R1[(R1.disp > 0.75) & (R1.equipa.isin({m[0] for m in mud}))]
        R1["dif"] = R1.mu - R1.antes
        # linha atual da Pinnacle (1 credito)
        linhas, apostas = {}, []
        if est["creditos"].get(hoje, 0) < MAX_CREDITOS_DIA and KEY:
            r = requests.get(f"{API}/events/{e['id']}/odds", params={"apiKey": KEY, "bookmakers": "pinnacle",
                             "markets": "player_points", "oddsFormat": "decimal"}, timeout=30)
            est["creditos"][hoje] = est["creditos"].get(hoje, 0) + 1
            if r.ok:
                rec = agora.strftime("%Y-%m-%dT%H:%M:%SZ"); rows = []
                for bk in r.json().get("bookmakers", []):
                    for m in bk.get("markets", []):
                        for o in m.get("outcomes", []):
                            rows.append([rec, "alerta", e["id"], e["commence_time"], e["home_team"], e["away_team"], bk["key"],
                                         m.get("last_update", ""), m["key"], o.get("description", ""), o["name"], o.get("point", ""), o["price"]])
                            linhas.setdefault(M.nome_chave(o.get("description", "")), {})[o["name"]] = (o.get("point"), o["price"])
                f = PASTA / f"{agora:%Y-%m-%d}.csv"
                novo = not f.exists()
                with f.open("a", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    if novo:
                        w.writerow(["recolhido_em", "momento", "jogo_id", "inicio_jogo", "casa", "fora", "casa_apostas",
                                    "atualizado_em", "mercado", "jogador", "lado", "linha", "odd"])
                    w.writerows(rows)
        txt = [f"## {agora:%d/%m %H:%M} UTC: {e['away_team']} @ {e['home_team']}", ""]
        txt += [f"- **{n}** ({t}, {mm} min de media): {s} (antes: {p0:.0%} de faltar, agora {p:.0%})" for t, k, n, s, p, p0, mm in mud]
        txt += ["", "Colegas (pontos previstos antes -> agora | linha Pinnacle agora | veredito):", "```"]
        for j in R1.sort_values("dif", ascending=False).itertuples():
            if j.dif < 1.0 and M.nome_chave(j.nome) not in linhas:
                continue
            l = linhas.get(M.nome_chave(j.nome), {})
            ver, lt = "", ""
            if "Over" in l and "Under" in l and l["Over"][0] == l["Under"][0]:
                ln, oo, ou = float(l["Over"][0]), l["Over"][1], l["Under"][1]
                pj = (1 / oo) / (1 / oo + 1 / ou)
                pm_ = float(M.p_over([j.mu], [ln], par["r"], par["a"], par["b"])[0])
                pm = AP.PESO_MODELO * pm_ + (1 - AP.PESO_MODELO) * pj
                evo, evu = pm * oo - 1, (1 - pm) * ou - 1
                lado, ev, odd, pl = ("Over", evo, oo, pm) if evo > evu else ("Under", evu, ou, 1 - pm)
                lt = f"{ln} ({oo}/{ou})"
                if ev > AP.VALOR_MIN and abs(pm_ - pj) <= AP.DISCORDANCIA_MAX and E.at[j.Index, "n"] >= AP.MIN_JOGOS:
                    stake = round(min(AP.FRACAO_KELLY * (pl * odd - 1) / (odd - 1), AP.STAKE_MAX) * AP.BANCA, 2)
                    ver = f"APOSTA {lado} @ {odd} (EV {ev:+.1%})"
                    apostas.append(dict(chave=f"{e['id']}|player_points|{j.nome}|alerta", recolhido_em=agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        jogo_id=e["id"], inicio_jogo=e["commence_time"], mercado="player_points",
                                        casa=e["home_team"], fora=e["away_team"], jogador=j.nome, linha=ln, odd_over=oo, odd_under=ou,
                                        p_justa=round(pj, 4), lado=lado, odd=odd, previsto=round(j.mu, 2), p_modelo=round(pm_, 4),
                                        ev=round(ev, 4), stake=stake, origem="alerta"))
                else:
                    ver = "sem valor (a Pinnacle ja ajustou?)" if ev <= AP.VALOR_MIN else "passar"
            txt.append(f"{j.nome:24s} {j.antes:5.1f} -> {j.mu:5.1f} ({j.dif:+.1f}) | {lt:18s} | {ver}")
        txt += ["```", "", "Na Betano/Betclic: confirma se a linha desses jogadores ainda nao subiu.", ""]
        if apostas:
            fb = PASTA / "apostas.csv"
            A = pd.read_csv(fb, dtype={"jogo_id": str}) if fb.exists() else pd.DataFrame()
            pd.concat([A, pd.DataFrame(apostas)], ignore_index=True).to_csv(fb, index=False)
        fa = PASTA / "ALERTAS.md"
        old = fa.read_text(encoding="utf-8").split("\n", 2)[2] if fa.exists() else ""
        fa.write_text("# Alertas de ultima hora\n\n" + "\n".join(txt) + "\n" + old, encoding="utf-8")
        titulo = "ALERTA: " + ", ".join(f"{n} {s}" for t, k, n, s, p, p0, mm in mud) + f" ({e['away_team']} @ {e['home_team']})"
        try:
            subprocess.run(["gh", "issue", "create", "--title", titulo[:250], "--body", "\n".join(txt)], check=False, timeout=60)
        except Exception as x:
            print("issue falhou:", x)
        print(titulo)
    est["vistos"] = est["vistos"][-300:]
    EST.write_text(json.dumps(est))

if __name__ == "__main__":
    main()
