/**
 * Executa o JavaScript de todos os nodes "Code" fora do n8n, com $input, $json
 * e $() simulados. Pega erro de lógica sem precisar de planilha, SMTP ou chave
 * de IA — e roda em menos de um segundo.
 *
 * Uso:  node tests/test_code_nodes.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
const wf = (arq) => JSON.parse(readFileSync(join(raiz, 'workflows', arq), 'utf8'));

const W1 = wf('1_convite_por_email.json');
const W2 = wf('2_formulario_e_respostas.json');
const W3 = wf('3_analise_com_ia.json');

const codigo = (w, nome) => {
  const n = w.nodes.find((x) => x.name === nome);
  if (!n) throw new Error(`node não encontrado: ${nome}`);
  return n.parameters.jsCode;
};
const cfgDoWorkflow = (w) => {
  const n = w.nodes.find((x) => x.name === 'Configuração');
  return Object.fromEntries(n.parameters.assignments.assignments.map((a) => [a.name, a.value]));
};

let falhas = 0;
const afirmar = (cond, desc) => {
  console.log((cond ? '  ✓ ' : '  ✗ FALHOU: ') + desc);
  if (!cond) falhas++;
};
const secao = (t) => console.log(`\n${t}`);

const embrulhar = (arr) => arr.map((j) => (j && typeof j === 'object' && 'json' in j ? j : { json: j }));

/** Roda um jsCode com o contexto do n8n simulado. */
function rodar(js, { entrada = [], nodes = {}, json = null } = {}) {
  const $input = { all: () => embrulhar(entrada), first: () => embrulhar(entrada)[0] };
  const $ = (nome) => {
    if (!(nome in nodes)) throw new Error(`node referenciado mas não simulado: ${nome}`);
    const itens = embrulhar(nodes[nome]);
    return { all: () => itens, first: () => itens[0], last: () => itens[itens.length - 1] };
  };
  const $json = json ?? (entrada.length ? embrulhar(entrada)[0].json : {});
  return new Function('$input', '$', '$json', js)($input, $, $json);
}

const ontem = (dias) => new Date(Date.now() - dias * 864e5).toISOString();

// ===========================================================================
secao('WORKFLOW 1 · Selecionar Pendentes');
{
  const cfg = cfgDoWorkflow(W1);
  const js = codigo(W1, 'Selecionar Pendentes');
  const vendas = [
    { id_venda: 'V-1', nome: 'Gustavo Silva', email: 'g@ex.com', produto: 'Fone', data_compra: ontem(3), convite_enviado_em: '' },
    { id_venda: 'V-2', nome: 'Marina Duarte', email: 'm@ex.com', produto: 'Cafeteira', data_compra: ontem(5), convite_enviado_em: '2026-08-01T10:00:00Z' },
    { id_venda: 'V-3', nome: 'Sem Email', email: 'nao-e-email', produto: 'X', data_compra: ontem(4), convite_enviado_em: '' },
    { id_venda: 'V-4', nome: 'Recente Demais', email: 'r@ex.com', produto: 'Y', data_compra: new Date().toISOString(), convite_enviado_em: '' },
    { id_venda: 'V-5', nome: 'Data BR', email: 'b@ex.com', produto: 'Z', data_compra: '01/08/2026', convite_enviado_em: '' },
    { id_venda: '', nome: 'Linha vazia', email: '', produto: '', data_compra: '', convite_enviado_em: '' },
  ];
  const r = rodar(js, { entrada: vendas, nodes: { 'Configuração': [cfg] } });
  const ids = r.map((i) => i.json.id_venda);

  afirmar(ids.includes('V-1'), 'inclui venda pendente com e-mail válido');
  afirmar(!ids.includes('V-2'), 'pula quem já recebeu convite');
  afirmar(!ids.includes('V-3'), 'pula e-mail inválido');
  afirmar(!ids.includes('V-4'), 'pula compra recente (janela de 24h)');
  afirmar(ids.includes('V-5'), 'entende data no formato brasileiro dd/mm/aaaa');
  afirmar(!ids.includes(''), 'ignora linha em branco da planilha');

  const t = r[0].json.token;
  afirmar(/^[a-z2-9]{24}$/.test(t), `token com 24 caracteres legíveis (${t})`);
  afirmar(new Set(r.map((i) => i.json.token)).size === r.length, 'cada venda recebe um token diferente');
  afirmar(r[0].json.link === `${cfg.URL_FORMULARIO}?t=${t}`, 'link montado a partir da configuração');
  afirmar(r[0].json.primeiro_nome === 'Gustavo', 'extrai o primeiro nome');

  const vazio = rodar(js, { entrada: [], nodes: { 'Configuração': [cfg] } });
  afirmar(Array.isArray(vazio) && vazio.length === 0, 'sem pendentes devolve zero itens');
}

secao('WORKFLOW 1 · Montar E-mail e Registrar Envio');
{
  const venda = { id_venda: 'V-1', nome: 'Gustavo Silva', primeiro_nome: 'Gustavo', email: 'g@ex.com',
                  telefone: '11999999999', produto: 'Fone Aurora X2', data_compra: ontem(3),
                  token: 'abc123', link: 'http://localhost:5678/webhook/feedback?t=abc123',
                  empresa: 'Loja Exemplo' };
  const [e] = rodar(codigo(W1, 'Montar E-mail'), { json: venda });
  afirmar(e.json.assunto.includes('Gustavo') && e.json.assunto.includes('Fone Aurora X2'),
    `assunto personalizado ("${e.json.assunto}")`);
  afirmar(e.json.corpo_html.includes(venda.link), 'link aparece no HTML');
  afirmar(e.json.corpo_texto.includes(venda.link), 'link aparece também na versão texto');
  afirmar(!/undefined|\[object/.test(e.json.corpo_html), 'HTML sem "undefined" vazando');

  const [reg] = rodar(codigo(W1, 'Preparar Registro'), { nodes: { 'Montar E-mail': [e.json] } });
  afirmar(reg.json.token === 'abc123', 'registro devolve o token gerado');
  afirmar(Boolean(Date.parse(reg.json.convite_enviado_em)), 'registro carimba a data de envio');
  const colunas = ['id_venda','data_compra','nome','email','telefone','produto','token','convite_enviado_em'];
  afirmar(colunas.every((c) => c in reg.json), 'registro tem exatamente as colunas da aba `vendas`');
}

// ===========================================================================
secao('WORKFLOW 2 · Renderizar Página');
{
  const js = codigo(W2, 'Renderizar Página');
  const cfg = cfgDoWorkflow(W2);
  const venda = { id_venda: 'V-1', nome: 'Gustavo Silva', produto: 'Fone Aurora X2',
                  telefone: '11999999999', token: 'abc123' };
  // linhas de outras vendas que também vêm na leitura da aba inteira
  const ruido = [
    { id_venda: 'V-0', nome: 'Outra Pessoa', produto: 'Cafeteira', telefone: '', token: 'zzz999' },
    { id_venda: 'V-2', nome: 'Mais Alguem', produto: 'Luminária', telefone: '', token: 'yyy888' },
  ];
  const contexto = (t, vendas, respostas) => ({
    nodes: {
      'Configuração': [cfg],
      'Webhook · Página do Formulário': [{ query: { t } }],
      'Buscar Venda': vendas,
      'Buscar Resposta': respostas,
    },
  });

  const [ok] = rodar(js, contexto('abc123', [...ruido, venda], []));
  const extrair = (html) => JSON.parse(
    html.match(/<script id="dados-venda" type="application\/json">([\s\S]*?)<\/script>/)[1]
        .replace(/\\u003c/g, '<'),
  );
  const d1 = extrair(ok.json.pagina);
  afirmar(d1.ok === true && d1.ja_respondeu === false, 'token válido ⇒ estado de formulário');
  afirmar(d1.primeiro_nome === 'Gustavo' && d1.produto === 'Fone Aurora X2', 'injeta nome e produto');
  afirmar(!ok.json.pagina.includes('__DADOS_DA_VENDA__'), 'placeholder foi substituído');
  afirmar(ok.json.pagina.trimStart().startsWith('<!doctype html>'), 'devolve a página HTML completa');

  const [inv] = rodar(js, contexto('', [], []));
  afirmar(extrair(inv.json.pagina).ok === false, 'sem token ⇒ estado de link inválido');
  const [inv2] = rodar(js, contexto('naoexiste', ruido, []));
  afirmar(extrair(inv2.json.pagina).ok === false, 'token inexistente ⇒ link inválido');

  const [rep] = rodar(js, contexto('abc123', [...ruido, venda], [
    { id_resposta: 'R-9', id_venda: 'V-0', respondido_em: '2026-01-01T00:00:00Z' },   // de outra venda
    { id_resposta: 'R-1', id_venda: 'V-1', respondido_em: '2026-08-12T14:30:00Z' },
  ]));
  const d2 = extrair(rep.json.pagina);
  afirmar(d2.ja_respondeu === true && d2.respondido_em.startsWith('2026-08-12'), 'já respondido ⇒ estado de repetição');

  const [xss] = rodar(js, contexto('abc123', [{ ...venda, produto: 'Fone </script><script>alert(1)</script>' }], []));
  const [outra] = rodar(js, contexto('yyy888', [...ruido, venda], []));
  afirmar(extrair(outra.json.pagina).produto === 'Luminária',
    'com a aba inteira em mãos, escolhe a venda do token pedido (não a primeira linha)');
  const [respOutra] = rodar(js, contexto('abc123', [...ruido, venda],
    [{ id_resposta: 'R-9', id_venda: 'V-0', respondido_em: 'x' }]));
  afirmar(extrair(respOutra.json.pagina).ja_respondeu !== true,
    'resposta de OUTRA venda não bloqueia esta');
  const bruto = xss.json.pagina.match(/<script id="dados-venda"[^>]*>([\s\S]*?)<\/script>/)[1];
  afirmar(!bruto.includes('</script>') && bruto.includes('\\u003c'),
    'nome de produto com </script> é escapado (não quebra a página)');
}

secao('WORKFLOW 2 · Validar Envio e Decidir');
{
  const jsV = codigo(W2, 'Validar Envio');
  const jsD = codigo(W2, 'Decidir');
  const venda = { id_venda: 'V-1', nome: 'Gustavo Silva', email: 'g@ex.com',
                  telefone: '1188887777', produto: 'Fone', token: 'abc123' };
  const outraVenda = { id_venda: 'V-7', nome: 'Fulano', email: 'f@ex.com',
                       telefone: '', produto: 'Cafeteira', token: 'outro999' };

  const validar = (body) => rodar(jsV, { nodes: { 'Webhook · Receber Resposta': [{ body }] } })[0].json;
  const decidir = (envio, vendas, respostas) => rodar(jsD, {
    nodes: { 'Validar Envio': [envio], 'Buscar Venda (envio)': vendas, 'Buscar Resposta (envio)': respostas },
  })[0].json;

  const bom = validar({ t: 'abc123', nota: 9, observacoes: '  Muito bom  ', telefone: '(11) 98765-4321' });
  afirmar(bom.nota === 9 && bom.nota_valida, 'nota 9 é aceita');
  afirmar(bom.telefone === '11987654321', 'telefone normalizado para só dígitos');
  afirmar(bom.observacoes === 'Muito bom', 'observações vêm sem espaço nas pontas');
  afirmar(validar({ t: 'a', nota: 0 }).nota_valida, 'nota 0 é válida (é uma nota, não ausência)');
  afirmar(!validar({ t: 'a', nota: 11 }).nota_valida, 'nota 11 é rejeitada');
  afirmar(!validar({ t: 'a', nota: 'dez' }).nota_valida, 'nota não numérica é rejeitada');
  afirmar(!validar({ t: 'a' }).nota_valida, 'nota ausente é rejeitada');
  afirmar(validar({ t: 'a', nota: 5, observacoes: 'x'.repeat(5000) }).observacoes.length === 1000,
    'observações são cortadas em 1000 caracteres');

  afirmar(decidir(bom, [outraVenda, venda], []).pode_gravar,
    'acha a venda certa no meio da aba inteira');
  afirmar(decidir(bom, [outraVenda], []).erro === 'token_invalido', 'token inexistente é recusado');
  afirmar(decidir(bom, [], []).erro === 'token_invalido', 'aba vazia ⇒ token inválido');
  afirmar(decidir(bom, [{ error: 'falha na planilha' }], []).erro === 'token_invalido',
    'node de planilha que falhou não vira venda válida');
  afirmar(decidir(bom, [venda], [{ id_resposta: 'R-1', id_venda: 'V-1' }]).erro === 'ja_respondido',
    'resposta duplicada é recusada');
  afirmar(decidir(bom, [venda], [{ id_resposta: 'R-9', id_venda: 'V-7' }]).pode_gravar,
    'resposta de outra venda NÃO bloqueia esta');
  afirmar(decidir(bom, [venda], []).codigo === 200, 'sucesso responde 200');
  afirmar(decidir(bom, [], []).codigo === 404, 'token inválido responde 404');
  afirmar(decidir(bom, [venda], [{ id_resposta: 'R-1', id_venda: 'V-1' }]).codigo === 409,
    'duplicado responde 409');
  afirmar(decidir(validar({ t: 'abc123', nota: 99 }), [venda], []).codigo === 400,
    'nota inválida (com token válido) responde 400');

  const robo = validar({ t: 'abc123', nota: 10, empresa_site: 'https://spam.example' });
  const dRobo = decidir(robo, [venda], []);
  afirmar(robo.robo === true, 'honeypot preenchido marca como robô');
  afirmar(!dRobo.pode_gravar && dRobo.codigo === 200,
    'robô não grava, mas recebe 200 (não revela que foi detectado)');
}

secao('WORKFLOW 2 · Montar Resposta');
{
  const js = codigo(W2, 'Montar Resposta');
  const venda = { id_venda: 'V-1', nome: 'Gustavo Silva', email: 'real@ex.com',
                  telefone: '1188887777', produto: 'Fone', token: 'abc123' };
  const outra = { id_venda: 'V-9', nome: 'Errado', email: 'errado@ex.com',
                  telefone: '', produto: 'Outro Produto', token: 'zzz' };
  const montar = (nota, extra = {}) => rodar(js, {
    nodes: {
      'Validar Envio': [{ nota, token: 'abc123', observacoes: 'ok', telefone: '11987654321', ...extra }],
      'Buscar Venda (envio)': [outra, venda],   // aba inteira, venda certa no meio
    },
  })[0].json;

  afirmar(montar(10).classificacao_nps === 'promotor', 'nota 10 ⇒ promotor');
  afirmar(montar(9).classificacao_nps === 'promotor', 'nota 9 ⇒ promotor');
  afirmar(montar(8).classificacao_nps === 'neutro', 'nota 8 ⇒ neutro');
  afirmar(montar(7).classificacao_nps === 'neutro', 'nota 7 ⇒ neutro');
  afirmar(montar(6).classificacao_nps === 'detrator', 'nota 6 ⇒ detrator');
  afirmar(montar(0).classificacao_nps === 'detrator', 'nota 0 ⇒ detrator');

  const r = montar(10);
  afirmar(r.email === 'real@ex.com', 'e-mail vem da planilha, não do navegador');
  afirmar(r.produto === 'Fone', 'produto vem da planilha, não do navegador');
  afirmar(/^R-/.test(r.id_resposta), 'id_resposta gerado com prefixo R-');
  const colunas = ['id_resposta','id_venda','respondido_em','nome','email','telefone','produto',
                   'nota','classificacao_nps','observacoes','sentimento','temas','analisado_em'];
  afirmar(colunas.every((c) => c in r), 'resposta tem exatamente as colunas da aba `respostas`');
}

// ===========================================================================
secao('WORKFLOW 3 · Montar Prompt');
{
  const js = codigo(W3, 'Montar Prompt');
  const cfg = cfgDoWorkflow(W3);
  const resp = (id, nota, obs, analisado = '') => ({
    id_resposta: id, id_venda: 'V' + id, nota, observacoes: obs, produto: 'Fone',
    respondido_em: '2026-08-1' + (id.length % 9) + 'T10:00:00Z', nome: 'N', email: 'e@x.com',
    telefone: '', classificacao_nps: '', analisado_em: analisado,
  });

  // 4 promotores, 1 neutro, 5 detratores  ⇒ NPS = (4-5)/10*100 = -10
  const lote = [
    resp('R1', 10, 'Som excelente'), resp('R2', 10, 'Chegou rápido'),
    resp('R3', 9, 'Muito bom'), resp('R4', 9, ''),
    resp('R5', 7, 'Ok'),
    resp('R6', 6, 'Bateria fraca'), resp('R7', 5, 'Demorou'),
    resp('R8', 3, 'Veio quebrado'), resp('R9', 0, 'Péssimo'), resp('R10', 2, 'Ruim'),
    resp('R99', 10, 'ja analisada', '2026-08-01T00:00:00Z'),
  ];
  const [p] = rodar(js, { entrada: lote, nodes: { 'Configuração': [cfg] } });
  const m = p.json.metricas;

  afirmar(m.respostas === 10, 'ignora respostas já analisadas (10 de 11)');
  afirmar(m.promotores === 4 && m.neutros === 1 && m.detratores === 5,
    `classificação NPS correta (${m.promotores}/${m.neutros}/${m.detratores})`);
  afirmar(m.nps === -10, `NPS calculado em JavaScript, não pela IA (${m.nps})`);
  afirmar(m.nota_media === 6.1, `nota média correta (${m.nota_media})`);
  // R4 não escreveu nada e R5 escreveu só "Ok" (2 caracteres): comentário curto
  // demais não ajuda a agrupar tema nenhum e só gasta token.
  afirmar(m.com_comentario === 8, 'conta só comentários com conteúdo (ignora vazio e "Ok")');

  const g = p.json.corpo_gemini;
  afirmar(g.generationConfig.responseMimeType === 'application/json', 'pede saída em JSON');
  afirmar(g.generationConfig.responseSchema.required.includes('classificacoes'), 'schema exige classificações');
  afirmar(g.generationConfig.temperature <= 0.3, 'temperatura baixa para tarefa de classificação');
  const prompt = g.contents[0].parts[0].text;
  afirmar(prompt.includes('[R8] nota 3'), 'comentários entram no prompt com id e nota');
  afirmar(!prompt.includes('[R99]'), 'resposta já analisada não entra no prompt');
  afirmar(!prompt.includes('e@x.com'), 'e-mail do cliente NÃO é enviado para a IA');

  const nada = rodar(js, { entrada: [resp('R1', 10, 'x', '2026-01-01')], nodes: { 'Configuração': [cfg] } });
  afirmar(nada.length === 0, 'nada novo ⇒ zero itens ⇒ não chama (nem paga) a IA');
}

secao('WORKFLOW 3 · Consolidar Análise');
{
  const js = codigo(W3, 'Consolidar Análise');
  const base = {
    metricas: { respostas: 3, com_comentario: 3, nps: 33, nota_media: 8, promotores: 2,
                neutros: 0, detratores: 1, periodo_de: '2026-08-10', periodo_ate: '2026-08-17' },
    lote: [
      { id_resposta: 'R1', id_venda: 'V1', nota: 10, produto: 'Fone', observacoes: 'ótimo', respondido_em: 'x', nome: 'A', email: 'a@x', telefone: '', classificacao_nps: 'promotor' },
      { id_resposta: 'R2', id_venda: 'V2', nota: 9, produto: 'Fone', observacoes: 'bom', respondido_em: 'x', nome: 'B', email: 'b@x', telefone: '', classificacao_nps: 'promotor' },
      { id_resposta: 'R3', id_venda: 'V3', nota: 3, produto: 'Fone', observacoes: 'ruim', respondido_em: 'x', nome: 'C', email: 'c@x', telefone: '', classificacao_nps: 'detrator' },
    ],
  };
  const respostaIA = (obj) => ({ candidates: [{ content: { parts: [{ text: JSON.stringify(obj) }] } }] });

  const bom = rodar(js, {
    json: respostaIA({
      resumo: 'Clientes gostam do som e reclamam do prazo.',
      temas: [{ tema: 'qualidade do som', mencoes: 2, tom: 'positivo' },
              { tema: 'prazo de entrega', mencoes: 1, tom: 'negativo' }],
      acoes: ['Revisar transportadora'],
      classificacoes: [
        { id_resposta: 'R1', sentimento: 'positivo', temas: 'qualidade do som' },
        { id_resposta: 'R2', sentimento: 'positivo', temas: 'qualidade do som' },
        { id_resposta: 'R3', sentimento: 'negativo', temas: 'prazo de entrega' },
      ],
    }),
    nodes: { 'Montar Prompt': [base] },
  })[0].json;

  afirmar(bom.analise.nps === 33, 'NPS vem das métricas, não da IA');
  afirmar(bom.analise.sentimento_positivo === 2 && bom.analise.sentimento_negativo === 1,
    'contagem de sentimento bate com as classificações');
  afirmar(bom.respostas.length === 3 && bom.respostas.every((r) => r.analisado_em),
    'todas as respostas do lote são marcadas como analisadas');
  afirmar(bom.respostas.find((r) => r.id_resposta === 'R3').sentimento === 'negativo',
    'sentimento é associado à resposta certa');
  afirmar(bom.analise.temas_principais.includes('qualidade do som (2, positivo)'),
    'temas viram texto legível para a planilha');

  const quebrado = rodar(js, { json: { erro: 'timeout' }, nodes: { 'Montar Prompt': [base] } })[0].json;
  afirmar(quebrado.falha_ia !== '', 'falha da IA é registrada');
  afirmar(quebrado.analise.nps === 33, 'métricas saem mesmo com a IA fora do ar');
  afirmar(quebrado.analise.resumo.includes('indisponível'), 'resumo avisa que a IA falhou');
  afirmar(quebrado.respostas.every((r) => r.analisado_em),
    'lote é marcado como analisado mesmo assim (não repete a chamada em loop)');

  const lixo = rodar(js, {
    json: { candidates: [{ content: { parts: [{ text: 'isso não é json' }] } }] },
    nodes: { 'Montar Prompt': [base] },
  })[0].json;
  afirmar(lixo.falha_ia !== '', 'resposta não-JSON da IA não derruba o workflow');
}

secao('WORKFLOW 3 · Relatório');
{
  const consolidado = {
    analise: { gerado_em: 'x', periodo_de: '2026-08-10', periodo_ate: '2026-08-17', respostas: 3,
               nps: 33, nota_media: 8, promotores: 2, neutros: 0, detratores: 1,
               sentimento_positivo: 2, sentimento_neutro: 0, sentimento_negativo: 1,
               temas_principais: 'som (2, positivo)', resumo: 'Resumo aqui.',
               acoes_sugeridas: 'Revisar transportadora' },
    ia: { temas: [{ tema: 'qualidade do som', mencoes: 2, tom: 'positivo' }], acoes: ['Revisar transportadora'] },
  };
  const [rel] = rodar(codigo(W3, 'Montar Relatório'), {
    nodes: { 'Consolidar Análise': [consolidado], 'Configuração': [cfgDoWorkflow(W3)] },
  });
  afirmar(rel.json.assunto.includes('NPS 33'), `assunto traz o número principal ("${rel.json.assunto}")`);
  afirmar(rel.json.corpo_html.includes('Resumo aqui.'), 'resumo da IA entra no e-mail');
  afirmar(rel.json.corpo_html.includes('qualidade do som'), 'temas entram no e-mail');
  afirmar(!/undefined|\[object|NaN/.test(rel.json.corpo_html), 'HTML sem undefined/NaN vazando');

  const vazio = rodar(codigo(W3, 'Montar Relatório'), {
    nodes: { 'Consolidar Análise': [{ ...consolidado, ia: { temas: [], acoes: [] } }],
             'Configuração': [cfgDoWorkflow(W3)] },
  })[0].json;
  afirmar(vazio.corpo_html.includes('Sem comentários em texto'), 'período sem comentários tem texto próprio');
}

// ===========================================================================
console.log('\n' + '='.repeat(64));
if (falhas) {
  console.log(`${falhas} verificação(ões) falharam.`);
  process.exit(1);
}
console.log('Todos os testes passaram.');
