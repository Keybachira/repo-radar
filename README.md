# repo-radar

**Em que repos deixei trabalho por acabar?** Varre a tua pasta de projectos e mostra, de uma vez, o que ficou por commitar, por enviar ou esquecido num stash. Depois podes agir ali mesmo.

## Instalar (fica no PATH)

```bash
cd repo-radar
uv tool install --editable .
```

O ficheiro principal tem de se chamar `repo_radar.py` (com underscore). Abre um terminal novo depois de instalar.

Para não escreveres a pasta de cada vez, define onde estão os teus projectos:

```powershell
setx REPO_RADAR_ROOTS "C:\Projects"        # Windows (várias pastas: separa com ;)
```
```bash
export REPO_RADAR_ROOTS="$HOME/projects"   # Linux/macOS (várias pastas: separa com :)
```

## Usar

```bash
repo-radar                  # lista só os repos com algo pendente + menu de acções
repo-radar C:\Projects      # numa pasta específica
repo-radar -a               # mostra também os repos limpos
repo-radar -f               # faz git fetch antes (mais lento, mas "por puxar" fica certo)
repo-radar -n               # só lista, sem menu (bom para scripts)
repo-radar -d 5             # explora até 5 níveis de pastas (padrão: 3)
```

## O que mostra

```
   #  Repo            Ramo     Último commit   Estado
   1  flowty          main     hoje            3 alterados, 2 novos, 1 por enviar
   2  xl              feature  ontem           ramo não enviado (4 commits)
   3  vnbn-gestao     main     há 5 dias       1 stash
   4  acacia          main     há 2 sem.       2 por puxar
```

| Estado | Significa |
|---|---|
| `N alterados` | ficheiros modificados ou em stage, ainda sem commit |
| `N novos` | ficheiros novos que o git ainda não conhece |
| `N em conflito` | merge/rebase com conflitos por resolver |
| `N por enviar` | commits locais que ainda não fizeste push |
| `ramo não enviado` | o ramo nunca foi enviado para o remoto |
| `N por puxar` | há commits novos no remoto (precisas de pull) |
| `N stash` | alterações guardadas e esquecidas |
| `sem remote` | repo só local, sem cópia em lado nenhum |

Ordem: primeiro o mais urgente (conflitos, alterações), depois commits por enviar, stash e por último o que só precisa de pull. Dentro de cada grupo, o mais recente primeiro.

## Menu de acções

Depois da lista, escreve o número do repo e uma letra:

| Acção | Faz |
|---|---|
| `3c` | corre o [smart-commit](https://github.com/Keybachira/ab-commiter) nesse repo (se o tiveres instalado) |
| `3p` | `git push` (ou `push -u origin HEAD` se o ramo ainda não foi enviado) |
| `3l` | `git pull --ff-only` (nunca cria merges sozinho) |
| `3e` | abre no editor (`zed`, `code` ou `cursor`; muda com `REPO_RADAR_EDITOR`) |
| `3s` | mostra o `git status` desse repo |
| `r` | actualiza a lista toda |

Depois de cada acção, o repo é reanalisado e a tabela volta a aparecer.

## Notas

- Só usa a biblioteca padrão, e analisa vários repos em paralelo.
- Sem `-f`, o "por puxar" reflecte o último fetch que fizeste. Com `-f` fala com o servidor, e pode demorar com muitos repos ou ligação lenta.
- Ignora `node_modules`, `.venv`, `dist`, `build` e pastas escondidas, e não entra dentro de um repo à procura de outros.
- Um repo com erro (por exemplo "dubious ownership") aparece a vermelho com a mensagem do git.
