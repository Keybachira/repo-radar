#!/usr/bin/env python3
"""repo-radar — quais dos teus repositórios têm trabalho por acabar?

Varre uma pasta de projectos e mostra, de uma vez, os repos com:
  - alterações por commitar (e ficheiros novos)
  - commits por enviar (push) ou ramos que nunca foram enviados
  - stash esquecido
  - commits novos no remoto por puxar (pull)
Depois podes agir directamente: commit (smart-commit), push, pull, abrir no editor.

Só usa a biblioteca padrão.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

IGNORAR = {
    "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target",
    "AppData", "$Recycle.Bin", "Library", "Applications",
}

# ---------- apresentação ----------


def _cor(cod, txt):
    return f"\033[{cod}m{txt}\033[0m" if sys.stdout.isatty() else txt


def verde(t): return _cor("32", t)
def amarelo(t): return _cor("33", t)
def vermelho(t): return _cor("31", t)
def cinza(t): return _cor("90", t)
def negrito(t): return _cor("1", t)


def preparar_consola():
    for s in (sys.stdout, sys.stderr, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if os.name == "nt":
        os.system("")  # activa cores ANSI no terminal do Windows


# ---------- git ----------


def git(caminho, *args, timeout=30):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        ["git", "-C", str(caminho), "-c", "core.quotepath=off", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=env,
    )


@dataclass
class Repo:
    caminho: Path
    nome: str
    ramo: str = "?"
    alterados: int = 0        # em stage ou modificados
    novos: int = 0            # ficheiros novos (untracked)
    conflitos: int = 0
    ahead: int = 0
    behind: int = 0
    tem_upstream: bool = False
    tem_remote: bool = False
    sem_upstream: int = 0     # commits que não estão em nenhum remoto (ramo nunca enviado)
    stash: int = 0
    ultimo: float = 0.0
    erro: str = ""

    @property
    def sujo(self):
        return (self.alterados + self.novos + self.conflitos) > 0

    @property
    def por_enviar(self):
        if self.tem_upstream:
            return self.ahead
        return self.sem_upstream if self.tem_remote else 0

    @property
    def pendente(self):
        return self.sujo or self.por_enviar > 0 or self.stash > 0

    @property
    def atencao(self):
        return bool(self.erro) or self.pendente or self.behind > 0

    @property
    def gravidade(self):
        if self.erro or self.conflitos:
            return 0
        if self.sujo:
            return 1
        if self.por_enviar:
            return 2
        if self.stash:
            return 3
        if self.behind:
            return 4
        return 5


def analisar(caminho, nome, fetch):
    r = Repo(caminho, nome)
    try:
        if fetch:
            git(caminho, "fetch", "--quiet", timeout=25)
        s = git(caminho, "status", "--porcelain=v2", "--branch")
        if s.returncode != 0:
            linhas = s.stderr.strip().splitlines()
            r.erro = (linhas[0] if linhas else "erro do git")[:60]
            return r
        for l in s.stdout.splitlines():
            if l.startswith("# branch.head "):
                r.ramo = l[len("# branch.head "):]
            elif l.startswith("# branch.upstream"):
                r.tem_upstream = True
            elif l.startswith("# branch.ab "):
                a, b = l[len("# branch.ab "):].split()
                r.ahead, r.behind = int(a[1:]), int(b[1:])
            elif l.startswith(("1 ", "2 ")):
                if l.split(" ", 2)[1] != "..":
                    r.alterados += 1
            elif l.startswith("u "):
                r.conflitos += 1
            elif l.startswith("? "):
                r.novos += 1
        r.tem_remote = bool(git(caminho, "remote").stdout.strip())
        if not r.tem_upstream and r.tem_remote and r.ramo != "(detached)":
            c = git(caminho, "rev-list", "--count", "HEAD", "--not", "--remotes")
            if c.returncode == 0 and c.stdout.strip().isdigit():
                r.sem_upstream = int(c.stdout.strip())
        r.stash = sum(1 for l in git(caminho, "stash", "list").stdout.splitlines() if l.strip())
        t = git(caminho, "log", "-1", "--format=%ct")
        if t.returncode == 0 and t.stdout.strip().isdigit():
            r.ultimo = float(t.stdout.strip())
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        r.erro = type(e).__name__
    return r


# ---------- descoberta ----------


def encontrar_repos(raiz, profundidade):
    achados = []
    pilha = [(str(raiz), 0)]
    while pilha:
        d, n = pilha.pop()
        try:
            with os.scandir(d) as it:
                entradas = list(it)
        except OSError:
            continue
        if any(e.name == ".git" for e in entradas):
            achados.append(Path(d))
            continue  # não entra dentro de um repo
        if n >= profundidade:
            continue
        for e in entradas:
            try:
                if (e.is_dir(follow_symlinks=False) and e.name not in IGNORAR
                        and not e.name.startswith(".")):
                    pilha.append((e.path, n + 1))
            except OSError:
                pass
    return achados


# ---------- tabela ----------


def idade(ts):
    if not ts:
        return "—"
    d = (time.time() - ts) / 86400
    if d < 1:
        return "hoje"
    if d < 2:
        return "ontem"
    if d < 14:
        return f"há {int(d)} dias"
    if d < 60:
        return f"há {int(d / 7)} sem."
    if d < 365:
        return f"há {int(d / 30)} meses"
    return f"há {int(d / 365)} anos"


def _pl(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def estado_txt(r):
    if r.erro:
        return f"erro: {r.erro}"
    partes = []
    if r.conflitos:
        partes.append(_pl(r.conflitos, "em conflito", "em conflito"))
    if r.alterados:
        partes.append(_pl(r.alterados, "alterado", "alterados"))
    if r.novos:
        partes.append(_pl(r.novos, "novo", "novos"))
    if r.tem_upstream and r.ahead:
        partes.append(f"{r.ahead} por enviar")
    elif not r.tem_upstream and r.tem_remote and r.sem_upstream:
        partes.append(f"ramo não enviado ({_pl(r.sem_upstream, 'commit', 'commits')})")
    if r.behind:
        partes.append(f"{r.behind} por puxar")
    if r.stash:
        partes.append(f"{r.stash} stash")
    if not r.tem_remote:
        partes.append("sem remote")
    return ", ".join(partes) if partes else "limpo"


def cor_da_linha(r):
    if r.gravidade == 0:
        return vermelho
    if r.gravidade in (1, 2, 3):
        return amarelo
    if r.gravidade == 4:
        return cinza
    return verde


def cortar(t, n):
    return t if len(t) <= n else t[: n - 1] + "…"


def mostrar(repos, total):
    if not repos:
        print(verde("\n  Tudo limpo e enviado."))
    else:
        w_repo = min(30, max(len(r.nome) for r in repos))
        w_ramo = min(20, max(len(r.ramo) for r in repos))
        print()
        print(negrito(f"  {'#':>2}  {'Repo':<{w_repo}}  {'Ramo':<{w_ramo}}  {'Último commit':<14}  Estado"))
        for i, r in enumerate(repos, 1):
            linha = (f"  {i:>2}  {cortar(r.nome, w_repo):<{w_repo}}  {cortar(r.ramo, w_ramo):<{w_ramo}}  "
                     f"{idade(r.ultimo):<14}  {estado_txt(r)}")
            print(cor_da_linha(r)(linha))
    pend = sum(1 for r in total if r.pendente)
    atras = sum(1 for r in total if not r.pendente and r.behind)
    limpos = sum(1 for r in total if not r.atencao)
    print(cinza(f"\n  {len(total)} repos · {pend} com trabalho pendente · {atras} por actualizar · {limpos} limpos"))


# ---------- acções ----------


def abrir_editor(caminho):
    custom = os.environ.get("REPO_RADAR_EDITOR")
    exe = shutil.which(custom) if custom else None
    if not exe:
        for nome in ("zed", "code", "cursor"):
            exe = shutil.which(nome)
            if exe:
                break
    try:
        if exe:
            subprocess.Popen([exe, "."], cwd=str(caminho))
        elif os.name == "nt":
            os.startfile(str(caminho))  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(caminho)])
    except OSError as e:
        print(vermelho(f"  Não consegui abrir o editor: {e}"))


def correr(caminho, *cmd):
    return subprocess.run(list(cmd), cwd=str(caminho)).returncode


def executar(r, letra):
    print(cinza(f"\n  -> {r.nome}"))
    if letra in ("", "s"):
        print(git(r.caminho, "status", "-sb").stdout)
    elif letra == "c":
        exe = shutil.which("smart-commit")
        if exe:
            correr(r.caminho, exe)
        else:
            print(amarelo("  O smart-commit não está instalado. Instala-o ou faz o commit à mão."))
    elif letra == "p":
        if r.tem_upstream:
            correr(r.caminho, "git", "push")
        else:
            remoto = "origin" if "origin" in git(r.caminho, "remote").stdout.split() else None
            if remoto:
                correr(r.caminho, "git", "push", "-u", remoto, "HEAD")
            else:
                print(amarelo("  Sem remote 'origin' configurado."))
    elif letra == "l":
        correr(r.caminho, "git", "pull", "--ff-only")
    elif letra == "e":
        abrir_editor(r.caminho)
        print("  Aberto no editor.")


def menu(repos, total, fetch):
    ajuda = "acção: nº + letra (3c commit, 3p push, 3l pull, 3e editor, 3s estado) · r actualizar · Enter sai"
    print(cinza("  " + ajuda))
    while True:
        try:
            resp = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not resp:
            return
        if resp == "r":
            for i, r in enumerate(repos):
                repos[i] = analisar(r.caminho, r.nome, fetch)
            mostrar(repos, total)
            continue
        m = re.fullmatch(r"(\d+)\s*([cplesr]?)", resp)
        if not m or not (1 <= int(m.group(1)) <= len(repos)):
            print(amarelo("  Não percebi. Exemplo: 3c"))
            continue
        i = int(m.group(1)) - 1
        executar(repos[i], m.group(2))
        novo = analisar(repos[i].caminho, repos[i].nome, False)
        repos[i] = novo
        for j, t in enumerate(total):
            if t.caminho == novo.caminho:
                total[j] = novo
        mostrar(repos, total)


# ---------- entrada ----------


def main():
    preparar_consola()
    ap = argparse.ArgumentParser(
        prog="repo-radar",
        description="Mostra quais dos teus repositórios têm trabalho por acabar.")
    ap.add_argument("pastas", nargs="*", help="pastas com projectos (padrão: REPO_RADAR_ROOTS ou a pasta actual)")
    ap.add_argument("-d", "--profundidade", type=int, default=3, help="níveis de pastas a explorar (padrão: 3)")
    ap.add_argument("-a", "--todos", action="store_true", help="mostra também os repos limpos")
    ap.add_argument("-f", "--fetch", action="store_true", help="faz git fetch antes (mais lento, 'por puxar' fica certo)")
    ap.add_argument("-n", "--sem-menu", action="store_true", help="só lista, sem menu de acções")
    args = ap.parse_args()

    if args.pastas:
        raizes = args.pastas
    elif os.environ.get("REPO_RADAR_ROOTS"):
        raizes = [p for p in os.environ["REPO_RADAR_ROOTS"].split(os.pathsep) if p]
    else:
        raizes = ["."]

    tarefas = []
    multiplas = len(raizes) > 1
    for raiz in raizes:
        raiz = Path(raiz).expanduser().resolve()
        if not raiz.is_dir():
            print(vermelho(f"Pasta não existe: {raiz}"))
            continue
        for rp in encontrar_repos(raiz, args.profundidade):
            rel = rp.name if rp == raiz else str(rp.relative_to(raiz)).replace("\\", "/")
            tarefas.append((rp, f"{raiz.name}/{rel}" if multiplas else rel))

    if not tarefas:
        print("Não encontrei nenhum repositório git.")
        return 1

    print(cinza(f"A analisar {len(tarefas)} repos{' (com fetch)' if args.fetch else ''}..."))
    with ThreadPoolExecutor(max_workers=8) as ex:
        total = list(ex.map(lambda t: analisar(t[0], t[1], args.fetch), tarefas))

    ordenados = sorted(total, key=lambda r: (r.gravidade, -r.ultimo))
    visiveis = [r for r in ordenados if args.todos or r.atencao]
    mostrar(visiveis, total)

    if visiveis and not args.sem_menu and sys.stdin.isatty():
        print()
        menu(visiveis, total, args.fetch)
    return 0


def _entrada():
    try:
        return main()
    except KeyboardInterrupt:
        print("\nInterrompido.")
        return 130


if __name__ == "__main__":
    sys.exit(_entrada())