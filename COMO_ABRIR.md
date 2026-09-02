# Como abrir o acervo-dedup

Este arquivo é o passo a passo sem jargão. Se algo aqui não bater com o que
você vê na tela, é o arquivo que está errado, não você.

---

## O jeito mais curto

Tem um atalho chamado **acervo-dedup** na sua Área de Trabalho.
**Clique duas vezes nele.** Só isso.

Uma janela cinza-escura abre, com o nome `acervo·dedup` no canto superior
esquerdo e quatro etapas numeradas na lateral. Se você viu isso, deu certo.

---

## Se o atalho sumir

O programa mora em:

```
C:\Users\ferlief\dev\workspace\acervo-dedup\dist\acervo-dedup\
```

Dentro dessa pasta tem **dois arquivos parecidos**. A diferença importa:

| arquivo | clicar? |
|---|---|
| `acervo-dedup-gui` | **Sim.** É este. Abre a janela. |
| `acervo-dedup` | Não. É o motor. Sozinho ele pisca e fecha. |

O Windows costuma esconder o `.exe` do fim do nome. Se os dois aparecerem
com o mesmo ícone, olhe o final do nome: **o que termina em `-gui` é o
certo**.

Para recriar o atalho: clique com o botão direito em `acervo-dedup-gui` →
*Mostrar mais opções* → *Enviar para* → *Área de trabalho (criar atalho)*.

---

## Três coisas que dão errado com todo mundo

**1. Clicar no arquivo de dentro do `.zip`.**
Se você abriu o `acervo-dedup-windows.zip` com dois cliques, o Windows só
está te *mostrando* o conteúdo — não descompactou nada. Programa aberto daí
não funciona. Descompacte primeiro: botão direito no zip → *Extrair tudo*.

**2. Separar os dois arquivos.**
`acervo-dedup-gui` e `acervo-dedup` precisam ficar na **mesma pasta**, junto
com a pasta `_internal`. A janela procura o motor do lado dela. Não mova, não
renomeie, não copie só um.

**3. Avisos do Windows.**
Pode aparecer uma tela azul dizendo *"O Windows protegeu o seu computador"*.
Isso acontece com todo programa novo que não pagou assinatura digital — não é
sinal de problema. Clique em **Mais informações** e depois em **Executar
assim mesmo**.

---

## O que fazer depois que a janela abrir

A lateral tem quatro etapas. **As três últimas ficam apagadas até a primeira
terminar** — é de propósito, para não ter como fazer fora de ordem.

### 1. Varredura

Clique no botão amarelo **Iniciar varredura**. O texto preto embaixo vai
enchendo de linhas — é o programa contando o que está fazendo. Pode demorar
minutos num acervo grande. **Nada é movido nesta etapa.**

> **Se aparecer um erro vermelho falando de banco não encontrado:** falta
> rodar o `acervo` antes. Os dois programas trabalham em dupla — o `acervo`
> olha as fotos e anota o que viu; o `acervo-dedup` lê essas anotações. Sem a
> primeira parte, a segunda não tem o que ler.

### 2. Resultado

Mostra quanto espaço dá para recuperar, dividido em duas caixas:

- **quarentena** (amarelo) — cópias **idênticas**, byte por byte. Aqui não
  existe engano possível.
- **revisão** (laranja) — fotos **parecidas**, não idênticas. Aqui o programa
  pode errar: pode ser uma rajada de fotos diferentes.

### 3. Conferência

A lista dos grupos. Cada um mostra qual foto **fica** e por quê. Vale abrir
alguns dos laranjas e olhar — são os que erram.

### 4. Isolar

Comece sempre por **Simular**. Ela lista o que *seria* movido sem tocar em
nada. Se a lista fizer sentido, aí sim **Mover de fato** — e ele vai te pedir
para digitar a palavra `ISOLAR`, de propósito.

---

## O que o programa nunca faz

**Nunca apaga nada.** Não existe botão de apagar em lugar nenhum. Ele só
*move* arquivos para duas pastas separadas. Apagar de vez, depois de você
conferir, é uma decisão sua, fora do programa.

## Como fechar

Feche a janela no X. O programa encerra junto — não fica nada rodando
escondido.
