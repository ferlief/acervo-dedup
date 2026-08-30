# dedup-engine

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

Grava na tabela `duplicatas` do `acervo-index`. Também exporta relatório JSON com `duplicate_groups`, espaço recuperável e o representante de cada grupo.

## Estado

**Esqueleto.** Nada do descrito acima está implementado neste repositório — o texto define o desenho, não o que já roda.

A implementação de referência são as oito iterações do protótipo de origem, mantido fora deste repositório. A reescrita parte do que ficou de pé, não da cópia.

## Licença e monetização

Código fechado, sob Obsn Studios.

Gratuito para uso pessoal local, sem limite artificial. Licença comercial simbólica por honra para uso profissional, no modelo Obsidian. Sem paywall agressivo, sem assinatura recorrente.
