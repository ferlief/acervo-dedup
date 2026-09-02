# Contribuindo com acervo-dedup

## Mensagens de commit

**Inglês, sempre — [Conventional Commits](https://www.conventionalcommits.org/), modo imperativo.** Não depende de o repositório ser fechado ou ter audiência externa — é o padrão de quem programa de forma séria hoje, independentemente de quem lê depois. Identificador continua em português; comentário e docstring também são em inglês (ver abaixo).

```
<type>(<scope>): short imperative summary, ≤50 chars

Body explaining WHY this change exists, not what changed — the diff
already shows what. Wrap at ~72 columns.
```

Tipos comuns: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`.

Referências: [conventionalcommits.org](https://www.conventionalcommits.org/) para o formato, as 7 regras de Chris Beams ("How to Write a Git Commit Message") para a prosa. Sem linha de atribuição a ferramenta de geração de código.

## Comentários e docstrings

**Inglês, sempre.** Pela mesma razão da mensagem de commit: é o padrão de quem programa de forma séria, e não depende de quem lê depois.

O que **não** muda de idioma:

| superfície | idioma | por quê |
|---|---|---|
| comentário, docstring, mensagem de commit | inglês | público técnico, indeterminado |
| identificador (`agrupar_exatas`, `quarentena_dir`) | português | renomear é refatoração de risco, e o vocabulário do domínio é o do acervo |
| saída do CLI, texto de interface, README | português | a usuária é brasileira; a ferramenta fala com ela |

Um comentário existe para explicar **por que**, não o quê. Se ele estiver descrevendo o que a linha faz, o problema é a linha.

## Antes de abrir um PR

O custo do erro aqui é o mais alto da suíte: apagar o original é irreversível (ver `CLAUDE.md`). Qualquer mudança em `quality.py` (política de representante) ou em `quarantine.py` merece rodar `python -m unittest discover -s tests` — a suíte já cobre disco e SQLite reais, não só dado sintético — antes do PR, não depois.

## A camada gráfica

`src/acervo_dedup/gui/` é **apresentação, e só**. A regra que a mantém honesta: ela não importa `exact`, `perceptual`, `quality` nem `quarantine` — executa `acervo-dedup scan` e `acervo-dedup isolar` como subprocesso e transmite o `stdout`.

Isso não é purismo arquitetural, é o invariante 1 sobrevivendo à existência de botões: se a única forma de mover arquivo é o comando que já era auditável, nenhum bug de interface inventa um caminho novo até o disco. Uma regra de decisão que aparecer nessa pasta está no lugar errado.
