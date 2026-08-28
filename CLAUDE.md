# dedup-engine — contexto do projeto

Motor CLI sob **Obsn Studios**. Proprietário, privado.

## Custo do erro

Apagar o original é **irreversível**. Este é o produto da suíte com o erro mais caro em termos de dado perdido.

## Invariantes

1. **O motor isola, nunca apaga.** Remoção é sempre um passo separado e explícito do usuário.
2. **Toda escolha de representante é registrada com o motivo.** Sem isso, não dá para auditar o que foi descartado.
3. **Agnóstico a nome de arquivo.** Nome é lixo depois de recuperação de disco; só o binário conta.
4. **Falha de I/O não derruba a varredura.** Arquivo bloqueado ou sem permissão vira registro de erro, não exceção fatal.
5. **Escreve em `duplicatas`, lê `arquivos`.** Não toca em `sinais` nem em `veredito`.

## Escala

Centenas de milhares de arquivos, HDs externos incluídos. Triagem por tamanho antes de qualquer hash — a maioria dos arquivos morre nessa peneira sem custar I/O.

## Histórico

A implementação de referência está em `C:\CLAUDE\dedup_fase1.py` … `dedup_fase8.py` — oito iterações, arquivo morto. Reescrever a partir do que ficou de pé, não copiar.
