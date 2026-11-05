# nba-odds

Recolha automatica de odds da NBA (The Odds API) com GitHub Actions.

**Para ver as odds de forma legivel, abre [RESUMO.md](RESUMO.md).** Os ficheiros em `odds/` sao dados em bruto para o modelo.
As odds ficam em `odds/AAAA-MM-DD.csv` (uma linha por casa de apostas, mercado e resultado).

- 11:07 e 18:07 UTC: vencedor, handicap e totais (3 pedidos cada)
- De 15 em 15 minutos entre as 22:00 e as 04:00 UTC: verifica (de graca) se algum jogo comeca nos
  proximos 45 minutos e, se sim, guarda as odds de vencedor (1 pedido), no maximo uma vez a cada 40 minutos.

Total: cerca de 300 a 350 pedidos por mes, dentro dos 500 do plano gratis.
A chave da API esta guardada como secret `ODDS_API_KEY` (Settings > Secrets and variables > Actions).

## Props (linhas de jogadores) — desde 2026-11-05
`props.py` guarda as linhas de pontos dos jogadores da Pinnacle em `props/AAAA-MM-DD.csv`, duas vezes por jogo
(`cedo` ~3h antes e `fecho` ~30 min antes), e as lesoes da ESPN de cada momento em `props/lesoes/`.
A recolha do vencedor (h2h) deixou de correr sozinha para poupar pedidos.

### Apostas virtuais em props (tudo na nuvem, sem PC)
- `historico.py`: estatisticas de cada jogador em cada jogo, da ESPN -> `dados/jogadores.csv`.
- `modelo_props.py`: preve pontos de cada jogador (minutos, ritmo de pontos, colegas lesionados, adversario).
- `apostas_props.py`: decide over/under/passar com as linhas "cedo" da Pinnacle e as lesoes desse momento,
  avalia no dia seguinte (resultado e CLV contra a linha de fecho) e escreve **`props/RESUMO_PROPS.md`**.
