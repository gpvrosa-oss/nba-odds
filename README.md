# nba-odds

Recolha automatica de odds da NBA (The Odds API) com GitHub Actions.
As odds ficam em `odds/AAAA-MM-DD.csv` (uma linha por casa de apostas, mercado e resultado).

- 11:07 e 18:07 UTC: vencedor, handicap e totais (3 pedidos cada)
- De 15 em 15 minutos entre as 22:00 e as 04:00 UTC: verifica (de graca) se algum jogo comeca nos
  proximos 45 minutos e, se sim, guarda as odds de vencedor (1 pedido), no maximo uma vez a cada 40 minutos.

Total: cerca de 300 a 350 pedidos por mes, dentro dos 500 do plano gratis.
A chave da API esta guardada como secret `ODDS_API_KEY` (Settings > Secrets and variables > Actions).
