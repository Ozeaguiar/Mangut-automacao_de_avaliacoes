# Guia de setup

Do zero até o primeiro e-mail chegando na sua caixa. Uns 30 minutos, sendo a
maior parte cliques no console do Google.

Você vai precisar de: n8n rodando local, uma conta Google e uma conta Gmail com
verificação em duas etapas ativada.

---

## Etapa 1 · A planilha

```bash
python scripts/gerar_planilha.py     # ou: make planilha
```

1. Suba `planilha/modelo_planilha.xlsx` no Google Drive.
2. Clique com o botão direito → **Abrir com → Planilhas Google**.
   (Isso converte o arquivo; é a planilha convertida que você vai usar.)
3. Na aba `vendas`, troque os e-mails de exemplo pelo **seu** — é assim que você
   vai testar o fluxo recebendo os convites.
4. Copie o **ID da planilha** da URL. Ele é o trecho entre `/d/` e `/edit`:

```
https://docs.google.com/spreadsheets/d/1AbC...XyZ/edit#gid=0
                                       └────┬────┘
                                     esse é o ID
```

As abas são `leia-me`, `painel`, `vendas`, `respostas` e `analise`. Não renomeie
colunas nem apague a linha 1 — os nodes do Google Sheets casam pelo nome do
cabeçalho e reclamam de "schema" se algo mudar.

## Etapa 2 · Acesso do n8n à planilha (conta de serviço)

Existem dois caminhos no n8n: OAuth2 e conta de serviço. Conta de serviço tem
bem menos passos — não pede tela de consentimento nem URI de redirecionamento — e
é o que os workflows já vêm configurados para usar.

1. Abra <https://console.cloud.google.com> e crie um projeto (nome livre).
2. **APIs e serviços → Biblioteca** → procure **Google Sheets API** → **Ativar**.
3. **APIs e serviços → Credenciais → Criar credenciais → Conta de serviço**.
   Dê um nome (`n8n-feedback`), avance e conclua.
4. Clique na conta criada → aba **Chaves** → **Adicionar chave → Criar nova chave
   → JSON**. Um arquivo é baixado. Abra num editor de texto.
5. Desse JSON você precisa de dois campos:
   - `client_email` — algo como `n8n-feedback@seu-projeto.iam.gserviceaccount.com`
   - `private_key` — o bloco que começa com `-----BEGIN PRIVATE KEY-----`
6. No n8n: **Credentials → Add credential → Google Service Account API**.
   Cole o e-mail em *Service Account Email* e a chave inteira em *Private Key*,
   incluindo as linhas BEGIN e END. Deixe a chave **Impersonate a User**
   desligada.
7. Volte na planilha, clique em **Compartilhar** e adicione aquele
   `client_email` como **Editor**.

O passo 7 é o mais esquecido. Sem ele o n8n autentica normalmente e mesmo assim
recebe *"The caller does not have permission"*.

## Etapa 3 · Enviar e-mail (SMTP do Gmail)

O Gmail não aceita mais a senha da conta em aplicativos externos. Você precisa de
uma senha de app, que só existe com verificação em duas etapas ligada.

1. <https://myaccount.google.com/security> → ative a **verificação em duas etapas**.
2. Na mesma página, procure **Senhas de app** → crie uma (nome: `n8n`).
3. Copie os 16 caracteres gerados.
4. No n8n: **Credentials → Add credential → SMTP**:

| Campo | Valor |
|---|---|
| Host | `smtp.gmail.com` |
| Port | `465` |
| SSL/TLS | ligado |
| User | seu e-mail completo do Gmail |
| Password | a senha de app de 16 caracteres |

A porta e o SSL andam juntos: **465 exige SSL/TLS ligado**, **587 exige
desligado**. Trocar um sem o outro dá timeout ou erro de conexão.

Limite do Gmail comum: cerca de 500 e-mails por dia. Suficiente para portfólio e
para uma loja pequena. Acima disso, troque por Resend ou SendGrid.

## Etapa 4 · Chave do Gemini

1. Abra <https://aistudio.google.com/apikey> → **Create API key**. É gratuito e
   não pede cartão.
2. No n8n: **Credentials → Add credential → Google Gemini(PaLM) Api**.
3. Cole a chave em *API Key* e deixe o *Host* como
   `https://generativelanguage.googleapis.com`.

Essa credencial é nativa do n8n e tem teste de conexão embutido — mais simples
que montar um Header Auth na mão. A chave fica na credencial, nunca no node
`Configuração`, então não vai junto quando você exportar o workflow para o
GitHub.

## Etapa 5 · Importar os workflows

No n8n: **Workflows → ⋯ → Import from File**, um de cada vez:

1. `workflows/1_convite_por_email.json`
2. `workflows/2_formulario_e_respostas.json`
3. `workflows/3_analise_com_ia.json`

Em cada workflow, abra o node **Configuração** e preencha:

| Campo | O que colocar |
|---|---|
| `PLANILHA_ID` | o ID copiado na etapa 1 |
| `EMPRESA` | o nome que aparece no e-mail e no formulário |
| `LOGO` | *(workflow 2)* URL pública da logo, ou deixe vazio |
| `URL_FORMULARIO` | *(workflow 1)* `http://localhost:5678/webhook/feedback` |
| `REMETENTE` | seu e-mail do Gmail |
| `DESTINATARIO_RELATORIO` | *(workflow 3)* quem recebe o relatório semanal |
| `MODELO_GEMINI` | *(workflow 3)* `gemini-3.6-flash` |

Depois, conecte as credenciais:

- **Google Sheets** — em todos os nodes de planilha. São 2 no workflow 1, **5 no
  workflow 2** (`Buscar Venda`, `Buscar Resposta`, `Buscar Venda (envio)`,
  `Buscar Resposta (envio)`, `Gravar na Planilha`) e 3 no workflow 3.
- **SMTP** — nos nodes `Enviar Convite` e `Enviar Relatório`.
- **Google Gemini(PaLM) Api** — no node `Gemini · Analisar`.

Sobre o modelo: chaves criadas recentemente não têm acesso aos modelos antigos.
Se aparecer *"is no longer available to new users"*, a própria mensagem de erro
diz qual usar no lugar. A lista atual está em
<https://ai.google.dev/gemini-api/docs/models>.

## Etapa 6 · Publicar o workflow 2

Cada webhook do n8n tem duas URLs:

| | URL | Quando funciona |
|---|---|---|
| Teste | `/webhook-test/feedback` | só depois de clicar em *Execute workflow*, e só para **uma** chamada |
| Produção | `/webhook/feedback` | sempre, mas só com o workflow publicado |

O link do e-mail aponta para a URL de produção. Abra o workflow 2 e clique em
**Publish** (nas versões mais antigas do n8n é a chave **Active**, no canto
superior direito). Sem isso o cliente recebe *"webhook not registered"*.

Se você já tinha uma versão antiga desse workflow, **apague de vez** em vez de
arquivar. Workflow arquivado continua segurando o path do webhook, e a versão
nova não consegue registrar.

## Etapa 7 · Primeiro teste

1. Abra o **workflow 1** e clique em **Execute workflow**.
2. Em alguns segundos o convite chega no e-mail que você colocou na aba `vendas`.
   - Não chegou? Confira a aba `vendas`: se `convite_enviado_em` foi preenchido,
     o envio saiu e o problema está na entrega (olhe o spam). Se ficou vazio,
     olhe o erro na execução do n8n.
   - As linhas de exemplo têm `data_compra` de 2 a 3 dias atrás justamente para
     passarem pela janela de 24 horas.
3. Clique no botão do e-mail. A página abre com seu nome e o produto.
4. Dê uma nota, escreva um comentário e envie.
5. Confira a aba `respostas`: a linha está lá. A aba `painel` já mostra o NPS.
6. Abra o link de novo: agora aparece *"você já respondeu"*.
7. Rode o **workflow 3** manualmente. O relatório chega por e-mail.

## Etapa 8 · Fazer o link funcionar fora da sua máquina

Enquanto `URL_FORMULARIO` apontar para `localhost`, o link só abre no seu
computador. Para um teste real ou uma demo no celular, o caminho recomendado é
**Cloudflare Tunnel** ou hospedar o n8n num servidor, definindo a variável de
ambiente `WEBHOOK_URL` com o endereço público.

O n8n também tem um túnel próprio (`n8n start --tunnel`), mas ele é só para
desenvolvimento: a URL muda a cada reinício e reiniciar o n8n com parâmetros
diferentes dos originais é uma boa forma de perder a configuração. Se for usar,
**faça backup do volume antes**:

```bash
docker run --rm -v n8n_data:/dados -v "$PWD":/backup alpine \
  tar czf /backup/n8n_backup.tar.gz -C /dados .
```

---

## Desenvolvendo o formulário sem tocar no n8n

```bash
make demo
```

Sobe um n8n falso (`tests/n8n_falso.py`) que responde os mesmos webhooks e serve
a página em <http://localhost:8080/formulario.html?t=demo-1>. Três tokens:

- `demo-1` e `demo-2` — clientes que ainda não responderam
- `demo-usada` — cliente que já respondeu (tela de repetição)
- qualquer outra coisa — tela de link inválido

Editou `site/formulario.html`? Rode `make workflow` para embutir a nova versão no
workflow 2.

Para atualizar a página no n8n você tem dois caminhos. Reimportar o JSON é o
seguro. Colar o HTML direto no campo `PAGINA_HTML` do node `Configuração`
funciona e evita reconectar as credenciais, mas o valor passa de 30 mil
caracteres e pode truncar na colagem — se a página ficar presa na tela de
carregamento, foi isso.

---

## Solução de problemas

**`The caller does not have permission`**
Você não compartilhou a planilha com o e-mail da conta de serviço. Etapa 2,
passo 7.

**`Webhook not registered for path feedback`**
O workflow 2 não está publicado, ou o link aponta para `/webhook-test/` sem uma
execução de teste rodando. Etapa 6.

**O campo *Column* do node Google Sheets apaga sozinho**
Comportamento conhecido: o seletor de coluna tenta listar as colunas em tempo de
edição e não consegue, porque o ID da planilha vem de uma expressão. Por isso os
workflows leem a aba inteira e fazem o casamento em JavaScript — não configure
filtro no node.

**A página abre em branco / mostra o HTML como texto**
O node **Responder HTML** perdeu o cabeçalho `Content-Type: text/html`. Confira
em *Options → Response Headers*.

**A página fica travada na tela de carregamento**
O HTML em `PAGINA_HTML` está incompleto, quase sempre por colagem truncada.
Reimporte o workflow. Depois de 5 segundos a própria página desiste e mostra a
tela de link inválido, em vez de ficar no esqueleto para sempre.

**Sempre cai em "este link não é mais válido"**
O token da URL não bate com nenhuma linha da coluna `token` na aba `vendas`.
Compare o que está na planilha com o que está na URL. Se a coluna estiver vazia,
o workflow 1 não chegou a gravar.

**`token_invalido` no envio, mesmo com token que funciona ao abrir a página**
O node `Configuração` precisa ser ancestral de quem o referencia. Se ele estiver
ligado só ao webhook GET, na rota POST ele nunca executa e todo
`$('Configuração')` falha três nodes adiante. `python tests/test_estrutura.py`
detecta isso.

**"Invalid login: 535" no SMTP**
Você usou a senha da conta em vez da senha de app, ou a verificação em duas
etapas não está ativa. Etapa 3.

**O mesmo cliente recebeu dois convites**
`convite_enviado_em` não foi gravado. Como o registro acontece depois do envio,
um erro no node `Registrar Envio` faz a venda continuar pendente. Olhe o
histórico de execuções.

**`Invalid JSON payload received. Unknown name ""`**
No node `Gemini · Analisar`, o campo *Specify Body* está em "Using Fields
Below". Tem que ser **Using JSON**, com a expressão
`{{ JSON.stringify($json.corpo_gemini) }}`.

**`models/... is not found` ou `no longer available to new users`**
Chave nova não acessa modelo antigo. A mensagem de erro diz qual usar; ponha em
`MODELO_GEMINI`.

**`503 — This model is currently experiencing high demand`**
Sobrecarga temporária do lado do Google, comum nos modelos mais novos. O node já
tenta 5 vezes com 5 segundos de intervalo. Se persistir, use um modelo menos
disputado.

**O relatório saiu com "[análise de IA indisponível: ...]"**
Comportamento planejado: a IA falhou e o pipeline seguiu com as métricas. O texto
entre colchetes traz o motivo real vindo da API.

**A planilha reclama de "schema"**
Alguma coluna foi renomeada, reordenada ou apagada. Volte ao nome original ou
clique em *Refresh columns* no node.

---

## Personalizando

**Texto e cores do formulário** → `site/formulario.html`. O arquivo está dividido
em seis blocos comentados; o de textos e o de tema cobrem praticamente tudo que
se quer mudar sem programar. Depois rode `make workflow`.

**Espera de 24h** → constante `HORAS_ESPERA` no node `Selecionar Pendentes`.

**Frequência da varredura** → node `A Cada 15 Minutos` (workflow 1).

**Dia do relatório** → node `Toda Segunda 09:00` (workflow 3). O fuso vem de
`GENERIC_TIMEZONE` no seu n8n.

**Faixas de nota** → `FAIXAS` no bloco de textos do HTML controla o que é crítico
e o que é neutro na página. A classificação NPS gravada na planilha fica em
`Montar Resposta`.

**Adicionar uma pergunta** → acrescente o campo no HTML, inclua-o em
`Validar Envio` e `Montar Resposta`, adicione a coluna em `COLUNAS['respostas']`
(em `tests/gerar_workflows.py`) e regere planilha e workflows.

**Alertar na hora quando a nota for baixa** → depois de `Gravar na Planilha`,
insira um `IF` com `{{ $json.nota <= 6 }}` e um node de e-mail no ramo
verdadeiro. Todos os dados do cliente já estão no item.

**Trocar de LLM** → o node `Gemini · Analisar` é um HTTP Request comum. Trocar
por OpenAI ou Anthropic é mudar URL, cabeçalho e o formato do corpo em
`Montar Prompt`; `Consolidar Análise` só precisa saber onde fica o texto na
resposta.

---

## Levando para a entrevista

**"Por que o n8n serve a página em vez de você hospedar um HTML?"**
Porque assim a página e os webhooks ficam na mesma origem — não existe CORS, nem
preflight, nem cabeçalho para configurar. E, renderizando no servidor, o nome do
cliente já vem dentro do HTML: nada de placeholder piscando enquanto um fetch
carrega.

**"Como você impede resposta duplicada?"**
Antes de gravar, o workflow procura o `id_venda` na aba `respostas`. Se achar,
responde 409 e a página mostra a tela de "você já respondeu". A validação está no
servidor, não no navegador.

**"E se alguém chamar o webhook direto, sem passar pelo formulário?"**
Sem um token válido não acontece nada — 404. Com um token válido, o que a pessoa
consegue é registrar a própria avaliação, que é exatamente o que o formulário
faria. Nome, e-mail e produto gravados vêm sempre da planilha, nunca do corpo da
requisição, então não dá para forjar uma resposta em nome de outro cliente.

**"Por que a IA não calcula o NPS?"**
Porque modelo de linguagem não é calculadora e um número errado num relatório
semanal derruba a confiança no projeto inteiro. A IA faz o que ela faz bem:
resumir, agrupar tema, classificar sentimento. Aritmética é JavaScript.

**"O que acontece se a API da IA cair?"**
O relatório sai assim mesmo, com as métricas e o motivo da falha no lugar do
resumo. A análise qualitativa é um acréscimo — não pode ser ponto único de falha
para o resto do fluxo.

**"Como você testa isso?"**
`tests/test_code_nodes.mjs` executa o JavaScript real de todos os nodes `Code`
com `$input`, `$json` e `$()` simulados. São 91 verificações em menos de um
segundo, sem planilha, sem SMTP e sem chave de IA. Inclui os casos chatos:
`</script>` no nome do produto, resposta não-JSON da IA, honeypot, nota 0 (que é
uma nota, não ausência de nota).

`tests/test_estrutura.py` valida o grafo em si: conexões apontando para nodes que
existem, `$('X')` sempre referenciando um ancestral, nenhum node órfão, todo
webhook alcançando um Respond to Webhook. Essa suíte nasceu de um bug real que
levou horas para achar porque o erro aparecia três nodes depois da causa.

**"O que você faria diferente em escala?"**
Google Sheets vira gargalo e não tem transação. Trocaria por Postgres, colocaria
uma fila entre o webhook e a gravação, e mudaria o polling de 15 minutos por um
webhook vindo da própria loja.
