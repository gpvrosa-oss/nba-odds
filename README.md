# nba-odds

Recolha automatica de odds da NBA (The Odds API), 5 vezes por dia, com GitHub Actions.
As odds ficam em `odds/AAAA-MM-DD.csv` (uma linha por casa de apostas, mercado e resultado).

- 11:00 e 18:00 UTC: vencedor, handicap e totais (3 pedidos cada)
- 23:30, 00:45 e 02:15 UTC: so vencedor, para ter as odds de fecho (1 pedido cada)

Total: cerca de 270 pedidos por mes, dentro dos 500 do plano gratis.
A chave da API esta guardada como secret `ODDS_API_KEY` (Settings > Secrets and variables > Actions).
