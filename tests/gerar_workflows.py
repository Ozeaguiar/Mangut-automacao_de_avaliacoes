"""
Gera os três workflows do n8n em workflows/*.json.

Por que gerar em vez de editar o JSON na mão:
  - o HTML do formulário mora em site/formulario.html e é embutido aqui na
    geração — dá para editar a página num arquivo .html de verdade;
  - as colunas das abas da planilha são declaradas UMA vez (COLUNAS abaixo) e
    alimentam tanto o schema dos nodes do Google Sheets quanto a planilha
    modelo, então os dois nunca saem de sincronia;
  - um diff de "mudei o horário do agendamento" vira uma linha, não 300.

Uso:  python tests/gerar_workflows.py
"""

import json
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "workflows"

# ---------------------------------------------------------------------------
# Contrato de dados: as colunas de cada aba da planilha.
# ---------------------------------------------------------------------------
COLUNAS = {
    "vendas": [
        "id_venda", "data_compra", "nome", "email", "telefone", "produto",
        "token", "convite_enviado_em",
    ],
    "respostas": [
        "id_resposta", "id_venda", "respondido_em", "nome", "email", "telefone",
        "produto", "nota", "classificacao_nps", "observacoes",
        "sentimento", "temas", "analisado_em",
    ],
    "analise": [
        "gerado_em", "periodo_de", "periodo_ate", "respostas", "nps", "nota_media",
        "promotores", "neutros", "detratores",
        "sentimento_positivo", "sentimento_neutro", "sentimento_negativo",
        "temas_principais", "resumo", "acoes_sugeridas",
    ],
}


def nid(nome: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"n8n-feedback/{nome}"))


def schema_da_aba(aba: str, chaves: list[str] | None = None) -> list[dict]:
    """Schema no formato que o resourceMapper do Google Sheets espera."""
    chaves = chaves or []
    return [
        {
            "id": c, "displayName": c, "required": False, "defaultMatch": c in chaves,
            "display": True, "type": "string", "canBeUsedToMatch": True,
        }
        for c in COLUNAS[aba]
    ]


# ===========================================================================
# Fábricas de node
# ===========================================================================
def limpar_js(js: str) -> str:
    """Tira os comentários do JavaScript antes de embutir no JSON.

    O código-fonte aqui neste arquivo continua comentado — quem mexe no
    gerador precisa da explicação. O que vai para o n8n, não: lá o comentário
    só ocupa tela. O scanner ignora `//` dentro de aspas para não estragar
    URLs como http://exemplo.com.
    """
    js = _sem_blocos(js)
    saida = []
    for linha in js.split("\n"):
        if linha.lstrip().startswith("//"):
            continue
        corte, aspas, i = None, None, 0
        while i < len(linha):
            c = linha[i]
            if aspas:
                if c == "\\":
                    i += 2
                    continue
                if c == aspas:
                    aspas = None
            elif c in "\"'`":
                aspas = c
            elif c == "/" and linha[i + 1:i + 2] == "/":
                corte = i
                break
            i += 1
        if corte is not None:
            linha = linha[:corte].rstrip()
            if not linha:
                continue
        saida.append(linha)

    # sobra de espaço onde os blocos de comentário estavam
    texto, anterior = [], False
    for linha in saida:
        vazia = not linha.strip()
        if vazia and anterior:
            continue
        texto.append(linha)
        anterior = vazia
    return "\n".join(texto).strip()


def _sem_blocos(codigo: str) -> str:
    """Remove comentários /* ... */ respeitando aspas.

    O scanner de aspas importa: o data URI da logo é base64, e base64 usa `/`.
    Sem isso, um `/*` acidental no meio da imagem cortaria o arquivo ao meio.
    """
    saida, i, aspas = [], 0, None
    while i < len(codigo):
        c = codigo[i]
        if aspas:
            if c == "\\":
                saida.append(codigo[i:i + 2]); i += 2; continue
            if c == aspas:
                aspas = None
        elif c in "\"'`":
            aspas = c
        elif c == "/" and codigo[i + 1:i + 2] == "*":
            fim = codigo.find("*/", i + 2)
            i = len(codigo) if fim == -1 else fim + 2
            continue
        saida.append(c); i += 1
    return "".join(saida)


def limpar_html(html: str) -> str:
    """Versão do formulário sem comentário nenhum, para embutir no workflow.

    O arquivo em site/formulario.html continua comentado — é ele que se edita.
    O que vai para dentro do JSON é esta cópia limpa.
    """
    import re

    partes, resto = [], html
    padrao = re.compile(r"(<(style|script)\b[^>]*>)([\s\S]*?)(</\2>)", re.I)

    def trata(m):
        abre, tag, corpo, fecha = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        corpo = _sem_blocos(corpo) if tag == "style" else limpar_js(corpo)
        return abre + "\n" + corpo.strip("\n") + "\n" + fecha

    # comentários HTML só fora de <style>/<script>
    marcas = []
    def guardar(m):
        marcas.append(trata(m))
        return f"\x00{len(marcas) - 1}\x00"

    resto = padrao.sub(guardar, resto)
    resto = re.sub(r"<!--[\s\S]*?-->", "", resto)
    resto = re.sub(r"\n[ \t]*\n{2,}", "\n\n", resto)
    for i, bloco in enumerate(marcas):
        resto = resto.replace(f"\x00{i}\x00", bloco)
    return resto.strip() + "\n"


def node(nome, tipo, versao, pos, params=None, **extra):
    # `notes` e `notas` existem para documentar a intenção aqui no gerador.
    # Não são exportados: no n8n virariam post-its de tutorial em cima do fluxo.
    extra.pop("notes", None)
    n = {"parameters": params or {}, "id": nid(nome), "name": nome,
         "type": tipo, "typeVersion": versao, "position": pos}
    n.update(extra)
    return n


def code(nome, pos, js, **extra):
    return node(nome, "n8n-nodes-base.code", 2, pos, {"jsCode": limpar_js(js)}, **extra)


def config(pos, valores: dict, notas: str = ""):
    """Node 'Configuração': um único lugar para editar IDs, URLs e chaves."""
    return node(
        "Configuração", "n8n-nodes-base.set", 3.5, pos,
        {
            "assignments": {
                "assignments": [
                    {"id": nid(f"cfg-{k}"), "name": k, "value": v, "type": "string"}
                    for k, v in valores.items()
                ]
            },
            "includeOtherFields": True,
            "options": {},
        },

    )


def sheets_ler(nome, pos, aba, filtro_coluna=None, filtro_valor=None, **extra):
    params = {
        # Conta de serviço: bem menos passos que OAuth2 (sem tela de consentimento,
        # sem URI de redirecionamento). Basta compartilhar a planilha com o e-mail
        # da conta de serviço. Para trocar, mude para "oAuth2" nos 8 nodes.
        "authentication": "serviceAccount",
        "documentId": {"__rl": True, "value": "={{ $('Configuração').first().json.PLANILHA_ID }}", "mode": "id"},
        "sheetName": {"__rl": True, "value": aba, "mode": "name"},
        "options": {},
    }
    if filtro_coluna:
        params["filtersUI"] = {"values": [{"lookupColumn": filtro_coluna, "lookupValue": filtro_valor}]}
    return node(nome, "n8n-nodes-base.googleSheets", 4.7, pos, params, **extra)


def sheets_gravar(nome, pos, aba, operacao="append", chaves=None, **extra):
    colunas = {
        "mappingMode": "autoMapInputData",
        "value": {},
        "matchingColumns": chaves or [],
        "schema": schema_da_aba(aba, chaves),
        "attemptToConvertTypes": False,
        "convertFieldsToString": True,
    }
    return node(
        nome, "n8n-nodes-base.googleSheets", 4.7, pos,
        {
            "authentication": "serviceAccount",
            "operation": operacao,
            "documentId": {"__rl": True, "value": "={{ $('Configuração').first().json.PLANILHA_ID }}", "mode": "id"},
            "sheetName": {"__rl": True, "value": aba, "mode": "name"},
            "columns": colunas,
            "options": {},
        },
        **extra,
    )


def responder(nome, pos, tipo, corpo, codigo=200, cabecalhos=None, **extra):
    opcoes = {"responseCode": codigo}
    if cabecalhos:
        opcoes["responseHeaders"] = {"entries": [{"name": k, "value": v} for k, v in cabecalhos.items()]}
    return node(
        nome, "n8n-nodes-base.respondToWebhook", 1.5, pos,
        {"respondWith": tipo, "responseBody": corpo, "options": opcoes}, **extra,
    )


def conectar(mapa: dict) -> dict:
    return {
        origem: {"main": [[{"node": d, "type": "main", "index": 0} for d in saida] for saida in saidas]}
        for origem, saidas in mapa.items()
    }


def salvar(arquivo: str, nome: str, nodes: list, conexoes: dict):
    wf = {
        "id": arquivo.replace("_", "")[:16],
        "name": nome,
        "nodes": nodes,
        "connections": conectar(conexoes),
        "active": False,
        "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all",
                     "saveDataSuccessExecution": "all", "executionTimeout": 900},
        "pinData": {},
        "tags": [],
        "versionId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"n8n-feedback/{arquivo}")),
        "meta": {"templateCredsSetupCompleted": False},
    }
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / arquivo).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {arquivo:32} {len(nodes):>2} nodes")


# ===========================================================================
# WORKFLOW 1 — convite por e-mail
# ===========================================================================
JS_SELECIONAR = r"""
// ---------------------------------------------------------------------------
// Escolhe quem ainda não recebeu o convite e gera o link único de cada um.
// Regras:
//   - só quem tem e-mail válido
//   - só quem ainda não tem convite_enviado_em preenchido
//   - só depois de HORAS_ESPERA da compra (mandar no minuto seguinte parece robô
//     e o cliente ainda nem usou o produto)
// ---------------------------------------------------------------------------
const HORAS_ESPERA = 24;

const cfg = $('Configuração').first().json;
const agora = new Date();

/** Aceita ISO (2026-08-19) e o formato brasileiro (19/08/2026), com ou sem hora. */
function paraData(valor) {
  if (!valor) return null;
  const s = String(valor).trim();
  const br = s.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:[ ,]+(\d{2}):(\d{2}))?/);
  if (br) return new Date(Date.UTC(+br[3], +br[2] - 1, +br[1], +(br[4] || 0), +(br[5] || 0)));
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

/** Token aleatório de 24 caracteres, sem 0/1/l/o para não confundir na leitura. */
function novoToken() {
  const abc = 'abcdefghijkmnpqrstuvwxyz23456789';
  let t = '';
  for (let i = 0; i < 24; i++) t += abc[Math.floor(Math.random() * abc.length)];
  return t;
}

const pendentes = $input.all()
  .map((i) => i.json)
  .filter((l) => l && String(l.id_venda || '').trim())
  .filter((l) => !String(l.convite_enviado_em || '').trim())
  .filter((l) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(l.email || '').trim()))
  .filter((l) => {
    const compra = paraData(l.data_compra);
    if (!compra) return true;                       // sem data: não bloqueia
    return (agora - compra) / 36e5 >= HORAS_ESPERA;
  });

if (pendentes.length === 0) return [];

return pendentes.map((l) => {
  const token = novoToken();
  const base = String(cfg.URL_FORMULARIO || '').replace(/\/+$/, '');
  return {
    json: {
      ...l,
      token,
      link: `${base}?t=${token}`,
      primeiro_nome: String(l.nome || '').trim().split(/\s+/)[0] || 'tudo bem',
      empresa: cfg.EMPRESA,
    },
  };
});
"""

JS_EMAIL = r"""
// ---------------------------------------------------------------------------
// Monta o e-mail de convite. Curto de propósito: um pedido, um botão, uma saída.
// E-mail de pesquisa comprido é e-mail não respondido.
//
// O visual espelha o do formulário (mesmo verde, mesmo papel, mesmas réguas)
// para que abrir o link não pareça ir parar em outro lugar. Estilos inline e
// estrutura em tabela — cliente de e-mail não entende CSS moderno.
// ---------------------------------------------------------------------------
const v = $json;

// ----- EDITE AQUI: cores, textos e logo do e-mail --------------------------
const VERDE  = '#3A4B41';   // fundo e botão
const PAPEL  = '#E6CFA7';   // cartão
const TINTA  = '#3A4B41';   // texto principal
const FRACO  = '#6b7a70';   // texto secundário
const LINHA  = '#b9a884';   // réguas finas

// URL da logo. Deixe '' para usar só o nome escrito.
// ATENÇÃO: precisa ser um link http(s) público — Gmail e Outlook bloqueiam
// imagem embutida (data:) em e-mail, ao contrário da página do formulário.
const LOGO = '';

const TITULO   = 'Sua Experiência';
const CHAMADA  = `Oi, ${v.primeiro_nome}! Que tal o sorvete?`;
const LINHA_1  = `Você levou <strong style="color:${TINTA};font-weight:600">${v.produto}</strong> e a gente queria muito saber o que achou. São <strong style="color:${TINTA};font-weight:600">30 segundos</strong>: uma nota e, se quiser, um comentário.`;
const LINHA_2  = 'A gente lê tudo. É assim que a próxima fornada fica melhor que essa.';
const BOTAO    = 'Avaliar minha experiência';
const RODAPE   = `Você recebeu este e-mail porque comprou na ${v.empresa}.`;
// ---------------------------------------------------------------------------

const assunto = `${v.primeiro_nome}, que tal o ${v.produto}?`;

const cabecalhoLogo = LOGO
  ? `<img src="${LOGO}" alt="${v.empresa}" height="40"
         style="display:block;margin:0 0 8px auto;height:40px;width:auto;border:0">`
  : '';

const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:40px 16px;background:${VERDE};
  font-family:Helvetica,Arial,sans-serif;color:${TINTA}">

<div style="display:none;max-height:0;overflow:hidden;opacity:0">
  São 30 segundos: uma nota e, se quiser, um comentário.</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="max-width:600px;background:${PAPEL}">
    <tr><td style="padding:44px 44px 38px">

      <!-- cabeçalho: título à esquerda, marca à direita -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="bottom" style="font-family:Georgia,'Times New Roman',serif;font-style:italic;
                   font-size:38px;line-height:1;color:${VERDE}">${TITULO}</td>
        <td valign="bottom" align="right" style="font-size:11px;line-height:1.9;
                   letter-spacing:2px;text-transform:uppercase;color:${TINTA}">
          ${cabecalhoLogo}<strong style="font-weight:700">${v.empresa}</strong><br>
          <span style="color:${FRACO}">Avaliação da visita</span>
        </td>
      </tr></table>

      <!-- ficha -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="margin-top:32px;font-size:11px;letter-spacing:2px;text-transform:uppercase"><tr>
        <td width="50%" valign="top">
          <span style="color:${FRACO}">Cliente</span><br>
          <strong style="font-weight:700;letter-spacing:1.5px">${v.nome}</strong>
        </td>
        <td width="50%" valign="top" align="right">
          <span style="color:${FRACO}">Sabor</span><br>
          <strong style="font-weight:700;letter-spacing:1.5px">${v.produto}</strong>
        </td>
      </tr></table>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:26px">
        <tr><td style="height:2px;background:${VERDE};font-size:0;line-height:0">&nbsp;</td></tr>
      </table>

      <h1 style="margin:26px 0 10px;font-size:21px;line-height:1.3;font-weight:700;color:${TINTA}">
        ${CHAMADA}</h1>

      <p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:${FRACO}">${LINHA_1}</p>
      <p style="margin:0 0 30px;font-size:15px;line-height:1.6;color:${FRACO}">${LINHA_2}</p>

      <!-- botão -->
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background:${VERDE}">
          <a href="${v.link}" style="display:inline-block;padding:17px 38px;color:${PAPEL};
             text-decoration:none;font-size:12px;font-weight:700;letter-spacing:3px;
             text-transform:uppercase">${BOTAO}</a>
        </td>
      </tr></table>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:34px">
        <tr><td style="height:1px;background:${LINHA};font-size:0;line-height:0">&nbsp;</td></tr>
      </table>
      <p style="margin:16px 0 0;font-size:11px;line-height:1.7;letter-spacing:1px;
                text-transform:uppercase;color:${FRACO}">Se o botão não abrir, use este endereço:</p>
      <p style="margin:4px 0 0;font-size:12px;line-height:1.6;word-break:break-all;color:${TINTA}">
        ${v.link}</p>

    </td></tr>
  </table>

  <p style="margin:18px 0 0;max-width:600px;font-size:11px;line-height:1.7;letter-spacing:1px;
            text-transform:uppercase;color:#9aa79d">${RODAPE}</p>

</td></tr></table>
</body></html>`;

const texto = [
  `Oi, ${v.primeiro_nome}!`, '',
  `Você levou ${v.produto} e a gente queria saber o que achou. São 30 segundos:`,
  v.link, '',
  `— Equipe ${v.empresa}`,
].join('\n');

return [{ json: { ...v, assunto, corpo_html: html, corpo_texto: texto } }];
"""

JS_REGISTRAR = r"""
// Grava de volta na aba `vendas` só o que mudou: o token gerado e o carimbo de
// envio. É esse carimbo que impede o mesmo cliente de receber duas vezes.
const v = $('Montar E-mail').first().json;

return [{
  json: {
    id_venda: v.id_venda,
    data_compra: v.data_compra ?? '',
    nome: v.nome ?? '',
    email: v.email ?? '',
    telefone: v.telefone ?? '',
    produto: v.produto ?? '',
    token: v.token,
    convite_enviado_em: new Date().toISOString(),
  },
}];
"""


def workflow_convite():
    nodes = [
        node("A Cada 15 Minutos", "n8n-nodes-base.scheduleTrigger", 1.2, [-360, -40],
             {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}),
        node("Executar Manualmente", "n8n-nodes-base.manualTrigger", 1, [-360, 140], {}),

        config([-140, 40], {
            "PLANILHA_ID": "COLE_AQUI_O_ID_DA_PLANILHA",
            "URL_FORMULARIO": "http://localhost:5678/webhook/feedback",
            "EMPRESA": "Loja Exemplo",
            "REMETENTE": "voce@gmail.com",
        }),

        sheets_ler("Ler Vendas", [80, 40], "vendas", alwaysOutputData=True,
                   notes="Lê a aba inteira; o filtro de quem já recebeu é feito no node seguinte."),

        code("Selecionar Pendentes", [300, 40], JS_SELECIONAR,
             notes="Nenhum pendente ⇒ nenhum item ⇒ o workflow simplesmente termina."),

        node("Loop Vendas", "n8n-nodes-base.splitInBatches", 3, [520, 40],
             {"options": {"reset": False}},
             notes="Um e-mail por vez: evita estourar o limite de envio do SMTP."),

        node("Fim", "n8n-nodes-base.noOp", 1, [760, -80], {}),

        code("Montar E-mail", [760, 180], JS_EMAIL),

        node("Enviar Convite", "n8n-nodes-base.emailSend", 2.1, [980, 180],
             {
                 "fromEmail": "={{ $('Configuração').first().json.REMETENTE }}",
                 "toEmail": "={{ $json.email }}",
                 "subject": "={{ $json.assunto }}",
                 "emailFormat": "both",
                 "text": "={{ $json.corpo_texto }}",
                 "html": "={{ $json.corpo_html }}",
                 "options": {},
             },
             retryOnFail=True, maxTries=2, waitBetweenTries=5000,
             notes="Credencial SMTP. No Gmail use uma senha de app, não a senha da conta."),

        code("Preparar Registro", [1200, 180], JS_REGISTRAR),

        sheets_gravar("Registrar Envio", [1420, 180], "vendas",
                      operacao="appendOrUpdate", chaves=["id_venda"],
                      notes="Só grava DEPOIS do envio: se o e-mail falhar, a venda continua pendente."),
    ]

    conexoes = {
        "A Cada 15 Minutos": [["Configuração"]],
        "Executar Manualmente": [["Configuração"]],
        "Configuração": [["Ler Vendas"]],
        "Ler Vendas": [["Selecionar Pendentes"]],
        "Selecionar Pendentes": [["Loop Vendas"]],
        "Loop Vendas": [["Fim"], ["Montar E-mail"]],
        "Montar E-mail": [["Enviar Convite"]],
        "Enviar Convite": [["Preparar Registro"]],
        "Preparar Registro": [["Registrar Envio"]],
        "Registrar Envio": [["Loop Vendas"]],
    }
    salvar("1_convite_por_email.json", "1 · Convite de avaliação por e-mail", nodes, conexoes)


# ===========================================================================
# WORKFLOW 2 — página do formulário + recebimento
# ===========================================================================
JS_PAGINA = r"""
// ---------------------------------------------------------------------------
// Renderiza a página no servidor.
// O token vem na URL, é procurado na aba `vendas` e os dados do cliente são
// injetados direto no HTML. Vantagens sobre buscar por fetch depois:
//   - uma requisição a menos;
//   - o nome do cliente já vem no HTML (nada de "Olá, {{nome}}" piscando);
//   - a página sai da MESMA origem dos webhooks, então não existe CORS.
// ---------------------------------------------------------------------------
const HTML = $('Configuração').first().json.PAGINA_HTML;

const token = String($('Webhook · Página do Formulário').first().json.query?.t || '').trim();

// Os nodes de planilha leem a aba INTEIRA e o casamento é feito aqui.
// O filtro nativo do Google Sheets depende de um campo que só carrega se o
// n8n conseguir listar as colunas em tempo de edição — e como o ID da
// planilha vem de uma expressão, ele nunca consegue. Filtrar em JS é código
// versionado: não se perde ao abrir o node.
const vendas = $('Buscar Venda').all().map((i) => i.json)
  .filter((v) => v && v.id_venda && String(v.token || '').trim() === token);

const idVenda = vendas.length ? String(vendas[0].id_venda) : null;
const jaRespondeu = $('Buscar Resposta').all().map((i) => i.json)
  .filter((r) => r && r.id_resposta && String(r.id_venda) === idVenda);

// O nome da empresa vale para TODAS as telas — inclusive link inválido e
// "já respondeu". Sem isso a página cai no texto de exemplo do HTML.
const EMPRESA = $('Configuração').first().json.EMPRESA;
// URL da logo (campo LOGO do node Configuração). Vazio = sem logo.
const LOGO = $('Configuração').first().json.LOGO || '';

let dados;
if (!token || vendas.length === 0) {
  dados = { ok: false, erro: 'token_invalido', empresa: EMPRESA, logo: LOGO };
} else if (jaRespondeu.length > 0) {
  dados = { ok: true, ja_respondeu: true, respondido_em: jaRespondeu[0].respondido_em, empresa: EMPRESA, logo: LOGO };
} else {
  const v = vendas[0];
  dados = {
    ok: true,
    ja_respondeu: false,
    primeiro_nome: String(v.nome || '').trim().split(/\s+/)[0] || '',
    produto: v.produto || '',
    telefone: v.telefone || '',
    empresa: EMPRESA,
    logo: LOGO,
  };
}

// `</script>` dentro de string quebraria a tag; escapamos o `<`.
const injecao = JSON.stringify(dados).replace(/</g, '\\u003c');

return [{ json: { pagina: HTML.replace('__DADOS_DA_VENDA__', injecao) } }];
"""

JS_VALIDAR = r"""
// ---------------------------------------------------------------------------
// Valida o envio ANTES de tocar na planilha. Nunca confie no que veio do
// navegador: a validação do formulário é conveniência para o usuário, não
// segurança.
// ---------------------------------------------------------------------------
const corpo = $('Webhook · Receber Resposta').first().json.body || {};
const token = String(corpo.t || '').trim();

const nota = Number(corpo.nota);
const notaValida = Number.isInteger(nota) && nota >= 0 && nota <= 10;

return [{
  json: {
    token,
    nota: notaValida ? nota : null,
    nota_valida: notaValida,
    // honeypot: campo escondido no HTML. Se veio preenchido, foi robô.
    robo: Boolean(String(corpo.empresa_site || '').trim()),
    observacoes: String(corpo.observacoes || '').trim().slice(0, 1000),
    telefone: String(corpo.telefone || '').replace(/\D/g, '').slice(0, 11),
  },
}];
"""

JS_MONTAR_RESPOSTA = r"""
// Junta o que veio do formulário com o que já estava na planilha de vendas.
// Nome, e-mail e produto vêm SEMPRE da venda — nunca do que o navegador mandou.
const envio = $('Validar Envio').first().json;
const venda = $('Buscar Venda (envio)').all().map((i) => i.json)
  .find((v) => v && v.id_venda && String(v.token || '').trim() === envio.token);

const nota = envio.nota;
const classificacao = nota <= 6 ? 'detrator' : nota <= 8 ? 'neutro' : 'promotor';
const agora = new Date().toISOString();

return [{
  json: {
    id_resposta: `R-${Date.now().toString(36).toUpperCase()}`,
    id_venda: venda.id_venda,
    respondido_em: agora,
    nome: venda.nome || '',
    email: venda.email || '',
    telefone: envio.telefone || venda.telefone || '',
    produto: venda.produto || '',
    nota,
    classificacao_nps: classificacao,
    observacoes: envio.observacoes,
    sentimento: '',        // preenchido pelo workflow 3
    temas: '',
    analisado_em: '',
  },
}];
"""

JS_DECIDIR = r"""
// Decide se pode gravar. Quatro motivos para recusar, cada um com sua mensagem.
const envio = $('Validar Envio').first().json;
// Casamento em JS — ver comentário no node "Renderizar Página".
const vendas = $('Buscar Venda (envio)').all().map((i) => i.json)
  .filter((v) => v && v.id_venda && String(v.token || '').trim() === envio.token);

const idVenda = vendas.length ? String(vendas[0].id_venda) : null;
const jaTem = $('Buscar Resposta (envio)').all().map((i) => i.json)
  .filter((r) => r && r.id_resposta && String(r.id_venda) === idVenda);

let erro = null;
if (envio.robo) erro = 'robo';                       // responde 200 para não dar pista
else if (!envio.token || vendas.length === 0) erro = 'token_invalido';
else if (jaTem.length > 0) erro = 'ja_respondido';
else if (!envio.nota_valida) erro = 'nota_invalida';

const codigos = { robo: 200, token_invalido: 404, ja_respondido: 409, nota_invalida: 400 };

return [{ json: { pode_gravar: erro === null, erro, codigo: erro ? codigos[erro] : 200 } }];
"""


def workflow_formulario():
    html = limpar_html((RAIZ / "site" / "formulario.html").read_text(encoding="utf-8"))

    nodes = [
        # ---------------- ramo A: servir a página ----------------
        node("Webhook · Página do Formulário", "n8n-nodes-base.webhook", 2.1, [-620, -80],
             {"path": "feedback", "responseMode": "responseNode", "options": {}},
             webhookId=nid("wh-pagina"),
             notes="GET /webhook/feedback?t=TOKEN — é este link que vai no e-mail."),

        # Os DOIS webhooks entram aqui. Se este node ficasse só na rota da
        # página, numa requisição POST ele nunca executaria — e todo
        # $('Configuração') da rota de envio falharia.
        config([-400, 40], {
            "PLANILHA_ID": "COLE_AQUI_O_ID_DA_PLANILHA",
            "EMPRESA": "Loja Exemplo",
            "LOGO": "",
            "PAGINA_HTML": html,
        }, notas="Vale para as duas rotas (página e envio). PAGINA_HTML é gerado a partir de "
                 "site/formulario.html — não edite aqui, edite o arquivo e rode o gerador."),

        node("É Envio?", "n8n-nodes-base.if", 2.2, [-180, 40],
             {"conditions": {
                 "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                 "conditions": [{"id": nid("cond-envio"),
                                 "leftValue": "={{ !!($json.body && $json.body.t) }}",
                                 "rightValue": "",
                                 "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                 "combinator": "and"}, "options": {}},
             notes="POST traz body.t; GET não. É o que separa as duas rotas."),

        sheets_ler("Buscar Venda", [60, -160], "vendas",
                   alwaysOutputData=True, onError="continueRegularOutput",
                   notes="Lê a aba inteira; o casamento pelo token é feito no node 'Renderizar Página'."),

        sheets_ler("Buscar Resposta", [280, -160], "respostas",
                   alwaysOutputData=True, onError="continueRegularOutput",
                   notes="Lê a aba inteira; a checagem de duplicata é feita em 'Renderizar Página'."),

        code("Renderizar Página", [500, -160], JS_PAGINA),

        responder("Responder HTML", [720, -160], "text", "={{ $json.pagina }}",
                  cabecalhos={"Content-Type": "text/html; charset=utf-8",
                              "Cache-Control": "no-store"}),

        # ---------------- ramo B: receber a resposta ----------------
        node("Webhook · Receber Resposta", "n8n-nodes-base.webhook", 2.1, [-620, 200],
             {"httpMethod": "POST", "path": "feedback/enviar",
              "responseMode": "responseNode", "options": {}},
             webhookId=nid("wh-envio"),
             notes="POST /webhook/feedback/enviar — chamado pelo JavaScript da página."),

        code("Validar Envio", [60, 220], JS_VALIDAR),

        sheets_ler("Buscar Venda (envio)", [280, 220], "vendas",
                   alwaysOutputData=True, onError="continueRegularOutput",
                   notes="Lê a aba inteira; o casamento pelo token é feito no node 'Decidir'."),

        sheets_ler("Buscar Resposta (envio)", [500, 220], "respostas",
                   alwaysOutputData=True, onError="continueRegularOutput",
                   notes="Lê a aba inteira; a checagem de duplicata é feita em 'Decidir'."),

        code("Decidir", [720, 220], JS_DECIDIR),

        node("Pode Gravar?", "n8n-nodes-base.if", 2.2, [940, 220],
             {"conditions": {
                 "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                 "conditions": [{"id": nid("cond-gravar"), "leftValue": "={{ $json.pode_gravar }}",
                                 "rightValue": "", "operator": {"type": "boolean", "operation": "true",
                                                                "singleValue": True}}],
                 "combinator": "and"}, "options": {}}),

        code("Montar Resposta", [1160, 120], JS_MONTAR_RESPOSTA),
        sheets_gravar("Gravar na Planilha", [1380, 120], "respostas", operacao="append"),
        responder("Responder Sucesso", [1600, 120], "json",
                  '={{ JSON.stringify({ ok: true, id_resposta: $json.id_resposta }) }}'),

        responder("Responder Recusa", [1160, 340], "json",
                  '={{ JSON.stringify({ ok: $json.erro === "robo", erro: $json.erro }) }}',
                  codigo="={{ $json.codigo }}"),
    ]

    conexoes = {
        # os dois gatilhos passam pela MESMA Configuração; o IF separa as rotas
        "Webhook · Página do Formulário": [["Configuração"]],
        "Webhook · Receber Resposta": [["Configuração"]],
        "Configuração": [["É Envio?"]],
        # saída 0 = true (envio) · saída 1 = false (página)
        "É Envio?": [["Validar Envio"], ["Buscar Venda"]],

        "Buscar Venda": [["Buscar Resposta"]],
        "Buscar Resposta": [["Renderizar Página"]],
        "Renderizar Página": [["Responder HTML"]],

        "Validar Envio": [["Buscar Venda (envio)"]],
        "Buscar Venda (envio)": [["Buscar Resposta (envio)"]],
        "Buscar Resposta (envio)": [["Decidir"]],
        "Decidir": [["Pode Gravar?"]],
        "Pode Gravar?": [["Montar Resposta"], ["Responder Recusa"]],
        "Montar Resposta": [["Gravar na Planilha"]],
        "Gravar na Planilha": [["Responder Sucesso"]],
    }
    salvar("2_formulario_e_respostas.json", "2 · Formulário e recebimento das respostas", nodes, conexoes)


# ===========================================================================
# WORKFLOW 3 — análise dos comentários com IA
# ===========================================================================
JS_PROMPT = r"""
// ---------------------------------------------------------------------------
// Monta o lote e o prompt.
// Duas decisões que mudam muito o resultado:
//   1. as métricas (NPS, média) são calculadas em JavaScript, NÃO pela IA.
//      Modelo de linguagem não é calculadora, e número errado em relatório
//      destrói a confiança no projeto inteiro.
//   2. a saída da IA é forçada a um schema JSON (responseSchema do Gemini),
//      então o node seguinte recebe estrutura e não um texto para adivinhar.
// ---------------------------------------------------------------------------
const cfg = $('Configuração').first().json;
const LIMITE_LOTE = 60;

const todas = $input.all().map((i) => i.json).filter((r) => r && r.id_resposta);
const novas = todas.filter((r) => !String(r.analisado_em || '').trim());

if (novas.length === 0) return [];

const lote = novas.slice(0, LIMITE_LOTE);
const comComentario = lote.filter((r) => String(r.observacoes || '').trim().length >= 3);

// ---- métricas determinísticas -------------------------------------------
const notas = lote.map((r) => Number(r.nota)).filter((n) => Number.isFinite(n));
const promotores = notas.filter((n) => n >= 9).length;
const detratores = notas.filter((n) => n <= 6).length;
const neutros = notas.length - promotores - detratores;
const nps = notas.length ? Math.round(((promotores - detratores) / notas.length) * 100) : 0;
const media = notas.length ? +(notas.reduce((a, b) => a + b, 0) / notas.length).toFixed(2) : 0;

const datas = lote.map((r) => r.respondido_em).filter(Boolean).sort();

// ---- prompt --------------------------------------------------------------
const comentarios = comComentario.map((r) =>
  `[${r.id_resposta}] nota ${r.nota} · ${r.produto}: ${String(r.observacoes).replace(/\s+/g, ' ').trim()}`
).join('\n');

const instrucao = [
  'Você analisa comentários de clientes de uma loja brasileira.',
  'Responda em português do Brasil, com objetividade e sem elogiar a empresa.',
  '',
  'Para o conjunto de comentários abaixo:',
  '1. Escreva um resumo de 3 a 5 frases sobre o que os clientes estão dizendo.',
  '2. Liste os temas recorrentes, do mais citado ao menos citado (no máximo 6).',
  '   Um tema é um assunto concreto (ex.: "prazo de entrega", "qualidade do som"),',
  '   nunca algo genérico como "experiência" ou "produto".',
  '3. Sugira de 2 a 4 ações práticas, cada uma ligada a um tema.',
  '4. Classifique CADA comentário em positivo, neutro ou negativo, e associe',
  '   até 2 temas da sua própria lista. Use o id entre colchetes.',
  '',
  'Se um comentário for vago demais para classificar, use "neutro" e tema "sem detalhe".',
  '',
  `Comentários (${comComentario.length}):`,
  comentarios || '(nenhum comentário em texto neste lote)',
].join('\n');

const corpo_gemini = {
  contents: [{ role: 'user', parts: [{ text: instrucao }] }],
  generationConfig: {
    temperature: 0.2,
    responseMimeType: 'application/json',
    responseSchema: {
      type: 'object',
      properties: {
        resumo: { type: 'string' },
        temas: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              tema: { type: 'string' },
              mencoes: { type: 'integer' },
              tom: { type: 'string', enum: ['positivo', 'negativo', 'misto'] },
            },
            required: ['tema', 'mencoes', 'tom'],
          },
        },
        acoes: { type: 'array', items: { type: 'string' } },
        classificacoes: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id_resposta: { type: 'string' },
              sentimento: { type: 'string', enum: ['positivo', 'neutro', 'negativo'] },
              temas: { type: 'string' },
            },
            required: ['id_resposta', 'sentimento', 'temas'],
          },
        },
      },
      required: ['resumo', 'temas', 'acoes', 'classificacoes'],
    },
  },
};

return [{
  json: {
    // .trim() de propósito: o nome é digitado à mão no node Configuração e
    // um espaço sobrando no fim vira 404 ("resource could not be found"),
    // porque ele entra direto na URL.
    modelo: String(cfg.MODELO_GEMINI || 'gemini-3.6-flash').trim(),
    corpo_gemini,
    metricas: {
      respostas: lote.length, com_comentario: comComentario.length,
      nps, nota_media: media, promotores, neutros, detratores,
      periodo_de: (datas[0] || '').slice(0, 10),
      periodo_ate: (datas[datas.length - 1] || '').slice(0, 10),
    },
    lote: lote.map((r) => ({ id_resposta: r.id_resposta, nota: r.nota, produto: r.produto,
                             observacoes: r.observacoes, id_venda: r.id_venda,
                             respondido_em: r.respondido_em, nome: r.nome, email: r.email,
                             telefone: r.telefone, classificacao_nps: r.classificacao_nps })),
  },
}];
"""

JS_CONSOLIDAR = r"""
// ---------------------------------------------------------------------------
// Lê a resposta do Gemini e junta com as métricas calculadas em JavaScript.
// Se a IA falhar ou devolver algo inesperado, o relatório ainda sai — com as
// métricas e sem a parte qualitativa. Uma etapa opcional não pode derrubar o
// pipeline inteiro.
// ---------------------------------------------------------------------------
const base = $('Montar Prompt').first().json;
const m = base.metricas;

let ia = { resumo: '', temas: [], acoes: [], classificacoes: [] };
let falhaIA = '';
try {
  const r = $json || {};

  // O node do Gemini está com "continue on fail": quando a API recusa a
  // chamada, o erro chega aqui como dado em vez de parar o workflow. Sem
  // olhar para ele, toda falha viraria o mesmo "sem conteúdo" genérico —
  // e o motivo real (chave inválida, cota, modelo errado) fica invisível.
  const apiErro = r.error || r.body?.error;
  if (apiErro) {
    throw new Error(`API do Gemini recusou: ${apiErro.status || apiErro.code || ''} ${apiErro.message || ''}`.trim());
  }
  if (typeof r.message === 'string' && !r.candidates) {
    throw new Error(`chamada falhou: ${r.message}`);
  }

  const cand = r.candidates?.[0];
  if (!cand) {
    const bloqueio = r.promptFeedback?.blockReason;
    if (bloqueio) throw new Error(`prompt bloqueado pelo filtro (${bloqueio})`);
    throw new Error(`resposta sem candidatos — recebido: ${JSON.stringify(r).slice(0, 300)}`);
  }

  const texto = cand.content?.parts?.[0]?.text;
  if (!texto) {
    const motivo = cand.finishReason || 'desconhecido';
    throw new Error(`resposta vazia (finishReason: ${motivo})`);
  }

  // O modelo às vezes embrulha o JSON em ```json ... ```
  const limpo = texto.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  ia = { ...ia, ...JSON.parse(limpo) };
} catch (e) {
  falhaIA = String(e.message || e);
}

const porId = new Map((ia.classificacoes || []).map((c) => [String(c.id_resposta).trim(), c]));
const conta = { positivo: 0, neutro: 0, negativo: 0 };
const agora = new Date().toISOString();

// linhas para atualizar a aba `respostas`
const respostas = base.lote.map((r) => {
  const c = porId.get(r.id_resposta);
  const sentimento = c?.sentimento || (falhaIA ? '' : 'neutro');
  if (sentimento && conta[sentimento] !== undefined) conta[sentimento] += 1;
  return {
    id_resposta: r.id_resposta, id_venda: r.id_venda, respondido_em: r.respondido_em,
    nome: r.nome, email: r.email, telefone: r.telefone, produto: r.produto,
    nota: r.nota, classificacao_nps: r.classificacao_nps, observacoes: r.observacoes,
    sentimento, temas: c?.temas || '', analisado_em: agora,
  };
});

// linha única para a aba `analise`
const analise = {
  gerado_em: agora,
  periodo_de: m.periodo_de, periodo_ate: m.periodo_ate,
  respostas: m.respostas, nps: m.nps, nota_media: m.nota_media,
  promotores: m.promotores, neutros: m.neutros, detratores: m.detratores,
  sentimento_positivo: conta.positivo, sentimento_neutro: conta.neutro,
  sentimento_negativo: conta.negativo,
  temas_principais: (ia.temas || []).map((t) => `${t.tema} (${t.mencoes}, ${t.tom})`).join(' · '),
  resumo: falhaIA ? `[análise de IA indisponível: ${falhaIA}]` : ia.resumo,
  acoes_sugeridas: (ia.acoes || []).join(' · '),
};

return [{ json: { analise, respostas, metricas: m, ia, falha_ia: falhaIA } }];
"""

JS_ESPALHAR = r"""
// Um item por resposta: é assim que o node do Google Sheets grava várias linhas.
return $('Consolidar Análise').first().json.respostas.map((json) => ({ json }));
"""

JS_RELATORIO = r"""
// ---------------------------------------------------------------------------
// Relatório por e-mail. Mesmo sistema visual do convite e do formulário:
// fundo verde, cartão papel, réguas e caixa alta espaçada.
// Hierarquia pensada para leitura no celular: os três números primeiro, o
// resumo depois e as ações no fim — a ordem em que a pessoa decide se precisa
// fazer alguma coisa.
// ---------------------------------------------------------------------------
const c = $('Consolidar Análise').first().json;
const a = c.analise;
const cfg = $('Configuração').first().json;

// ----- EDITE AQUI: cores, título e logo do relatório -----------------------
const VERDE  = '#3A4B41';   // fundo
const PAPEL  = '#E6CFA7';   // cartão
const TINTA  = '#3A4B41';   // texto principal
const FRACO  = '#6b7a70';   // texto secundário
const LINHA  = '#b9a884';   // réguas finas

// URL da logo. Deixe '' para usar só o nome escrito.
// ATENÇÃO: precisa ser um link http(s) público — Gmail e Outlook bloqueiam
// imagem embutida (data:) em e-mail, ao contrário da página do formulário.
const LOGO = '';

const TITULO   = 'O Relatório';
const CHAMADA  = 'Como os clientes avaliaram';
const SELO     = 'Resumo da semana';
// ---------------------------------------------------------------------------

// Faixas usuais de NPS: acima de 50 é ótimo, entre 0 e 50 é razoável, abaixo de 0 é crítico.
const cor = a.nps >= 50 ? '#2c5c3a' : a.nps >= 0 ? '#8a5d00' : '#8c2f22';
const rotulo = a.nps >= 50 ? 'ótimo' : a.nps >= 0 ? 'razoável' : 'crítico';

const cabecalhoLogo = LOGO
  ? `<img src="${LOGO}" alt="${cfg.EMPRESA}" height="40"
         style="display:block;margin:0 0 8px auto;height:40px;width:auto;border:0">`
  : '';

// Número grande com rótulo em caixa alta, separado por régua — não por caixinha.
const numero = (rot, val, apoio, corVal) => `
  <td width="33.33%" valign="top" style="padding-right:14px">
    <div style="font-size:10px;letter-spacing:2px;text-transform:uppercase;color:${FRACO}">${rot}</div>
    <div style="font-family:Georgia,'Times New Roman',serif;font-size:34px;line-height:1.1;
                margin-top:6px;color:${corVal || TINTA}">${val}</div>
    <div style="font-size:10px;letter-spacing:1.5px;text-transform:uppercase;
                color:${FRACO};margin-top:4px">${apoio}</div>
  </td>`;

const bloco = (titulo, conteudo) => `
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:30px">
    <tr><td style="height:1px;background:${LINHA};font-size:0;line-height:0">&nbsp;</td></tr>
    <tr><td style="padding-top:18px">
      <div style="font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
                  color:${TINTA};margin-bottom:12px">${titulo}</div>
      ${conteudo}
    </td></tr>
  </table>`;

const tema = (t) => `<li style="margin-bottom:9px;color:${FRACO}">
  <strong style="color:${TINTA};font-weight:700">${t.tema}</strong> — ${t.mencoes} menção(ões), tom ${t.tom}</li>`;
const acao = (x) => `<li style="margin-bottom:9px;color:${FRACO}">${x}</li>`;
const lista = (itens, vazio) =>
  `<ul style="margin:0;padding-left:18px;font-size:14.5px;line-height:1.6">${itens || `<li style="color:${FRACO}">${vazio}</li>`}</ul>`;

const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:40px 16px;background:${VERDE};
  font-family:Helvetica,Arial,sans-serif;color:${TINTA}">

<div style="display:none;max-height:0;overflow:hidden;opacity:0">
  NPS ${a.nps} · ${a.respostas} respostas · nota média ${a.nota_media}</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="max-width:620px;background:${PAPEL}">
    <tr><td style="padding:44px 44px 40px">

      <!-- cabeçalho -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="bottom" style="font-family:Georgia,'Times New Roman',serif;font-style:italic;
                   font-size:38px;line-height:1;color:${VERDE}">${TITULO}</td>
        <td valign="bottom" align="right" style="font-size:11px;line-height:1.9;
                   letter-spacing:2px;text-transform:uppercase;color:${TINTA}">
          ${cabecalhoLogo}<strong style="font-weight:700">${cfg.EMPRESA}</strong><br>
          <span style="color:${FRACO}">${SELO}</span>
        </td>
      </tr></table>

      <!-- ficha do período -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="margin-top:32px;font-size:11px;letter-spacing:2px;text-transform:uppercase"><tr>
        <td width="50%" valign="top">
          <span style="color:${FRACO}">Período</span><br>
          <strong style="font-weight:700;letter-spacing:1.5px">${a.periodo_de} a ${a.periodo_ate}</strong>
        </td>
        <td width="50%" valign="top" align="right">
          <span style="color:${FRACO}">Respostas</span><br>
          <strong style="font-weight:700;letter-spacing:1.5px">${a.respostas} analisadas</strong>
        </td>
      </tr></table>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:26px">
        <tr><td style="height:2px;background:${VERDE};font-size:0;line-height:0">&nbsp;</td></tr>
      </table>

      <h1 style="margin:26px 0 24px;font-size:21px;line-height:1.3;font-weight:700;color:${TINTA}">
        ${CHAMADA}</h1>

      <!-- os três números -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        ${numero('NPS', a.nps, rotulo, cor)}
        ${numero('Nota média', a.nota_media, 'de 0 a 10')}
        ${numero('Detratores', a.detratores, `de ${a.respostas}`)}
      </tr></table>

      ${bloco('O que os clientes estão dizendo',
        `<p style="margin:0;font-size:14.5px;line-height:1.65;color:${FRACO}">${a.resumo}</p>`)}
      ${bloco('Temas mais citados', lista((c.ia.temas || []).map(tema).join(''), 'Sem comentários em texto neste período.'))}
      ${bloco('Ações sugeridas', lista((c.ia.acoes || []).map(acao).join(''), 'Nada a sugerir neste período.'))}

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:30px">
        <tr><td style="height:1px;background:${LINHA};font-size:0;line-height:0">&nbsp;</td></tr>
      </table>
      <p style="margin:16px 0 0;font-size:11px;line-height:1.8;letter-spacing:1px;
                text-transform:uppercase;color:${FRACO}">
        Sentimento: ${a.sentimento_positivo} positivos ·
        ${a.sentimento_neutro} neutros · ${a.sentimento_negativo} negativos</p>

    </td></tr>
  </table>

  <p style="margin:18px 0 0;max-width:620px;font-size:11px;line-height:1.7;letter-spacing:1px;
            text-transform:uppercase;color:#9aa79d">
    Gerado automaticamente pelo n8n a partir da planilha de respostas.</p>

</td></tr></table>
</body></html>`;

return [{
  json: {
    assunto: `NPS ${a.nps} · ${a.respostas} respostas · ${cfg.EMPRESA}`,
    corpo_html: html,
    corpo_texto: `NPS ${a.nps} | nota média ${a.nota_media} | ${a.respostas} respostas\n\n${a.resumo}\n\nTemas: ${a.temas_principais}\n\nAções: ${a.acoes_sugeridas}`,
  },
}];
"""


def workflow_analise():
    nodes = [
        node("Toda Segunda 09:00", "n8n-nodes-base.scheduleTrigger", 1.2, [-380, -40],
             {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1,
                                     "triggerAtDay": [1], "triggerAtHour": 9, "triggerAtMinute": 0}]}}),
        node("Executar Manualmente", "n8n-nodes-base.manualTrigger", 1, [-380, 140], {}),

        config([-160, 40], {
            "PLANILHA_ID": "COLE_AQUI_O_ID_DA_PLANILHA",
            "EMPRESA": "Loja Exemplo",
            "MODELO_GEMINI": "gemini-3.6-flash",
            "REMETENTE": "voce@gmail.com",
            "DESTINATARIO_RELATORIO": "voce@gmail.com",
        }, notas="A chave do Gemini NÃO fica aqui — ela vive numa credencial "
                 "'Header Auth' do n8n, para não ir parar no JSON exportado."),

        sheets_ler("Ler Respostas", [60, 40], "respostas", alwaysOutputData=True),

        code("Montar Prompt", [280, 40], JS_PROMPT,
             notes="Sem respostas novas ⇒ nenhum item ⇒ o workflow termina sem chamar a IA (e sem custo)."),

        node("Gemini · Analisar", "n8n-nodes-base.httpRequest", 4.2, [500, 40],
             {
                 "method": "POST",
                 "url": "=https://generativelanguage.googleapis.com/v1beta/models/{{ $json.modelo }}:generateContent",
                 # Credencial nativa "Google Gemini(PaLM) Api": o n8n injeta a
                 # chave sozinho e tem teste de conexão embutido. Bem menos
                 # passos que montar um Header Auth na mão.
                 "authentication": "predefinedCredentialType",
                 "nodeCredentialType": "googlePalmApi",
                 "sendBody": True,
                 "contentType": "json",
                 "specifyBody": "json",
                 "jsonBody": "={{ JSON.stringify($json.corpo_gemini) }}",
                 "options": {"timeout": 120000},
             },
             retryOnFail=True, maxTries=5, waitBetweenTries=5000,
             alwaysOutputData=True, onError="continueRegularOutput",
             notes="Credencial: 'Google Gemini(PaLM) Api' (Predefined Credential Type). "
        "O corpo TEM de estar em Specify Body = Using JSON, com a expressão "
        "{{ JSON.stringify($json.corpo_gemini) }}. Em 'Using Fields Below' o Google "
        "recusa com 'Proto fields must have a name'. "
                   "Se a IA falhar, o fluxo continua e o relatório sai só com as métricas."),

        code("Consolidar Análise", [720, 40], JS_CONSOLIDAR),

        code("Uma Linha por Resposta", [940, -80], JS_ESPALHAR),
        sheets_gravar("Atualizar Respostas", [1160, -80], "respostas",
                      operacao="appendOrUpdate", chaves=["id_resposta"],
                      notes="Marca analisado_em: a próxima execução não reprocessa (nem paga por) o mesmo lote."),

        code("Preparar Linha da Análise", [940, 160],
             "return [{ json: $('Consolidar Análise').first().json.analise }];"),
        sheets_gravar("Gravar Análise", [1160, 160], "analise", operacao="append"),

        code("Montar Relatório", [1380, 160], JS_RELATORIO),
        node("Enviar Relatório", "n8n-nodes-base.emailSend", 2.1, [1600, 160],
             {
                 "fromEmail": "={{ $('Configuração').first().json.REMETENTE }}",
                 "toEmail": "={{ $('Configuração').first().json.DESTINATARIO_RELATORIO }}",
                 "subject": "={{ $json.assunto }}",
                 "emailFormat": "both",
                 "text": "={{ $json.corpo_texto }}",
                 "html": "={{ $json.corpo_html }}",
                 "options": {},
             }),
    ]

    conexoes = {
        "Toda Segunda 09:00": [["Configuração"]],
        "Executar Manualmente": [["Configuração"]],
        "Configuração": [["Ler Respostas"]],
        "Ler Respostas": [["Montar Prompt"]],
        "Montar Prompt": [["Gemini · Analisar"]],
        "Gemini · Analisar": [["Consolidar Análise"]],
        "Consolidar Análise": [["Uma Linha por Resposta", "Preparar Linha da Análise"]],
        "Uma Linha por Resposta": [["Atualizar Respostas"]],
        "Preparar Linha da Análise": [["Gravar Análise"]],
        "Gravar Análise": [["Montar Relatório"]],
        "Montar Relatório": [["Enviar Relatório"]],
    }
    salvar("3_analise_com_ia.json", "3 · Análise dos comentários com IA", nodes, conexoes)


if __name__ == "__main__":
    print("Gerando workflows:")
    workflow_convite()
    workflow_formulario()
    workflow_analise()
    print(f"\nOK — arquivos em {DESTINO}")
