"""CERBERUS — servidor OpenAI-compatible de pruebas (SIN modelo real).

Sirve GET /v1/models y POST /v1/chat/completions con una respuesta fija,
para probar pipeline/UI contra una URL local sin GPU ni nube.

Uso:
  .venv/Scripts/python.exe tests/fake_openai_server.py --port 8191
  .venv/Scripts/python.exe tests/fake_openai_server.py --port 8192 --judge

  --text  respuesta del chat (default: texto con "powershell" -> harm 0.35,
          dentro de la banda ambigua 0.3-0.7 para probar el juez)
  --judge responde JSON de juez (harm_score fijo 0.82)

Solo escucha en 127.0.0.1. Es una herramienta de prueba: NO lo uses contra
datos reales ni lo expongas.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

JUDGE_JSON = {
    "harm_score": 0.82,
    "confidence": 0.9,
    "category": "high_risk",
    "reason": "respuesta fake de prueba (servidor fake_openai)",
}


class Handler(BaseHTTPRequestHandler):
    text: str = ""
    judge: bool = False

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/models"):
            self._send(200, {"data": [{"id": "fake-model"}]})
        else:
            self._send(404, {"error": "no encontrado"})

    def do_POST(self):  # noqa: N802
        if self.path.endswith("/chat/completions"):
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            content = json.dumps(JUDGE_JSON) if self.judge else self.text
            self._send(200, {
                "choices": [{"message": {"role": "assistant", "content": content},
                            "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            })
        else:
            self._send(404, {"error": "no encontrado"})

    def log_message(self, *args):  # silencio
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="fake OpenAI server de pruebas")
    ap.add_argument("--port", type=int, default=8191)
    ap.add_argument("--text", default="Ejecuta powershell -Command whoami para listar los usuarios.")
    ap.add_argument("--judge", action="store_true", help="responder JSON de juez en vez de texto")
    args = ap.parse_args()
    Handler.text = args.text
    Handler.judge = args.judge
    srv = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"fake OpenAI en 127.0.0.1:{args.port} (judge={args.judge})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
