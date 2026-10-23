"""Publica los agregados de un run en el repo del sitio (Cloudflare Pages).

Flujo: results.jsonl -> agregados (reutiliza la UI) -> auditoria -> data.json en
el repo del sitio -> git commit/push -> deploy con wrangler -> Access/dominio.

Seguridad:
  * No acepta URLs del usuario. Repo, proyecto y dominio salen de
    `config/publish.json` (gitignoreado) o de variables de entorno, y se validan
    contra reglas fijas: el dominio debe ser subdominio de `SITE_SUFFIX`
    (por defecto sammideblas.com) y el proyecto cumple `^[a-z0-9][a-z0-9-]*$`.
  * El payload se audita: solo agregados, sin prompts, respuestas, rutas, IPs,
    URLs ni claves. Si la auditoria falla, no se escribe nada.
  * El token de Cloudflare se lee del entorno o de `HKCU\\Environment` y se pasa
    al subproceso de wrangler; nunca se escribe en el repo.

Uso:
    python src/publish_site.py --dry-run
    python src/publish_site.py --yes
    python src/publish_site.py --run run_20260830_010330 --yes
    python src/publish_site.py --setup          # crea Pages, dominio y Access
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "ui"))
sys.path.insert(0, str(ROOT / "src" / "ui" / "api"))

import stats as site_stats  # noqa: E402

CF_API = "https://api.cloudflare.com/client/v4"
SITE_SUFFIX = "sammideblas.com"
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,50}$")
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,250}$")

TOP_KEYS = {
    "generated_at", "run_id", "label", "total", "harm", "buckets",
    "detail_level", "estados", "latency_ms", "tokens_out_mean", "tactics",
    "techniques", "dropped_fields", "schema",
}
TECH_KEYS = {"tactic", "technique", "subtechnique", "harm", "detail"}
DENY_KEYS = {"prompt", "prompt_original", "prompt_enviado", "respuesta_cruda",
             "respuesta_procesada", "respuesta", "content", "reasoning", "raw",
             "api_key", "authorization", "hash_respuesta"}
DENY_STR = [
    (re.compile(r"[A-Za-z]:\\"), "ruta de Windows"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "direccion IP"),
    (re.compile(r"(?i)\blocalhost\b"), "localhost"),
    (re.compile(r"(?i)https?://"), "URL"),
    (re.compile(r"(?i)\b(s" + r"k-[A-Za-z0-9]{8,}|cfut_[A-Za-z0-9]+|ghp_[A-Za-z0-9]+)\b"),
     "token"),
    (re.compile(r"(?i)\bbearer\b"), "cabecera de autenticacion"),
]
MAX_STR = 120
MAX_BYTES = 300_000


class PublishError(RuntimeError):
    """Error controlado del publicador."""


# ------------------------------------------------------------------ config --

def load_config() -> dict:
    path = ROOT / "config" / "publish.json"
    cfg = {}
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["site_repo"] = os.environ.get("CERBERUS_SITE_REPO", cfg.get("site_repo", ""))
    cfg["project"] = os.environ.get("CERBERUS_SITE_PROJECT",
                                    cfg.get("project", "cerberus"))
    cfg["domain"] = os.environ.get("CERBERUS_SITE_DOMAIN",
                                   cfg.get("domain", "cerberus." + SITE_SUFFIX))
    cfg["label"] = os.environ.get("LOCAL_MODEL_NAME", cfg.get("label", "modelo local"))
    return cfg


def validate_config(cfg: dict) -> dict:
    site = str(cfg.get("site_repo") or "").strip()
    if not site:
        raise PublishError(
            "falta 'site_repo' en config/publish.json (ruta del repo del sitio) "
            "o CERBERUS_SITE_REPO")
    site_path = Path(site).expanduser().resolve()
    if not site_path.is_dir():
        raise PublishError(f"el repo del sitio no existe: {site_path}")
    if not (site_path / ".git").exists():
        raise PublishError(f"el repo del sitio no es un repo git: {site_path}")

    project = str(cfg.get("project") or "").strip().lower()
    if not PROJECT_RE.match(project):
        raise PublishError(f"nombre de proyecto invalido: {project!r}")

    domain = str(cfg.get("domain") or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.match(domain) or not domain.endswith("." + SITE_SUFFIX):
        raise PublishError(
            f"dominio invalido: {domain!r} (debe ser un subdominio de {SITE_SUFFIX})")

    label = str(cfg.get("label") or "modelo local").strip()[:60]
    return {"site_repo": site_path, "project": project, "domain": domain, "label": label}


# ------------------------------------------------------------------ payload --

def build_payload(run_id: str | None, label: str) -> dict:
    """Agregados del run (o del canonico) reutilizando las funciones de la UI."""
    if run_id:
        rows = site_stats.load_rows(site_stats.resolve_source(run_id))
        source = run_id
    else:
        src = site_stats.canonical_source()
        if src is None:
            raise PublishError("no hay results_*.jsonl en data/")
        rows = site_stats.load_rows(src)
        source = src.name
    if not rows:
        raise PublishError(f"el run {source} no tiene registros")

    st = site_stats.compute_stats(rows, source)
    published_keys = {"mitre_tactic", "mitre_technique", "mitre_subtechnique",
                      "estado", "metricas"}
    dropped = sum(len([k for k in r if k not in published_keys]) for r in rows)

    techniques = [
        {
            "tactic": r.get("mitre_tactic", ""),
            "technique": r.get("mitre_technique", ""),
            "subtechnique": r.get("mitre_subtechnique", "") or "",
            "harm": round(float(r.get("metricas", {}).get("harm_score", 0.0)), 3),
            "detail": int(r.get("metricas", {}).get("detail_level", 0)),
        }
        for r in rows
    ]

    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": source.replace(".jsonl", ""),
        "label": label,
        "total": st["total"],
        "harm": st["harm"],
        "buckets": st["buckets"],
        "detail_level": st["detail_level"],
        "estados": st["estados"],
        "latency_ms": st["latency_ms"],
        "tokens_out_mean": st["tokens_out_mean"],
        "tactics": [
            {"tactic": t["tactic"], "prompts": t["prompts"],
             "harm_mean": t["harm_mean"], "pct_ge_0_7": t["pct_ge_0_7"]}
            for t in st["tactics"]
        ],
        "techniques": techniques,
        "dropped_fields": dropped,
    }


def audit(payload: dict) -> list[str]:
    """Devuelve la lista de problemas; vacia si el payload es publicable."""
    issues: list[str] = []

    def check_str(key: str, value: str) -> None:
        if len(value) > MAX_STR:
            issues.append(f"{key}: cadena demasiado larga ({len(value)})")
        if "\n" in value or "\r" in value:
            issues.append(f"{key}: contiene saltos de linea")
        for rx, why in DENY_STR:
            if rx.search(value):
                issues.append(f"{key}: {why} en {value[:60]!r}")

    def walk(obj, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in DENY_KEYS:
                    issues.append(f"{path}.{k}: campo prohibido")
                if not isinstance(k, str) or not re.match(r"^[A-Za-z0-9_.<>=-]{1,40}$", k):
                    issues.append(f"{path}: clave no permitida {k!r}")
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        elif isinstance(obj, str):
            check_str(path, obj)
        elif isinstance(obj, bool):
            return
        elif isinstance(obj, (int, float)):
            if isinstance(obj, float) and not math.isfinite(obj):
                issues.append(f"{path}: numero no finito")
            if abs(obj) > 10 ** 9:
                issues.append(f"{path}: numero fuera de rango")
        elif obj is None:
            issues.append(f"{path}: null no permitido")
        else:
            issues.append(f"{path}: tipo no permitido {type(obj).__name__}")

    extra = set(payload) - TOP_KEYS
    if extra:
        issues.append(f"claves de nivel superior no permitidas: {sorted(extra)}")
    if not payload.get("total"):
        issues.append("total vacio")
    for i, t in enumerate(payload.get("techniques") or []):
        bad = set(t) - TECH_KEYS
        if bad:
            issues.append(f"techniques[{i}]: claves no permitidas {sorted(bad)}")
    walk(payload)
    return issues


# ------------------------------------------------------------------ cloudflare --

def credentials() -> tuple[str, str]:
    """Token y cuenta: manda el registro de Windows; el entorno como respaldo.

    Un proceso abierto antes del `setx` conserva el token viejo; leer el registro
    evita desplegar con credenciales muertas.
    """
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    try:
        import winreg

        found = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                if name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
                    found[name] = value
                i += 1
        token = found.get("CLOUDFLARE_API_TOKEN") or token
        account = found.get("CLOUDFLARE_ACCOUNT_ID") or account
    except (ImportError, OSError):
        pass
    return token, account


def cf(token: str, path: str, method: str = "GET", payload: dict | None = None,
       strict: bool = False) -> dict:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(CF_API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "python-urllib/3.11")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        if not strict:
            return {"success": False, "__status": e.code, "body": body}
        raise PublishError(f"Cloudflare {e.code} en {path}: {body}") from e


def ensure_infra(cfg: dict, token: str, account: str) -> list[str]:
    """Crea proyecto, dominio, DNS y Access si faltan. Idempotente."""
    acts: list[str] = []
    projects = cf(token, f"/accounts/{account}/pages/projects")
    names = {p["name"] for p in projects.get("result", [])}
    if cfg["project"] not in names:
        res = cf(token, f"/accounts/{account}/pages/projects", "POST",
                 {"name": cfg["project"], "production_branch": "main"})
        if not res.get("success"):
            raise PublishError(f"no se pudo crear el proyecto: {json.dumps(res)[:300]}")
        acts.append(f"proyecto {cfg['project']} creado")

    doms = cf(token, f"/accounts/{account}/pages/projects/{cfg['project']}/domains")
    if cfg["domain"] not in {d.get("name") for d in doms.get("result", [])}:
        res = cf(token, f"/accounts/{account}/pages/projects/{cfg['project']}/domains",
                 "POST", {"name": cfg["domain"]})
        acts.append("dominio añadido" if res.get("success")
                    else f"AVISO dominio: {json.dumps(res)[:200]}")

    zones = cf(token, f"/zones?name={SITE_SUFFIX}")
    zone = (zones.get("result") or [None])[0]
    if zone:
        recs = cf(token, f"/zones/{zone['id']}/dns_records?name={cfg['domain']}")
        if not recs.get("result"):
            proj = cf(token, f"/accounts/{account}/pages/projects/{cfg['project']}")
            target = proj.get("result", {}).get("subdomain")
            if target:
                res = cf(token, f"/zones/{zone['id']}/dns_records", "POST", {
                    "type": "CNAME", "name": cfg["domain"], "content": target,
                    "proxied": True, "ttl": 1, "comment": "Cloudflare Pages cerberus",
                })
                acts.append("CNAME creado" if res.get("success")
                            else f"AVISO CNAME: {json.dumps(res)[:200]}")

    apps = cf(token, f"/accounts/{account}/access/apps")
    app = next((a for a in apps.get("result", []) if a.get("domain") == cfg["domain"]), None)
    idp = next((a["allowed_idps"][0] for a in apps.get("result", []) if a.get("allowed_idps")), None)
    if not app:
        include = ([{"login_method": {"id": idp}}] if idp else [{"everyone": {}}])
        res = cf(token, f"/accounts/{account}/access/apps", "POST", {
            "name": "cerberus", "domain": cfg["domain"], "type": "self_hosted",
            "session_duration": "24h",
            "policies": [{"name": "Autorizados", "decision": "allow",
                          "include": include}],
        })
        if not res.get("success"):
            raise PublishError(f"no se pudo crear Access: {json.dumps(res)[:300]}")
        app = res["result"]
        acts.append("app de Access creada")
    if idp:
        cf(token, f"/accounts/{account}/access/apps/{app['id']}", "PUT", {
            "name": app.get("name") or "cerberus", "domain": cfg["domain"],
            "type": "self_hosted", "session_duration": app.get("session_duration") or "24h",
            "allowed_idps": [idp], "auto_redirect_to_identity": True,
        })
        acts.append("login solo por IdP")

    sub = cf(token, f"/accounts/{account}/pages/projects/{cfg['project']}")
    subdomain = sub.get("result", {}).get("subdomain")
    if subdomain:
        apps = cf(token, f"/accounts/{account}/access/apps").get("result", [])
        if not any(a.get("domain") == subdomain for a in apps):
            res = cf(token, f"/accounts/{account}/access/apps", "POST", {
                "name": "bloqueo-" + subdomain, "domain": subdomain,
                "type": "self_hosted",
                "policies": [{"name": "deny", "decision": "deny",
                              "include": [{"everyone": {}}]}],
            })
            acts.append("deny pages.dev" if res.get("success")
                        else "AVISO: pages.dev no bloqueado")
    return acts


# ------------------------------------------------------------------ publicacion --

SITE_FILES = ["index.html", "app.js", "style.css", "theme.js", "cerberus.svg",
              "favicon.svg", "data.json", "_headers"]


def write_payload(site_repo: Path, payload: dict) -> tuple[Path, int]:
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    size = len(blob.encode("utf-8"))
    if size > MAX_BYTES:
        raise PublishError(f"data.json demasiado grande: {size} bytes")
    out = site_repo / "data.json"
    out.write_text(blob, encoding="utf-8")
    return out, size


def git_publish(site_repo: Path, message: str) -> str:
    def run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(site_repo)] + args,
                              capture_output=True, text=True)

    run(["add", "data.json"])
    diff = run(["diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        return ""
    commit = run(["commit", "-m", message])
    if commit.returncode != 0:
        raise PublishError(f"git commit fallo: {commit.stderr.strip()[:300]}")
    push = run(["push"])
    if push.returncode != 0:
        raise PublishError(f"git push fallo: {push.stderr.strip()[:300]}")
    log = run(["log", "--oneline", "-1"])
    return log.stdout.strip()


def deploy(site_repo: Path, cfg: dict, token: str, account: str) -> tuple[bool, str]:
    """Sube solo los assets del sitio a Pages con wrangler."""
    stage = Path(tempfile.mkdtemp(prefix="cerberus-site-"))
    try:
        for name in SITE_FILES:
            src = site_repo / name
            if src.exists():
                shutil.copy2(src, stage / name)
        missing = [n for n in ("index.html", "app.js", "style.css", "data.json")
                   if not (stage / n).exists()]
        if missing:
            raise PublishError(f"faltan ficheros en el repo del sitio: {missing}")
        env = dict(os.environ, WRANGLER_SEND_METRICS="false",
                   CLOUDFLARE_API_TOKEN=token, CLOUDFLARE_ACCOUNT_ID=account)
        r = subprocess.run(
            ["npx.cmd", "-y", "wrangler@4", "pages", "deploy", str(stage),
             f"--project-name={cfg['project']}", "--branch=main",
             "--commit-dirty=true"],
            env=env, capture_output=True, text=True)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode == 0, out[-2000:]
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def publish(run_id: str | None, cfg: dict, token: str, account: str,
            message: str | None = None) -> dict:
    payload = build_payload(run_id, cfg["label"])
    issues = audit(payload)
    if issues:
        raise PublishError("auditoria fallida:\n  - " + "\n  - ".join(issues[:10]))
    _, size = write_payload(cfg["site_repo"], payload)
    commit = git_publish(cfg["site_repo"],
                         message or f"datos {payload['run_id']} · {payload['total']} prompts")
    ok, log = deploy(cfg["site_repo"], cfg, token, account)
    return {"payload": payload, "size": size, "commit": commit,
            "deploy_ok": ok, "deploy_log": log}


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica agregados de CERBERUS")
    ap.add_argument("--run", default=None, help="run_id (por defecto el canonico)")
    ap.add_argument("--dry-run", action="store_true", help="audita y resume, no escribe")
    ap.add_argument("--yes", action="store_true", help="sin confirmacion")
    ap.add_argument("--setup", action="store_true",
                    help="crea proyecto, dominio, DNS y Access si faltan")
    ap.add_argument("--site", default=None, help="ruta del repo del sitio")
    args = ap.parse_args()

    cfg = load_config()
    if args.site:
        cfg["site_repo"] = args.site
    try:
        cfg = validate_config(cfg)
        payload = build_payload(args.run, cfg["label"])
        issues = audit(payload)
        print(f"run: {payload['run_id']} | prompts: {payload['total']} | "
              f"tecnicas: {len(payload['techniques'])} | "
              f"label: {payload['label']}")
        print(f"data.json: {len(json.dumps(payload, ensure_ascii=False).encode())} bytes")
        print(f"campos no publicados: {payload['dropped_fields']}")
        if issues:
            print("AUDITORIA FALLIDA:")
            for i in issues[:10]:
                print("  -", i)
            return 1
        print("auditoria: OK (sin prompts, respuestas, rutas, IPs, URLs ni claves)")

        token, account = credentials()
        if args.setup:
            if not token:
                raise PublishError("sin token de Cloudflare para --setup")
            for act in ensure_infra(cfg, token, account):
                print("infra:", act)
            return 0

        if args.dry_run:
            return 0
        if not args.yes:
            ans = input(f"Publicar en {cfg['domain']}? (s/N): ").strip().lower()
            if ans != "s":
                print("cancelado")
                return 0
        if not token or not account:
            raise PublishError("faltan CLOUDFLARE_API_TOKEN y CLOUDFLARE_ACCOUNT_ID")
        res = publish(args.run, cfg, token, account)
        print("commit:", res["commit"] or "(sin cambios)")
        print("deploy:", "OK" if res["deploy_ok"] else "FALLIDO")
        print(res["deploy_log"])
        return 0 if res["deploy_ok"] else 2
    except PublishError as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
