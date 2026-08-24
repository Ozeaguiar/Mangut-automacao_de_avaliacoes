"""
Testes estruturais dos workflows — checam o GRAFO, não a lógica.

O bug que motivou este arquivo: o node `Configuração` estava ligado apenas na
rota do webhook GET, mas os nodes de planilha da rota POST liam
`$('Configuração').first().json.PLANILHA_ID`. Numa requisição POST o node
`Configuração` nunca executava, a expressão falhava, e o sintoma aparecia lá na
frente como "token_invalido" — três nodes depois da causa real.

A regra violada é simples e vale para qualquer workflow do n8n:

    se um node N usa $('X'), então X precisa ser ANCESTRAL de N no grafo.

Um node só tem dados quando já executou, e só executa antes de N se houver um
caminho dirigido de X até N.

Uso:  python tests/test_estrutura.py
"""

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

TIPOS_GATILHO = ("Trigger", "webhook", "manualTrigger")

falhas: list[str] = []


def afirmar(condicao: bool, descricao: str):
    print(("  ✓ " if condicao else "  ✗ FALHOU: ") + descricao)
    if not condicao:
        falhas.append(descricao)


def carregar(arquivo: Path) -> dict:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def arestas(wf: dict) -> dict[str, set[str]]:
    saida: dict[str, set[str]] = {n["name"]: set() for n in wf["nodes"]}
    for origem, ligacoes in wf["connections"].items():
        for grupo in ligacoes.get("main", []):
            for destino in grupo or []:
                saida.setdefault(origem, set()).add(destino["node"])
    return saida


def ancestrais(nome: str, arestas_por_no: dict[str, set[str]]) -> set[str]:
    """Todos os nodes a partir dos quais existe caminho dirigido até `nome`."""
    reverso: dict[str, set[str]] = {}
    for origem, destinos in arestas_por_no.items():
        for d in destinos:
            reverso.setdefault(d, set()).add(origem)

    vistos: set[str] = set()
    pilha = list(reverso.get(nome, set()))
    while pilha:
        atual = pilha.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        pilha.extend(reverso.get(atual, set()))
    return vistos


def referencias(node: dict) -> set[str]:
    """Nodes citados via $('Nome') nos parâmetros — ignorando o HTML embutido."""
    params = json.loads(json.dumps(node.get("parameters", {}), ensure_ascii=False))
    if node["name"] == "Configuração":
        for a in params.get("assignments", {}).get("assignments", []):
            if a.get("name") == "PAGINA_HTML":
                a["value"] = ""       # o $() do HTML é do navegador, não do n8n
    return set(re.findall(r"\$\('([^']+)'\)", json.dumps(params, ensure_ascii=False)))


def gatilhos(wf: dict) -> list[str]:
    return [n["name"] for n in wf["nodes"] if any(t in n["type"] for t in TIPOS_GATILHO)]


def alcancaveis(inicio: str, arestas_por_no: dict[str, set[str]]) -> set[str]:
    vistos, pilha = set(), [inicio]
    while pilha:
        atual = pilha.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        pilha.extend(arestas_por_no.get(atual, set()))
    return vistos


def main():
    arquivos = sorted((RAIZ / "workflows").glob("*.json"))
    if not arquivos:
        sys.exit("Nenhum workflow encontrado — rode `python tests/gerar_workflows.py` antes.")

    for arq in arquivos:
        wf = carregar(arq)
        print(f"\n{arq.name}")
        nomes = {n["name"] for n in wf["nodes"]}
        grafo = arestas(wf)

        # 1. toda conexão aponta para um node existente
        destinos = {d for ds in grafo.values() for d in ds}
        afirmar(destinos <= nomes, f"todas as conexões apontam para nodes existentes")

        # 2. REGRA PRINCIPAL: $('X') só é válido se X for ancestral
        problemas = []
        for node in wf["nodes"]:
            anc = ancestrais(node["name"], grafo)
            for ref in referencias(node):
                if ref not in nomes:
                    problemas.append(f"{node['name']} → $('{ref}') não existe")
                elif ref not in anc:
                    problemas.append(
                        f"{node['name']} → $('{ref}') não é ancestral "
                        f"(não terá dados quando este node rodar)"
                    )
        afirmar(not problemas, "toda referência $('X') aponta para um node ancestral")
        for p in problemas:
            print(f"      · {p}")

        # 3. todo node não-gatilho é alcançável a partir de algum gatilho
        alc = set()
        for g in gatilhos(wf):
            alc |= alcancaveis(g, grafo)
        orfaos = nomes - alc
        afirmar(not orfaos, f"nenhum node órfão{'' if not orfaos else f' ({orfaos})'}")

        # 4. workflows com Respond to Webhook precisam responder em toda rota
        respondem = [n["name"] for n in wf["nodes"] if n["type"].endswith("respondToWebhook")]
        if respondem:
            webhooks = [n for n in wf["nodes"] if n["type"].endswith(".webhook")]
            for w in webhooks:
                apartir = alcancaveis(w["name"], grafo)
                afirmar(any(r in apartir for r in respondem),
                        f"o webhook '{w['name']}' alcança pelo menos um Respond to Webhook")

    print("\n" + "=" * 64)
    if falhas:
        print(f"{len(falhas)} verificação(ões) falharam.")
        sys.exit(1)
    print("Estrutura dos workflows OK.")


if __name__ == "__main__":
    main()
