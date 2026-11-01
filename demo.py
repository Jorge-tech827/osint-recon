#!/usr/bin/env python3
"""
demo.py — ejemplo REAL de ejecución con resultados FICTICIOS.

Lanza el CLI de verdad (osint.main) con todos los módulos sobre una persona
inventada. Lo único que se sustituye es lo que saldría a Internet:

  - Las peticiones HTTP (redes sociales, XposedOrNot, Interpol, Google News,
    Nominatim, la web del dominio) se sirven con respuestas simuladas que imitan
    el formato real de cada API.
  - DNS y WHOIS devuelven registros inventados.
  - theHarvester y holehe se sustituyen por pequeños simuladores que imprimen /
    escriben su salida con el formato real, de modo que el adaptador del módulo
    external_tools los ejecuta como procesos externos y parsea su salida igual
    que con las herramientas reales.

Todo lo demás es la herramienta real: clasificación de entradas, módulos,
correlación, grafo con Graphviz, informe HTML/JSON, mapa y PDF con Chromium.

Datos ficticios usados:
  - Persona inventada: «Mateo Rivas Olmedo».
  - Dominio .example (reservado para documentación por la RFC 2606).
  - IPs 192.0.2.x (rango reservado para documentación, RFC 5737).
  - Teléfono: el número de ejemplo oficial de la librería phonenumbers.

Uso (Linux/macOS):   python3 demo.py
Resultado en:        ejemplo/
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

OUT_DIR = "ejemplo"
FOTO = os.path.join(OUT_DIR, "foto_ejemplo.jpg")

PERSONA = "Mateo Rivas Olmedo"
USERNAME = "mateorivas"
DOMINIO = "rivas-fotografia.example"
EMAIL = f"mateo.rivas@{DOMINIO}"
TELEFONO = "+34 612 34 56 78"          # número de ejemplo oficial de phonenumbers
ULTIMA_VEZ = "Estación de Atocha, Madrid"


# ---------------------------------------------------------------------------
# 1) Foto de ejemplo con EXIF (GPS, fecha y dispositivo inventados)
# ---------------------------------------------------------------------------
def crear_foto():
    import piexif
    from PIL import Image, ImageDraw

    def dms(dd):
        d = int(abs(dd))
        m = int((abs(dd) - d) * 60)
        s = round((((abs(dd) - d) * 60) - m) * 6000)
        return ((d, 1), (m, 1), (s, 100))

    lat, lon = 40.41300, -3.68100  # barrio de Salamanca, Madrid
    gps = {piexif.GPSIFD.GPSLatitudeRef: "N", piexif.GPSIFD.GPSLatitude: dms(lat),
           piexif.GPSIFD.GPSLongitudeRef: "W", piexif.GPSIFD.GPSLongitude: dms(lon)}
    exif = {piexif.ExifIFD.DateTimeOriginal: b"2026:10:20 18:30:45"}
    zeroth = {piexif.ImageIFD.Make: b"Samsung", piexif.ImageIFD.Model: b"Galaxy S23"}

    img = Image.new("RGB", (480, 320), (196, 210, 212))
    d = ImageDraw.Draw(img)
    d.ellipse((200, 70, 280, 150), fill=(150, 168, 172))
    d.rectangle((170, 165, 310, 300), fill=(150, 168, 172))
    d.text((12, 12), "FOTO DE EJEMPLO (ficticia)", fill=(60, 70, 72))
    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(FOTO, exif=piexif.dump({"0th": zeroth, "Exif": exif, "GPS": gps}))


# ---------------------------------------------------------------------------
# 2) Red simulada (formato real de cada API, datos inventados)
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status=200, data=None, content=b"", headers=None, url=""):
        self.status_code = status
        self._data = data
        self.content = content
        self.headers = headers or {}
        self.url = url

    def json(self):
        if self._data is None:
            raise ValueError("sin JSON")
        return self._data

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# Perfiles que "existen" para el username mateorivas.
PERFILES = ("github.com/", "twitch.tv/", "reddit.com/user/", "keybase.io/", "chess.com/member/")

BRECHAS_POR_EMAIL = {
    EMAIL: ["ForoFotografiaDemo", "TiendaOnlineDemo"],
    f"mrivas@{DOMINIO}": ["ForoFotografiaDemo"],
}
DETALLE_BRECHAS = [
    {"breach": "ForoFotografiaDemo", "domain": "foro-foto.example", "xposed_date": "2022",
     "xposed_records": 48210, "verified": "Yes",
     "xposed_data": "Email addresses;Usernames;Passwords",
     "details": "Brecha ficticia de un foro de fotografía (datos de ejemplo)."},
    {"breach": "TiendaOnlineDemo", "domain": "tienda.example", "xposed_date": "2020",
     "xposed_records": 125300, "verified": "Yes",
     "xposed_data": "Email addresses;Phone numbers;Physical addresses",
     "details": "Brecha ficticia de una tienda online (datos de ejemplo)."},
]

RSS = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<title>"{PERSONA}" - Google News</title>
<item><title>La familia de Mateo Rivas pide ayuda para encontrarle - Diario de Ejemplo</title>
<link>https://news.example/articulo/familia-pide-ayuda</link>
<pubDate>Mon, 19 Oct 2026 09:15:00 GMT</pubDate><source url="https://diario.example">Diario de Ejemplo</source></item>
<item><title>Vecinos de Atocha organizan una batida de búsqueda - Noticias Ficticias</title>
<link>https://news.example/articulo/batida-atocha</link>
<pubDate>Thu, 22 Oct 2026 18:40:00 GMT</pubDate><source url="https://noticias.example">Noticias Ficticias</source></item>
<item><title>Siguen sin pistas sobre el paradero de Mateo Rivas - Crónica Demo</title>
<link>https://news.example/articulo/sin-pistas</link>
<pubDate>Sat, 24 Oct 2026 08:00:00 GMT</pubDate><source url="https://cronica.example">Crónica Demo</source></item>
</channel></rss>""".encode("utf-8")

YELLOW = {"total": 1, "_embedded": {"notices": [{
    "entity_id": "2026/00001", "forename": "MATEO", "name": "RIVAS OLMEDO",
    "date_of_birth": "1992/04/16", "nationalities": ["ES"],
    "_links": {"self": {"href": "https://ws-public.interpol.int/notices/v1/yellow/2026-00001"}}}]}}
VACIO = {"total": 0, "_embedded": {"notices": []}}


def handler(url: str, params=None, **kw):
    params = params or {}
    # --- XposedOrNot ---
    if "xposedornot.com/v1/check-email/" in url:
        email = url.rsplit("/", 1)[-1]
        names = BRECHAS_POR_EMAIL.get(email)
        if names:
            return FakeResponse(200, {"breaches": [names], "email": email, "status": "success"})
        return FakeResponse(200, {"Error": "Not found", "email": None})
    if "xposedornot.com/v1/breach-analytics" in url:
        email = params.get("email", "")
        names = BRECHAS_POR_EMAIL.get(email, [])
        det = [d for d in DETALLE_BRECHAS if d["breach"] in names]
        return FakeResponse(200, {"ExposedBreaches": {"breaches_details": det}})
    # --- Interpol ---
    if "ws-public.interpol.int/notices/v1/yellow" in url:
        return FakeResponse(200, YELLOW)
    if "ws-public.interpol.int/notices/v1/red" in url:
        return FakeResponse(200, VACIO)
    # --- Google News ---
    if "news.google.com/rss/search" in url:
        return FakeResponse(200, content=RSS)
    # --- Nominatim ---
    if "nominatim.openstreetmap.org/search" in url:
        return FakeResponse(200, [{"lat": "40.40660", "lon": "-3.68930",
                                   "display_name": "Estación de Atocha, Madrid, España"}])
    # --- Web del dominio ---
    if DOMINIO in url and url.startswith("http"):
        return FakeResponse(200, content=b"<html>Rivas Fotografia (ficticio)</html>", url=url,
                            headers={"Server": "nginx",
                                     "Strict-Transport-Security": "max-age=31536000",
                                     "X-Content-Type-Options": "nosniff"})
    # --- Redes sociales (módulo usernames) ---
    if any(p + USERNAME in url for p in PERFILES):
        return FakeResponse(200, content=b"<html>perfil</html>", url=url)
    return FakeResponse(404, content=b"not found", url=url)


class FakeSession:
    headers: dict = {}

    def get(self, url, params=None, **kw):
        return handler(url, params=params, **kw)


# ---------------------------------------------------------------------------
# 3) DNS y WHOIS simulados
# ---------------------------------------------------------------------------
class _RR:
    def __init__(self, t):
        self.t = t

    def to_text(self):
        return self.t


DNS = {
    "A": ["192.0.2.10"],
    "MX": [f"10 mx1.{DOMINIO}."],
    "NS": ["ns1.dns-ficticio.example.", "ns2.dns-ficticio.example."],
    "TXT": ['"v=spf1 include:_spf.example ~all"'],
    "SOA": [f"ns1.dns-ficticio.example. hostmaster.{DOMINIO}. 2026010101 7200 3600 1209600 3600"],
}


def fake_resolve(self, qname, rdtype="A", *a, **k):
    if rdtype in DNS:
        return [_RR(x) for x in DNS[rdtype]]
    raise Exception("NoAnswer")


def fake_whois(domain):
    return {"registrar": "Registrador Ficticio S.L.", "creation_date": "2019-03-11",
            "expiration_date": "2027-03-11", "org": "Rivas Fotografía (ficticio)",
            "country": "ES", "emails": [f"admin@{DOMINIO}"]}


# ---------------------------------------------------------------------------
# 4) Simuladores de theHarvester y holehe (salida con su formato real)
# ---------------------------------------------------------------------------
THEHARVESTER_SIM = f'''#!{sys.executable}
# Simulador de theHarvester para el ejemplo: escribe <fichero>.json como el real.
import json, sys
a = sys.argv[1:]
out = a[a.index("-f") + 1]
json.dump({{"emails": ["contacto@{DOMINIO}", "{EMAIL}"],
           "hosts": ["www.{DOMINIO}", "tienda.{DOMINIO}"],
           "ips": ["192.0.2.10"]}}, open(out + ".json", "w"))
print("[*] Searching ... (simulador de theHarvester)")
'''

HOLEHE_SIM = f'''#!{sys.executable}
# Simulador de holehe para el ejemplo: imprime la salida real de holehe.
print("*" * 30)
print("   " + __import__("sys").argv[1])
print("*" * 30)
print("[+] spotify.com")
print("[+] strava.com mat****@gmail.com")
print("[+] flickr.com")
print()
print("[+] Email used, [-] Email not used, [x] Rate limit")
print("121 websites checked in 8.4 seconds")
'''


def instalar_simuladores(tmpdir):
    for nombre, codigo in (("theHarvester", THEHARVESTER_SIM), ("holehe", HOLEHE_SIM)):
        p = os.path.join(tmpdir, nombre)
        with open(p, "w") as fh:
            fh.write(codigo)
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["PATH"] = tmpdir + os.pathsep + os.environ.get("PATH", "")


class _Tee(io.TextIOBase):
    """Escribe a la vez en la consola y en un buffer (para guardar la salida)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def main() -> int:
    crear_foto()

    import dns.resolver
    import whois
    import osint
    import osintlib.orchestrator as orq

    orq.build_session = lambda *a, **k: FakeSession()   # red simulada
    dns.resolver.Resolver.resolve = fake_resolve        # DNS simulado
    whois.whois = fake_whois                            # WHOIS simulado

    argv = [
        "--name", PERSONA, "--email", EMAIL, "--username", USERNAME,
        "--phone", TELEFONO, "--domain", DOMINIO, "--image", FOTO,
        "--last-seen", ULTIMA_VEZ, "--last-seen-date", "2026-10-18",
        "--age", "34", "--nationality", "ES", "--sex", "M",
        "--output-dir", OUT_DIR, "--outfile", "informe_ejemplo", "--pdf", "-y",
    ]

    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        instalar_simuladores(tmp)
        with contextlib.redirect_stderr(_Tee(sys.__stderr__, buf)):
            rc = osint.main(argv)

    cmd = "python3 osint.py " + " ".join(
        f'"{x}"' if (" " in x or "," in x) else x for x in argv)
    with open(os.path.join(OUT_DIR, "salida_cli.txt"), "w", encoding="utf-8") as fh:
        fh.write("$ " + cmd + "\n" + buf.getvalue())
    print(f"\nEjemplo generado en {OUT_DIR}/ (código de salida {rc})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
