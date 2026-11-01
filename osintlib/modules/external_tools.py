"""
Módulo: integración con herramientas OSINT externas.

Este módulo satisface el requisito de "integración con al menos una herramienta
externa automatizada por línea de comandos y parseo de resultados". Está diseñado
como un registro ampliable de adaptadores: cada adaptador declara cómo detectar la
herramienta, cómo invocarla y cómo parsear su salida. Hoy incluye:

  - theHarvester : recolección de emails, hosts y subdominios de un dominio.
                   Se ejecuta con salida JSON y se parsea el fichero resultante.
  - holehe       : comprueba en qué servicios está registrado un email.
                   Se parsea su salida de texto.

Comportamiento clave: si la herramienta NO está instalada, el adaptador lo detecta
y devuelve estado 'not_installed' con la instrucción de instalación, SIN romper la
ejecución. Así la herramienta es robusta tanto si tienes el toolkit completo como
si no.

Para añadir otra herramienta externa basta con registrar un adaptador nuevo en
ADAPTERS siguiendo la misma interfaz.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Dict, List, Optional

from ..entity import Entity, Graph
from .base import BaseModule, Context, ModuleResult


def _which(*names: str) -> Optional[List[str]]:
    """
    Devuelve el comando base para ejecutar una herramienta:
    - Si existe un binario en PATH, lo usa.
    - Si no, intenta 'python -m <modulo>' cuando el módulo es importable.
    """
    for n in names:
        path = shutil.which(n)
        if path:
            return [path]
    # Fallback: ejecutar como módulo de Python (solo nombres de módulo válidos,
    # sin extensión ni puntos). find_spec puede lanzar si falta un paquete padre,
    # así que lo envolvemos para que la detección nunca rompa la ejecución.
    import importlib.util
    for n in names:
        if "." in n or "/" in n:
            continue
        try:
            if importlib.util.find_spec(n) is not None:
                return [sys.executable, "-m", n]
        except (ImportError, ValueError, ModuleNotFoundError):
            continue
    return None


# --------------------------------------------------------------------------
# Adaptador theHarvester
# --------------------------------------------------------------------------
def _theharvester(domain: str, graph: Graph, ctx: Context, res: ModuleResult) -> None:
    cmd_base = _which("theHarvester", "theHarvester.py")
    if not cmd_base:
        res.status = "not_installed"
        res.message = ("theHarvester no está instalado. Instálalo con "
                       "'pip install theHarvester' o desde "
                       "https://github.com/laramies/theHarvester")
        return

    dom_ent = graph.add_entity(Entity("domain", domain, sources=[self_name_th]))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "harvest")
        # -b bing,crtsh,... fuentes pasivas; -f fichero de salida (genera .json).
        cmd = cmd_base + ["-d", domain, "-b", "bing,crtsh,duckduckgo,otx",
                          "-f", out]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=int(ctx.config.get("settings", {}).get("ext_timeout", 180)))
        except subprocess.TimeoutExpired:
            res.status = "error"
            res.message = "theHarvester excedió el tiempo límite."
            return
        except Exception as exc:
            res.status = "error"
            res.message = f"No se pudo ejecutar theHarvester: {exc}"
            return

        data = None
        for cand in (out + ".json", out):
            if os.path.exists(cand):
                try:
                    with open(cand, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    break
                except Exception:
                    continue
        if data is None:
            res.message = ("theHarvester se ejecutó pero no produjo JSON parseable. "
                           f"Código de salida {proc.returncode}.")
            res.meta["stdout_tail"] = (proc.stdout or "")[-500:]
            return

        emails = data.get("emails", []) or []
        hosts = data.get("hosts", []) or []
        ips = data.get("ips", []) or []

        for em in emails:
            em_ent = graph.add_entity(Entity("email", str(em), sources=[self_name_th]))
            graph.add_relation(dom_ent, em_ent, "email_en_dominio", source=self_name_th)
        for h in hosts:
            host = str(h).split(":")[0]
            h_ent = graph.add_entity(Entity("host", host, sources=[self_name_th]))
            graph.add_relation(dom_ent, h_ent, "subdominio", source=self_name_th)
        for ip in ips:
            ip_ent = graph.add_entity(Entity("ip", str(ip), sources=[self_name_th]))
            graph.add_relation(dom_ent, ip_ent, "ip_asociada", source=self_name_th)

        res.findings.append({"herramienta": "theHarvester",
                             "emails": len(emails), "hosts": len(hosts), "ips": len(ips)})
        res.message = (f"theHarvester: {len(emails)} emails, {len(hosts)} hosts, "
                       f"{len(ips)} IPs.")


# --------------------------------------------------------------------------
# Adaptador holehe
# --------------------------------------------------------------------------
def _holehe(email: str, graph: Graph, ctx: Context, res: ModuleResult) -> None:
    cmd_base = _which("holehe")
    if not cmd_base:
        res.status = "not_installed"
        res.message = ("holehe no está instalado. Instálalo con 'pip install holehe' "
                       "o desde https://github.com/megadose/holehe")
        return

    email_ent = graph.add_entity(Entity("email", email, sources=[self_name_ho]))
    # --no-color: sin códigos ANSI alrededor de '[+]'; --no-clear: no borra la
    # pantalla. Sin ellos el parseo no encuentra nada.
    cmd = cmd_base + [email, "--only-used", "--no-color", "--no-clear"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=int(ctx.config.get("settings", {}).get("ext_timeout", 180)))
    except subprocess.TimeoutExpired:
        res.status = "error"
        res.message = "holehe excedió el tiempo límite."
        return
    except Exception as exc:
        res.status = "error"
        res.message = f"No se pudo ejecutar holehe: {exc}"
        return

    used = parse_holehe_output(proc.stdout or "")
    for item in used:
        service = item["servicio"]
        prof = graph.add_entity(Entity(
            "social_profile", f"{service}:{email}",
            label=f"{service} (holehe)", sources=[self_name_ho],
            attrs={"red": service, "fuente": "holehe", "url": f"https://{service}",
                   "pista_recuperacion": item.get("extra")},
        ))
        graph.add_relation(email_ent, prof, "cuenta_en", source=self_name_ho)
    res.findings.append({"herramienta": "holehe",
                         "servicios": [u["servicio"] for u in used]})
    res.message = f"holehe: {len(used)} servicio(s) con cuenta asociada."


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def parse_holehe_output(stdout: str) -> List[Dict[str, str]]:
    """
    Parsea la salida de texto de holehe.

    holehe marca con '[+] dominio [datos]' los servicios donde el email tiene
    cuenta. Se ignoran la línea de leyenda ('[+] Email used, ...') y se eliminan
    códigos de color por si alguna versión los emite igualmente.
    Devuelve [{'servicio': 'twitter.com', 'extra': 'pista de recuperación'}, ...].
    """
    out = []
    for raw in stdout.splitlines():
        line = _ANSI.sub("", raw).strip()
        if not line.startswith("[+]"):
            continue
        body = line[3:].strip()
        if not body or body.lower().startswith("email used"):
            continue  # leyenda final de holehe
        partes = body.split(None, 1)
        out.append({"servicio": partes[0], "extra": partes[1].strip() if len(partes) > 1 else ""})
    return out


# Nombres de fuente usados en las entidades (constantes de módulo).
self_name_th = "theHarvester"
self_name_ho = "holehe"


class ExternalToolsModule(BaseModule):
    name = "external_tools"
    description = "Integra herramientas externas (theHarvester, holehe) por CLI y parseo"
    accepts = ("domain", "email")

    def run(self, target_type: str, target_value: str, graph: Graph,
            ctx: Context) -> ModuleResult:
        res = ModuleResult(module=self.name, target=target_value)
        ran_any = False
        statuses = []

        if target_type in ("domain", "email"):
            # theHarvester trabaja sobre dominio.
            domain = target_value if target_type == "domain" else target_value.split("@")[-1]
            sub = ModuleResult(module="theHarvester", target=domain)
            _theharvester(domain, graph, ctx, sub)
            statuses.append(f"theHarvester: {sub.status} — {sub.message}")
            res.findings.extend(sub.findings)
            ran_any = ran_any or sub.status == "ok"

        if target_type == "email":
            sub = ModuleResult(module="holehe", target=target_value)
            _holehe(target_value, graph, ctx, sub)
            statuses.append(f"holehe: {sub.status} — {sub.message}")
            res.findings.extend(sub.findings)
            ran_any = ran_any or sub.status == "ok"

        res.message = " | ".join(statuses) if statuses else "Sin herramienta externa aplicable."
        res.status = "ok" if ran_any else "not_installed"
        res.meta["detalle"] = statuses
        return res
