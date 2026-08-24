# Mangut Sorbet · Feedbacks

Pesquisa de satisfação automatizada, com foco em melhorar o produto a partir do
que o cliente responde.

> Projeto de estudo. A sorveteria é um cenário fictício e os dados são de teste.
> O código roda de verdade, ponta a ponta.

Uma sorveteria montou um quiosque no Ibirapuera e resolveu apostar em sabores
novos, pensados para o gosto do paulistano. Eles queriam saber se estavam
acertando no sabor, na textura, no preço. O caixa não responde isso. Venda alta
pode ser só curiosidade, e quem não gostou quase nunca volta para reclamar.

Então montei essa automação. Um dia depois da compra o cliente recebe um link só
dele, dá uma nota de 0 a 10 e escreve o que quiser em 30 segundos. A resposta cai
numa planilha na hora e, toda segunda, vira um relatório por e-mail com o NPS, a
nota média e os assuntos que mais apareceram nos comentários.

`n8n` · `Google Sheets` · `Gemini` · `JavaScript` · `Python` · `SMTP`

São três workflows, um formulário e nenhuma ferramenta paga. Tem 91 testes
automatizados, incluindo uma suíte que valida o desenho dos fluxos antes de
importar no n8n. O passo a passo de instalação está no
[`GUIA_SETUP.md`](GUIA_SETUP.md).

---

## 1. O convite

A cada 15 minutos o fluxo lê a aba `vendas`, separa quem comprou há mais de 24
horas e ainda não recebeu convite, gera um token de 24 caracteres para cada um e
manda o e-mail. Depois grava o token de volta na planilha, que é como o fluxo
sabe que já mandou.

![Workflow 1 no n8n](docs/fluxo-1.png)

Deixei o e-mail bem curto. Uma frase, um botão, e o link em texto embaixo para o
caso de o botão não funcionar no cliente de e-mail da pessoa.

![E-mail de convite](docs/email_convite.png)

A espera de 24 horas foi de propósito. Se o convite sair logo depois do
pagamento, o cliente ainda nem provou o sorvete, e a nota não quer dizer nada.

---

## 2. O formulário

O link do e-mail cai num webhook GET. O n8n procura o token na planilha e devolve
a página já com o nome e o sabor dentro do HTML. Não tem uma segunda requisição
buscando esses dados depois.

![Workflow 2 no n8n](docs/fluxo-2.png)

Comecei fazendo do jeito comum, com a página buscando os dados por `fetch` depois
de carregar, e travei no CORS. Passei um tempo tentando configurar cabeçalho até
perceber que dava para o próprio n8n devolver a página pronta. Aí o problema
sumiu junto. A página passou a sair da mesma origem dos webhooks, e ainda
economizou uma requisição e o efeito de placeholder piscando na tela.

![Formulário](docs/formulario.png)

O cliente não digita nada que a sorveteria já sabe. Nome, sabor e telefone vêm da
venda, então a pergunta é *"Oi, Camila, que tal o sorvete?"* em vez de pedir para
ele se identificar.

O texto muda conforme a nota. Quem dá 3 lê *"Poxa, desculpa por isso"* e o
comentário passa a ser obrigatório. Quem dá 10 lê *"Que ótimo saber disso!"*.
Achei que isso ajudaria a trazer mais comentário escrito de quem teve problema,
que é justamente quem costuma não escrever nada.

Cada situação tem uma tela própria. Link inválido, já respondido, carregando,
erro no envio e sucesso. Na tela de erro eu aviso que as respostas continuam ali,
porque a primeira versão apagava tudo e era frustrante de testar.

A escala de 0 a 10 é um `radiogroup` que funciona com as setas do teclado e tem
`aria-label` em cada opção. Também tomei o cuidado de nunca usar só cor para
indicar alguma coisa. Toda faixa de nota vem com texto junto.

---

## 3. O relatório

Toda segunda às 9h o fluxo lê as respostas que ainda não foram analisadas,
calcula as métricas em JavaScript, manda só os comentários para o Gemini e monta
o e-mail.

![Workflow 3 no n8n](docs/fluxo-3.png)

![Relatório semanal](docs/relatorio_semanal.png)

A IA não calcula nada. NPS, média e contagem de promotores e detratores são feitos
em JavaScript. Deixei o modelo só com o que ele faz bem, que é resumir, agrupar
assunto e classificar sentimento. Se um número vier errado no relatório, ninguém
confia no resto.

A chamada usa o `responseSchema` do Gemini, então a resposta já chega como JSON
estruturado. Na primeira versão eu tentei extrair com regex de um texto solto e
quebrava toda hora.

Se a IA falhar, o relatório sai mesmo assim, com as métricas e o motivo do erro
no lugar do resumo. Isso salvou muito tempo de depuração. Enquanto a mensagem era
genérica, eu não fazia ideia se o problema era a chave, a cota ou o modelo.

Para a IA vai o mínimo, só nota, sabor e comentário. Nome, e-mail e telefone não
saem da planilha, e tem teste verificando isso.

---

## Algumas decisões

**A planilha manda, não o navegador.** O que chega no POST eu trato como dado não
confiável. Nome, e-mail e sabor gravados vêm sempre da linha da venda, então não
dá para alguém mandar uma resposta em nome de outra pessoa.

**Cada recusa tem um código HTTP.** Token que não existe responde 404, resposta
repetida responde 409, nota fora da faixa responde 400. O robô que preenche o
campo escondido recebe 200, porque avisar que ele foi pego só ajudaria ele a
tentar de novo.

**O token é sorteado e guardado, não assinado.** Cada convite gera uma string
aleatória que vira a chave de busca. Dá para revogar apagando a célula e não
depende de nenhum segredo no código.

**Os JSONs dos workflows são gerados por script.** `tests/gerar_workflows.py`
monta os 41 nodes e embute o `site/formulario.html` na hora de gerar. Fiz assim
porque editar JSON de 2 mil linhas na mão é pedir para errar, e porque as colunas
da planilha ficam declaradas em um lugar só. As mesmas alimentam o schema dos
nodes e a planilha modelo, então elas não saem de sincronia.

---

## Editando a página

O `site/formulario.html` está dividido em seis seções comentadas. Duas delas dá
para mexer sem saber programar. Uma tem todas as frases da página em um objeto
só, e a outra tem as cores e tamanhos em variáveis CSS.

Depois de editar, é só rodar `make workflow` para embutir a nova versão no
workflow 2.

---

## Rodando

Precisa de n8n rodando local, uma conta Google e uma chave gratuita do Gemini.

```bash
git clone <seu-repo> && cd feedback-pos-compra
make planilha        # gera planilha/modelo_planilha.xlsx
```

1. Suba `planilha/modelo_planilha.xlsx` no Drive e abra como Planilhas Google
2. Importe os três arquivos de `workflows/` no n8n
3. Em cada workflow, abra o node **Configuração** e cole o ID da planilha
4. Conecte as credenciais do Google Sheets, do SMTP e do Gemini
5. Rode o workflow 1 na mão e o convite chega no seu e-mail

Os detalhes de cada credencial estão no [`GUIA_SETUP.md`](GUIA_SETUP.md).

Dá para ver a página sem configurar nada.

```bash
make demo    # sobe um n8n falso e serve o formulário em localhost:8080
```

Os tokens `demo-1`, `demo-2` e `demo-usada` cobrem todas as telas.

---

## Testes

```
$ make testar

WORKFLOW 1 · Selecionar Pendentes
  ✓ pula quem já recebeu convite
  ✓ pula compra recente (janela de 24h)
  ✓ entende data no formato brasileiro dd/mm/aaaa
WORKFLOW 2 · Renderizar Página
  ✓ nome de produto com </script> é escapado (não quebra a página)
WORKFLOW 2 · Validar Envio e Decidir
  ✓ robô não grava, mas recebe 200 (não revela que foi detectado)
WORKFLOW 3 · Montar Prompt
  ✓ NPS calculado em JavaScript, não pela IA (-10)
  ✓ e-mail do cliente NÃO é enviado para a IA
WORKFLOW 3 · Consolidar Análise
  ✓ métricas saem mesmo com a IA fora do ar
```

São 91 verificações e rodam em menos de um segundo, sem planilha, sem SMTP e sem
chave de IA. O `tests/test_code_nodes.mjs` executa o JavaScript de verdade dos
nodes `Code` com `$input`, `$json` e `$()` simulados.

O `tests/test_estrutura.py` confere o desenho do fluxo. Ele verifica se toda
conexão aponta para um node que existe, se todo `$('X')` referencia um node que
vem antes no caminho, se sobrou node solto e se todo webhook chega em um Respond
to Webhook.

Essa segunda suíte eu só escrevi depois de perder um tempão com um bug. O node
`Configuração` estava ligado só ao webhook GET, então na rota POST ele nunca
rodava e todas as expressões que dependiam dele falhavam. O erro só aparecia três
nodes depois, disfarçado de "token inválido", e eu fiquei procurando no lugar
errado. Agora um teste pega isso em segundos.

---

## Estrutura

```
site/formulario.html            a página (embutida no workflow 2 na geração)
workflows/                      os três JSONs prontos para importar
planilha/modelo_planilha.xlsx   abas vendas · respostas · analise · painel
scripts/gerar_planilha.py       gera a planilha modelo
tests/gerar_workflows.py        gerador dos workflows
tests/test_code_nodes.mjs       testes da lógica dos nodes Code
tests/test_estrutura.py         testes do desenho do fluxo
tests/n8n_falso.py              webhooks simulados para desenvolvimento
Makefile                        `make ajuda` lista tudo
```

| Aba | Quem preenche | Para quê |
|---|---|---|
| `vendas` | a loja + workflow 1 | fila de convites; `token` e `convite_enviado_em` controlam o que já foi enviado |
| `respostas` | workflow 2 + workflow 3 | uma linha por avaliação, com nota, classificação NPS, comentário e depois sentimento e temas |
| `analise` | workflow 3 | uma linha por execução: NPS do período, resumo da IA, temas e ações |
| `painel` | fórmulas | NPS, nota média e distribuição ao vivo, sem depender de workflow nenhum |

---

## O que eu faria diferente

**Google Sheets não é banco.** Passando de alguns milhares de respostas as
leituras ficam lentas, e não tem transação. Em teoria, duas respostas do mesmo
token ao mesmo tempo poderiam gravar duas linhas. Para volume de verdade eu
usaria Postgres.

**O token não expira.** Quem guardar o link consegue abrir a página depois. Não
consegue responder de novo, mas um campo `expira_em` na aba `vendas` resolveria
direito.

**Nota baixa deveria avisar na hora.** Hoje o cliente insatisfeito só aparece no
relatório de segunda. Um `IF` depois de gravar na planilha já resolveria, e é o
primeiro item da lista abaixo.

**O n8n precisa estar acessível pelo cliente.** Em `localhost` o link do e-mail só
abre na minha máquina. Para valer de verdade precisa de túnel ou de hospedar o
n8n.

---

## Próximos passos

- [ ] Avisar na hora quando a nota for ≤ 6, com o telefone do cliente junto
- [ ] Lembrete automático para quem não respondeu em 3 dias
- [ ] Trocar Google Sheets por Postgres e plugar um BI
- [ ] Webhook `POST /nova-venda` para a loja empurrar a venda em vez de esperar o polling
- [ ] Comparar temas entre semanas, para ver o que está subindo

---

Feito por José Aguiar.
[LinkedIn](https://www.linkedin.com/in/ozzeaguiar) · [GitHub](https://github.com/Ozeaguiar)
