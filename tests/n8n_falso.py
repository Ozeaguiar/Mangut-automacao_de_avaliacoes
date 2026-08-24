"""
n8n falso: responde os dois webhooks do formulário para testar a página
sem precisar subir a stack inteira. Também serve o HTML.

Uso:  python tests/n8n_falso.py            (porta 5678, site em 8080)
Depois abra:  http://localhost:8080/formulario.html?t=demo-1
"""

import json
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parents[1]

# "planilha" em memória, com os mesmos campos da aba `vendas`
VENDAS = {
    "demo-1": {
        "id_venda": "V-1041", "nome": "Gustavo Silva", "email": "gustavo@exemplo.com",
        "telefone": "11987654321", "produto": "Fone Bluetooth Aurora X2",
    },
    "demo-2": {
        "id_venda": "V-1042", "nome": "Marina Duarte", "email": "marina@exemplo.com",
        "telefone": "21996541230", "produto": "Cafeteira Prensa Nórdica",
    },
    # já respondida, para exercitar a tela de repetição
    "demo-usada": {
        "id_venda": "V-1000", "nome": "Ana Prado", "email": "ana@exemplo.com",
        "telefone": "11912345678", "produto": "Luminária Arco",
        "respondido_em": "2026-08-12T14:30:00Z",
    },
}
RESPOSTAS: list[dict] = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencia o log padrão
        pass

    # ------------------------------------------------------------------ util
    def _json(self, codigo: int, corpo: dict):
        dados = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/webhook/feedback/dados":
            token = (parse_qs(u.query).get("t") or [""])[0]
            venda = VENDAS.get(token)
            if not venda:
                return self._json(404, {"ok": False, "erro": "token_invalido"})
            if "respondido_em" in venda or any(r["token"] == token for r in RESPOSTAS):
                quando = venda.get("respondido_em") or next(
                    r["respondido_em"] for r in RESPOSTAS if r["token"] == token
                )
                return self._json(200, {"ok": True, "ja_respondeu": True, "respondido_em": quando})
            return self._json(200, {
                "ok": True, "ja_respondeu": False,
                "primeiro_nome": venda["nome"].split()[0],
                "produto": venda["produto"], "telefone": venda["telefone"],
                "empresa": "Loja Exemplo",
            })
        return self._json(404, {"ok": False, "erro": "rota_desconhecida"})

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        if urlparse(self.path).path != "/webhook/feedback/enviar":
            return self._json(404, {"ok": False, "erro": "rota_desconhecida"})

        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "erro": "json_invalido"})

        token = str(corpo.get("t", ""))
        venda = VENDAS.get(token)
        if not venda:
            return self._json(404, {"ok": False, "erro": "token_invalido"})
        if corpo.get("empresa_site"):                       # honeypot preenchido
            return self._json(200, {"ok": True, "ignorado": True})
        if any(r["token"] == token for r in RESPOSTAS) or "respondido_em" in venda:
            return self._json(409, {"ok": False, "erro": "ja_respondido"})

        try:
            nota = int(corpo.get("nota"))
            assert 0 <= nota <= 10
        except (TypeError, ValueError, AssertionError):
            return self._json(400, {"ok": False, "erro": "nota_invalida"})

        RESPOSTAS.append({
            "token": token, "id_venda": venda["id_venda"], "nome": venda["nome"],
            "email": venda["email"], "produto": venda["produto"], "nota": nota,
            "telefone": re.sub(r"\D", "", str(corpo.get("telefone", ""))),
            "observacoes": str(corpo.get("observacoes", ""))[:1000],
            "respondido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        return self._json(200, {"ok": True, "id_resposta": f"R-{len(RESPOSTAS):04d}"})


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        nome = urlparse(self.path).path.lstrip("/") or "formulario.html"
        arq = RAIZ / "site" / nome
        if not arq.exists() or not arq.is_file():
            self.send_response(404); self.end_headers(); return
        dados = arq.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)


def subir():
    api = ThreadingHTTPServer(("127.0.0.1", 5678), Handler)
    site = ThreadingHTTPServer(("127.0.0.1", 8080), Site)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    threading.Thread(target=site.serve_forever, daemon=True).start()
    return api, site


if __name__ == "__main__":
    subir()
    print("n8n falso  → http://localhost:5678/webhook/feedback/dados?t=demo-1")
    print("formulário → http://localhost:8080/formulario.html?t=demo-1")
    print("Ctrl+C para sair.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
