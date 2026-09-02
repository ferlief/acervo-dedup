# acervo-dedup

Detecção de redundância em acervos grandes. Aplicativo de janela no Windows, com o mesmo motor exposto como CLI.

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

## Interface

Janela nativa do Windows (WebView2, o runtime do Edge que já vem no Windows 11), servida por um servidor local que **só escuta em `127.0.0.1`**, com token de sessão gerado a cada início. Nada trafega para fora da máquina.

A interface é uma **casca**: ela não contém nenhuma regra de detecção, de escolha de representante ou de destino. Ela executa `scan` e `isolar` como subprocesso e transmite o `stdout` deles ao vivo. Apagar a pasta `src/acervo_dedup/gui/` inteira não muda um bit do resultado do motor.

O invariante "isola, nunca apaga" é o que a tela desenha:

- **Não existe botão de apagar** em lugar nenhum da interface.
- `isolar` abre sempre em **dry-run**. Mover de fato exige digitar `ISOLAR` num diálogo que diz quantos arquivos e para onde.
- **Cor é semântica, não decoração.** A paleta vem de *Operários* (Tarsila do Amaral, 1933): ocre = certeza (cópia byte-idêntica, descarte seguro), terracota = semelhança (pode errar, decisão humana), tijolo = ação irreversível, céu = informação neutra.

Quatro etapas, na ordem em que o erro fica mais caro: **Varredura → Resultado → Conferência → Isolar**. As três últimas ficam travadas até existir relatório.

## Instalação

Requer **Windows 10/11 com o runtime WebView2** (já vem instalado no Windows 11) para a janela nativa. Para rodar do código-fonte ou usar só o CLI, requer **Python 3.10 ou mais novo**. Testado no Windows 11 com Python 3.14.

São **dois programas**, e a ordem importa: `acervo` varre o disco, calcula SHA-256 e hash perceptual, e escreve o índice; `acervo-dedup` lê esse índice e decide o que é duplicata. A divisão existe para a imagem ser decodificada **uma vez só** pela suíte inteira — por isso `acervo-dedup` não depende de Pillow: ele lê `phash` do banco em vez de reabrir a foto.

### Opção A — executável (uso normal)

Descompacte `acervo-dedup-windows.zip` numa pasta e dê **duplo clique em `acervo-dedup-gui.exe`**. Não há instalador, não há registro no sistema, não há serviço em segundo plano: apagar a pasta desinstala.

A pasta traz **dois binários**, e os dois são necessários:

| binário | subsistema | papel |
|---|---|---|
| `acervo-dedup-gui.exe` | janela | é o que você abre; não mostra console |
| `acervo-dedup.exe` | console | é o motor; a janela o executa e lê o `stdout` dele para o log ao vivo |

Não separe os dois nem renomeie o segundo — a janela procura `acervo-dedup.exe` ao lado dela.

### Opção B — do código-fonte

Os dois repositórios são **privados** (código fechado, Obsn Studios): o `clone` exige credencial com acesso.

```bash
git clone https://github.com/ferlief/acervo.git
git clone https://github.com/ferlief/acervo-dedup.git
```

Use um ambiente virtual — instalar pacote em Python global é como escrever direto no acervo: funciona até o dia em que outro projeto pede outra versão.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ./acervo
pip install -e "./acervo-dedup[gui]"
```

O extra `[gui]` traz o `pywebview` (a janela nativa). Sem ele o motor e o CLI funcionam igual, e `gui` cai para o navegador — a dependência de janela é opcional de propósito: uma varredura de HD externo por SSH não precisa de toolkit gráfico instalado.

Confirme que instalou:

```bash
python -m acervo.cli --help
python -m acervo_dedup.cli --help
```

**No Windows, `pip` costuma avisar que a pasta `Scripts` não está no PATH.** Se `acervo-dedup` não for reconhecido como comando, use a forma `python -m acervo_dedup.cli ...` — funciona sempre, sem mexer no PATH. Todos os exemplos abaixo usam essa forma.

### Gerar o executável

```bash
pip install -e ".[build]"
python -m PyInstaller --noconfirm --clean packaging/acervo-dedup.spec
```

Sai em `dist/acervo-dedup/` (~36 MB). É `onedir`, não `onefile`, de propósito: a janela executa o CLI uma vez por varredura, e um `onefile` reextrairia o pacote inteiro para uma pasta temporária a cada execução.

## Uso pela interface

Abra `acervo-dedup-gui.exe`. As quatro etapas do trilho lateral são a ordem correta, e cada uma só destrava quando a anterior produziu resultado:

1. **Varredura** — informe as raízes (ou deixe vazio para usar a config) e clique em *Iniciar varredura*. A saída do motor aparece linha a linha. Nada é movido nesta etapa.
2. **Resultado** — quanto dá para recuperar, separado em `quarentena` (cópia byte-idêntica) e `revisao` (parecida). Erros de leitura ficam listados aqui, não escondidos.
3. **Conferência** — grupo a grupo, com o representante, o motivo da escolha e a distância de cada candidato. Filtre por método, ordene por espaço, busque por caminho ou `sha256`. **Vale conferir a olho os grupos perceptuais** — são os falíveis.
4. **Isolar** — comece por *Simular*. Se a lista fizer sentido, *Mover de fato* pede a palavra `ISOLAR` digitada.

Para apontar outra configuração, abra pelo terminal:

```bash
acervo-dedup-gui.exe --config dedup-config.yaml
```

## Uso pelo CLI

O mesmo motor, sem janela. É o caminho para automação, máquina remota e scripts.

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

## Desenvolvimento

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[build]"
python -m unittest discover -s tests
```

A suíte cobre a política de representante, os dois agrupamentos, o roteamento entre os dois destinos e um teste de ponta a ponta com disco e SQLite reais. **Qualquer mudança em `quality.py` ou `quarantine.py` roda a suíte antes do commit, não depois** — é onde o erro custa dado perdido.

Convenções (detalhe em `CONTRIBUTING.md`):

- **Commits em inglês**, Conventional Commits, modo imperativo.
- **Comentários e docstrings em inglês.** Identificadores e texto de interface continuam em português.
- A camada `gui/` não pode importar `exact`, `perceptual`, `quality` nem `quarantine`. Se precisar, a regra está no lugar errado.

## Estado

**Implementado.** Motor em Python (`src/acervo_dedup/`), portado das oito iterações do protótipo de origem (`acervo-prototipo/dedup_fase1.py` … `dedup_fase8.py`), não copiado — a passada exata e a perceptual usam a mesma lógica testada em disco real (triagem por tamanho, SHA-256 em blocos, hash perceptual com indexação multi-partição/LSH, guarda de proporção), adaptada ao contrato de `acervo/esquema.sql`.

Duas diferenças deliberadas em relação ao protótipo, exigidas pelo contrato da suite:

- A passada perceptual **lê** `phash`/`largura`/`altura` de `arquivos` em vez de reabrir a imagem — é o próprio propósito de `sinais(fonte=exif)` no esquema: dar a este programa o que ele precisa sem redecodificar.
- A política de representante é mais específica que a descrita acima: grupo exato usa a data de criação mais antiga; grupo perceptual usa qualidade mensurável (RAW > resolução > original-vs-edição via EXIF Software > menor perda de compressão via soma de quantização JPEG), com desempate por data. Ver `src/acervo_dedup/quality.py`.

Comandos: `acervo-dedup scan` (detecta e grava relatório + `duplicatas`, nunca move nada), `acervo-dedup isolar` (move para `quarentena`/`revisao` conforme o grau de certeza, dry-run por padrão, `--execute` para mover de fato, `--somente` para tratar uma classe por vez) e `acervo-dedup gui` (janela nativa; `--navegador` força a aba do navegador).

A interface gráfica (`src/acervo_dedup/gui/`) é posterior ao motor e não o alterou: ela executa os dois comandos acima como subprocesso. O empacotamento para Windows está em `packaging/`.

## Licença e monetização

Código fechado, sob Obsn Studios.

Gratuito para uso pessoal local, sem limite artificial. Licença comercial simbólica por honra para uso profissional, no modelo Obsidian. Sem paywall agressivo, sem assinatura recorrente.
