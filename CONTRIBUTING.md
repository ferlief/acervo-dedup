# Contribuindo com acervo-dedup

## Idioma dos commits

**Português.** Repositório fechado, sob Obsn Studios, sem audiência externa prevista — identificador, README, comentário de código: tudo já está em português. Um commit em inglês seria a única peça fora do padrão, não o contrário.

Se este repositório algum dia abrir código ou ganhar colaborador que não leia português, esta é a primeira regra a revisar — não antes disso.

## Formato

- Modo imperativo, foco no porquê da mudança, não só no quê.
- Sem linha de atribuição a ferramenta de geração de código.

## Antes de abrir um PR

O custo do erro aqui é o mais alto da suíte: apagar o original é irreversível (ver `CLAUDE.md`). Qualquer mudança em `quality.py` (política de representante) ou em `quarantine.py` merece rodar `python -m unittest discover -s tests` — a suíte já cobre disco e SQLite reais, não só dado sintético — antes do PR, não depois.
