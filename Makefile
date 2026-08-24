.DEFAULT_GOAL := ajuda
SHELL := /bin/bash

ajuda:  ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

planilha:  ## Gera planilha/modelo_planilha.xlsx (suba no Google Drive)
	python3 scripts/gerar_planilha.py

workflow:  ## Regera os 3 JSONs, embutindo site/formulario.html no workflow 2
	python3 tests/gerar_workflows.py

testar:  ## Roda a suíte de testes (lógica dos nodes Code + estrutura do grafo)
	node tests/test_code_nodes.mjs
	python3 tests/test_estrutura.py

demo:  ## Sobe o n8n falso + o formulário em http://localhost:8080/formulario.html?t=demo-1
	@echo "Tokens de teste: demo-1 · demo-2 · demo-usada (já respondida)"
	python3 tests/n8n_falso.py

tudo: workflow planilha testar  ## Regera tudo e roda os testes

.PHONY: ajuda planilha workflow testar demo tudo
