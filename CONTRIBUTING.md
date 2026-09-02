# Contribuindo com acervo-dedup

## Mensagens de commit

**Inglês, sempre — [Conventional Commits](https://www.conventionalcommits.org/), modo imperativo.** Não depende de o repositório ser fechado ou ter audiência externa — é o padrão de quem programa de forma séria hoje, independentemente de quem lê depois. Identificador e comentário de código continuam em português; a mensagem de commit é uma superfície separada.

```
<type>(<scope>): short imperative summary, ≤50 chars

Body explaining WHY this change exists, not what changed — the diff
already shows what. Wrap at ~72 columns.
```

Tipos comuns: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`.

Referências: [conventionalcommits.org](https://www.conventionalcommits.org/) para o formato, as 7 regras de Chris Beams ("How to Write a Git Commit Message") para a prosa. Sem linha de atribuição a ferramenta de geração de código.

## Antes de abrir um PR

O custo do erro aqui é o mais alto da suíte: apagar o original é irreversível (ver `CLAUDE.md`). Qualquer mudança em `quality.py` (política de representante) ou em `quarantine.py` merece rodar `python -m unittest discover -s tests` — a suíte já cobre disco e SQLite reais, não só dado sintético — antes do PR, não depois.
