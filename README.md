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

## Dois destinos, por grau de certeza

O que a passada exata acha e o que a perceptual acha não têm o mesmo grau de confiança, e por isso não vão para o mesmo lugar:

| origem | destino | por quê |
|---|---|---|
| grupo **exato** | `quarentena` | Os bytes são idênticos. Ou o SHA-256 bate ou não bate — não há falso positivo possível. |
| grupo **perceptual** | `revisao` | Veio de semelhança, que erra. Pode ser foto única. Fila de decisão humana, nunca descarte automático. |

A separação é estrutural de propósito. Numa medição real numa pasta de referência facial, **4 de 11 candidatos perceptuais eram uma rajada** de fotos distintas — mesma pose, instantes e enquadramentos diferentes — e não cópias. Apertar o limiar de distância não resolveria: a rajada media distância 2, dentro de qualquer corte defensável. Limiar escolhido para fazer um caso específico passar é chute; separar por grau de certeza é garantia.

`isolar --somente quarentena` move só o descarte seguro, sem tocar na fila de revisão.

## Saída

Grava na tabela `duplicatas` do `acervo`. Também exporta relatório JSON com `duplicate_groups`, espaço recuperável e o representante de cada grupo.

## Instalação

Requer **Python 3.10 ou mais novo** e Git. Testado no Windows 11 com Python 3.14.

São **dois programas**, e a ordem importa: `acervo` varre o disco, calcula SHA-256 e hash perceptual, e escreve o índice; `acervo-dedup` lê esse índice e decide o que é duplicata. A divisão existe para a imagem ser decodificada **uma vez só** pela suíte inteira — por isso `acervo-dedup` não depende de Pillow: ele lê `phash` do banco em vez de reabrir a foto.

```bash
git clone https://github.com/ferlief/acervo.git
git clone https://github.com/ferlief/acervo-dedup.git

pip install -e ./acervo
pip install -e ./acervo-dedup
```

Os dois repositórios são **privados** (código fechado, Obsn Studios): o `clone` exige credencial com acesso. A distribuição para quem não tem acesso ao código é executável empacotado, não `git clone` — ainda não existe.

Confirme que instalou:

```bash
python -m acervo.cli --help
python -m acervo_dedup.cli --help
```

**No Windows, `pip` costuma avisar que a pasta `Scripts` não está no PATH.** Se `acervo-dedup` não for reconhecido como comando, use a forma `python -m acervo_dedup.cli ...` — funciona sempre, sem mexer no PATH. Todos os exemplos abaixo usam essa forma.

## Uso

### 1. Configurar

```bash
cp acervo/config.example.yaml acervo-config.yaml
cp acervo-dedup/config.example.yaml dedup-config.yaml
```

Nos dois arquivos, aponte `banco.caminho` para o **mesmo** `.sqlite3` — é ele que liga os dois programas — e `varredura.raizes` para a pasta a limpar. Em `dedup-config.yaml`, confira também `quarentena.diretorio` e `revisao.diretorio`.

Nenhum caminho é fixo no código: a mesma linha de comando roda contra uma pasta de teste ou contra o acervo inteiro, trocando só a config.

### 2. Indexar

```bash
python -m acervo.cli --config acervo-config.yaml indexar
```

Varre, hasheia e decodifica cada imagem uma vez. Só isso demora — as etapas seguintes são rápidas.

### 3. Detectar

```bash
python -m acervo_dedup.cli --config dedup-config.yaml scan
```

**Não move nada.** Grava a tabela `duplicatas` e o relatório JSON, e imprime quanto espaço é recuperável, separado por grau de certeza.

### 4. Conferir antes de mexer

Abra o relatório JSON. Cada grupo traz o representante (o que fica), o motivo da escolha, e os candidatos com seu `destino`. Vale conferir a olho os grupos `perceptual` — são os falíveis.

### 5. Isolar o descarte seguro

Primeiro em dry-run, que é o padrão:

```bash
python -m acervo_dedup.cli --config dedup-config.yaml isolar --somente quarentena
```

Se a lista fizer sentido, execute:

```bash
python -m acervo_dedup.cli --config dedup-config.yaml isolar --somente quarentena --execute
```

Move só as cópias byte-idênticas. A estrutura de subpastas é preservada, e nada é sobrescrito (colisão de nome ganha sufixo `_dup1`).

### 6. Decidir sobre as parecidas

```bash
python -m acervo_dedup.cli --config dedup-config.yaml isolar --somente revisao --execute
```

Isso **não é descarte** — é fila de decisão. Olhe a pasta `revisao` e devolva para o acervo o que for foto única.

### 7. Apagar — só você

O programa nunca apaga. Depois de conferir a quarentena, apagar a pasta é uma escolha sua, fora da ferramenta. É esse passo que recupera o espaço em disco.

## Estado

**Implementado.** CLI em Python (`src/acervo_dedup/`), portado das oito iterações do protótipo de origem (`acervo-prototipo/dedup_fase1.py` … `dedup_fase8.py`), não copiado — a passada exata e a perceptual usam a mesma lógica testada em disco real (triagem por tamanho, SHA-256 em blocos, hash perceptual com indexação multi-partição/LSH, guarda de proporção), adaptada ao contrato de `acervo/esquema.sql`.

Duas diferenças deliberadas em relação ao protótipo, exigidas pelo contrato da suite:

- A passada perceptual **lê** `phash`/`largura`/`altura` de `arquivos` em vez de reabrir a imagem — é o próprio propósito de `sinais(fonte=exif)` no esquema: dar a este programa o que ele precisa sem redecodificar.
- A política de representante é mais específica que a descrita acima: grupo exato usa a data de criação mais antiga; grupo perceptual usa qualidade mensurável (RAW > resolução > original-vs-edição via EXIF Software > menor perda de compressão via soma de quantização JPEG), com desempate por data. Ver `src/acervo_dedup/quality.py`.

Comandos: `acervo-dedup scan` (detecta e grava relatório + `duplicatas`, nunca move nada) e `acervo-dedup isolar` (move para `quarentena`/`revisao` conforme o grau de certeza, dry-run por padrão, `--execute` para mover de fato, `--somente` para tratar uma classe por vez). `python -m unittest discover -s tests` cobre a política de representante, os dois agrupamentos, o roteamento entre os dois destinos e um teste de ponta a ponta com disco e SQLite reais.

## Licença e monetização

Código fechado, sob Obsn Studios.

Gratuito para uso pessoal local, sem limite artificial. Licença comercial simbólica por honra para uso profissional, no modelo Obsidian. Sem paywall agressivo, sem assinatura recorrente.
