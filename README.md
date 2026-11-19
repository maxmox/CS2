# CS2 · Painel do dia

Página: https://maxmox.github.io/CS2/

Jogos de Counter-Strike 2 das próximas ~40 horas, com o preço do Polymarket e o nosso precificador pré-jogo.

- **Polymarket**: meio do livro e o preço real de compra de cada lado (série e cada mapa).
- **Nosso**: a força de cada time é um Elo por mapa, com os resultados da Liquipedia (torneios S/A/B/C-Tier). A série é calculada com mapas independentes e calibrada por formato.
  - Teste fora da amostra em 2026: BO3 log-loss 0,633 e BO1 0,646 (moeda = 0,693).
- **Odd justa**: vem do Polymarket quando ele tem o jogo. Quando não tem, vem do nosso preço.
  - Medido em 19/11/2026, em 3.066 séries desde out/2025, com o preço 10 min antes: o Polymarket teve log-loss 0,589 e o nosso 0,634.
  - Misturar os dois não melhorou.
  - Apostar quando os dois discordam perdeu de −18% a −41%.

## Como roda

A Action roda `.github/workflows/pages.yml` a cada 15 min e chama `python motor/atualizar.py`, que usa só a biblioteca padrão. Ela:

1. Busca as partidas na Liquipedia: uma consulta à página `Liquipedia:Matches`, respeitando os termos da API (programa identificado, gzip, no máximo 1 requisição a cada 2 s e 1 parse a cada 30 s).
2. Busca os jogos de CS2 abertos no Polymarket (gamma-api).
3. Casa os dois pelo horário e pelos nomes:
   - apelidos aprendidos dos jogos passados ficam em `data/apelidos.json`;
   - "≈" na página marca um nome achado por aproximação.
4. Grava o registro: o último preço antes do início de cada jogo (o nosso e o do Polymarket) e o resultado, em `data/registro/AAAA-MM.json`.
5. A cada 3 h, aplica os mapas novos dos torneios recentes à força dos times (`data/forca.json`) e faz commit.

O estado rápido (`data/estado.json`) e a página (`data/hoje.json`) ficam só no site publicado. A Action relê esses arquivos do site a cada rodada.

Para rodar no PC, no Brasil o DNS bloqueia o Polymarket: `DOH=1 python motor/atualizar.py`.
