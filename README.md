# acervo-dedup

Detecção de redundância em acervos grandes. CLI, sem interface.

Responde a **uma** pergunta: *estes arquivos são o mesmo conteúdo?*

## Duas passadas

1. **Exata** — triagem por tamanho em bytes (arquivo de tamanho único é descartado sem I/O), depois SHA-256 em blocos para os candidatos. Agnóstico a nome de arquivo, que costuma estar caótico depois de recuperação de disco.
2. **Perceptual** — hash perceptual para pegar recompressão, redimensionamento e captura de tela da mesma foto, que a passada exata não vê.

## O custo do erro define o desenho

Apagar o original é irreversível. Por isso:

- O motor **isola**, não apaga. A remoção é sempre um segundo passo, explícito.
- O representante do grupo é o de metadado de criação mais antigo, e a escolha é registrada com o motivo.
- Exceção de arquivo bloqueado ou permissão negada não derruba a varredura global.

## Saída

Grava na tabela `duplicatas` do `acervo`. Também exporta relatório JSON com `duplicate_groups`, espaço recuperável e o representante de cada grupo.

## Estado

**Implementado.** CLI em Python (`src/acervo_dedup/`), portado das oito iterações do protótipo de origem (`acervo-prototipo/dedup_fase1.py` … `dedup_fase8.py`), não copiado — a passada exata e a perceptual usam a mesma lógica testada em disco real (triagem por tamanho, SHA-256 em blocos, hash perceptual com indexação multi-partição/LSH, guarda de proporção), adaptada ao contrato de `acervo/esquema.sql`.

Duas diferenças deliberadas em relação ao protótipo, exigidas pelo contrato da suite:

- A passada perceptual **lê** `phash`/`largura`/`altura` de `arquivos` em vez de reabrir a imagem — é o próprio propósito de `sinais(fonte=exif)` no esquema: dar a este programa o que ele precisa sem redecodificar.
- A política de representante é mais específica que a descrita acima: grupo exato usa a data de criação mais antiga; grupo perceptual usa qualidade mensurável (RAW > resolução > original-vs-edição via EXIF Software > menor perda de compressão via soma de quantização JPEG), com desempate por data. Ver `src/acervo_dedup/quality.py`.

Comandos: `acervo-dedup scan` (detecta e grava relatório + `duplicatas`, nunca move nada) e `acervo-dedup isolar` (move para quarentena, dry-run por padrão, `--execute` para mover de fato). `python -m unittest discover -s tests` cobre a política de representante, os dois agrupamentos e um teste de ponta a ponta com disco e SQLite reais.

## Licença e monetização

Código fechado, sob Obsn Studios.

Gratuito para uso pessoal local, sem limite artificial. Licença comercial simbólica por honra para uso profissional, no modelo Obsidian. Sem paywall agressivo, sem assinatura recorrente.
