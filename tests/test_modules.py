"""Tests de los módulos (offline, con respuestas simuladas donde hay red)."""

import piexif
import pytest
from PIL import Image

from conftest import FakeResponse, FakeSession
from osintlib.entity import Entity, Graph
from osintlib.modules import discover_modules
from osintlib.modules.breaches_free import BreachesFreeModule, fetch_breaches
from osintlib.modules.interpol import InterpolModule, _split_name
from osintlib.modules.missing_db import MissingDBModule
from osintlib.modules.news import NewsModule
from osintlib.modules.permutations import PermutationsModule, email_patterns
from osintlib.modules.phone import PhoneModule
from osintlib.modules.reverse_image import ReverseImageModule
from osintlib.modules.usernames import SITES, UsernamesModule


def test_descubrimiento_modulos():
    nombres = {c().name for c in discover_modules()}
    # Deben estar los módulos clave.
    for n in ("usernames", "phone", "exif", "interpol", "news", "breaches_free",
              "permutations", "reverse_image", "missing_db", "geocode"):
        assert n in nombres


# ---------------- Usernames ----------------
class TestUsernames:
    def test_patrones_desde_nombre(self):
        cand = UsernamesModule()._candidate_usernames("person", "Juan Perez")
        assert "juanperez" in cand and "juan.perez" in cand and "jperez" in cand

    def test_normaliza_acentos(self):
        cand = UsernamesModule()._candidate_usernames("person", "Mateo Rívas")
        assert all("í" not in c for c in cand)

    def test_desde_email(self):
        assert UsernamesModule()._candidate_usernames("email", "pepe@x.com") == ["pepe"]

    def test_cobertura_sitios(self):
        assert len(SITES) >= 30


# ---------------- Permutación de emails ----------------
class TestPermutations:
    def test_patrones_email(self):
        pats = email_patterns("Mateo Rivas")
        assert "mateo.rivas" in pats and "mrivas" in pats

    def test_sin_dominio_ni_comunes_skip(self, ctx_factory=None):
        from osintlib.modules.base import Context
        from osintlib.utils import get_logger
        ctx = Context(config={"settings": {"permute_common": "off"}},
                      session=FakeSession(), logger=get_logger("t"))
        res = PermutationsModule().run("person", "Juan Perez", Graph(), ctx)
        assert res.status == "skipped"

    def test_hit_anade_email_y_brecha(self):
        from osintlib.modules.base import Context
        from osintlib.utils import get_logger
        state = {"n": 0}

        def handler(url, **kw):
            if "check-email" in url:
                state["n"] += 1
                if state["n"] == 1:  # primer email: con brecha
                    return FakeResponse(200, {"breaches": [["DemoLeak"]]})
                return FakeResponse(200, {"Error": "Not found"})
            return FakeResponse(200, {"ExposedBreaches": {"breaches_details":
                [{"breach": "DemoLeak", "xposed_date": "2021", "verified": True, "xposed_data": ["Emails"]}]}})

        g = Graph()
        g.add_entity(Entity("domain", "ejemplo.es", sources=["x"]))
        ctx = Context(config={"settings": {"permute_common": "off", "permute_max": "7"}},
                      session=FakeSession(handler), logger=get_logger("t"))
        res = PermutationsModule().run("person", "Mateo Rivas", g, ctx)
        assert res.status == "ok"
        emails = [e.value for e in g.entities_by_type("email")]
        assert len(emails) == 1  # solo el que tuvo brecha
        assert g.entities_by_type("breach")

    def test_red_caida_da_error(self):
        from osintlib.modules.base import Context
        from osintlib.utils import get_logger

        def handler(url, **kw):
            raise ConnectionError("sin red")

        g = Graph()
        g.add_entity(Entity("domain", "ejemplo.es", sources=["x"]))
        ctx = Context(config={"settings": {"permute_common": "off"}},
                      session=FakeSession(handler), logger=get_logger("t"))
        res = PermutationsModule().execute("person", "Mateo Rivas", g, ctx)
        assert res.status == "error"


# ---------------- Teléfono (phonenumbers, offline) ----------------
class TestPhone:
    def test_numero_valido_es(self, ctx_factory):
        g = Graph()
        res = PhoneModule().run("phone", "+34 600 123 456", g, ctx_factory())
        assert res.status == "ok"
        ph = g.entities_by_type("phone")[0]
        assert ph.attrs["valido"] is True
        assert ph.attrs["pais"] == "España"
        assert ph.attrs["tipo_linea"] == "móvil"
        assert "Europe/Madrid" in ph.attrs["zonas_horarias"]
        assert ph.attrs["e164"] == "+34600123456"

    def test_no_duplica_nodo(self, ctx_factory):
        g = Graph()
        g.add_entity(Entity("phone", "+34 600 123 456", sources=["input"]))  # sembrado
        PhoneModule().run("phone", "+34 600 123 456", g, ctx_factory())
        assert len(g.entities_by_type("phone")) == 1

    def test_numero_invalido(self, ctx_factory):
        g = Graph()
        res = PhoneModule().run("phone", "123", g, ctx_factory(settings={"phone_region": "ES"}))
        assert res.status in ("ok", "error")  # no revienta


# ---------------- EXIF (imagen real generada) ----------------
class TestExif:
    def _foto_con_gps(self, path, lat=40.4168, lon=-3.7038):
        def dms(dd):
            d = int(abs(dd))
            m = int((abs(dd) - d) * 60)
            s = round((((abs(dd) - d) * 60) - m) * 6000)
            return ((d, 1), (m, 1), (s, 100))
        gps = {piexif.GPSIFD.GPSLatitudeRef: "N", piexif.GPSIFD.GPSLatitude: dms(lat),
               piexif.GPSIFD.GPSLongitudeRef: "W", piexif.GPSIFD.GPSLongitude: dms(lon)}
        exif = {piexif.ExifIFD.DateTimeOriginal: b"2026:10:20 18:30:45"}
        zeroth = {piexif.ImageIFD.Make: b"Samsung", piexif.ImageIFD.Model: b"Galaxy S23"}
        Image.new("RGB", (32, 32), (120, 120, 120)).save(
            path, exif=piexif.dump({"0th": zeroth, "Exif": exif, "GPS": gps}))

    def test_extrae_gps(self, tmp_path, ctx_factory):
        f = tmp_path / "foto.jpg"
        self._foto_con_gps(str(f))
        g = Graph()
        res = ReverseImageAvoid = None
        from osintlib.modules.exif import ExifModule
        res = ExifModule().run("image", str(f), g, ctx_factory())
        assert res.status == "ok"
        locs = g.entities_by_type("location")
        assert locs and abs(locs[0].attrs["lat"] - 40.4168) < 0.01
        img = g.entities_by_type("image")[0]
        assert "Samsung" in img.attrs["dispositivo"]


# ---------------- Búsqueda inversa ----------------
class TestReverseImage:
    def test_url_genera_enlaces(self, ctx_factory):
        g = Graph()
        res = ReverseImageModule().run("image", "https://x.com/f.jpg", g, ctx_factory())
        assert res.status == "ok"
        motores = {f["motor"] for f in res.findings}
        assert {"Google Lens", "Yandex", "TinEye", "Bing"} <= motores

    def test_fichero_inexistente_error(self, ctx_factory):
        res = ReverseImageModule().run("image", "/no/existe.jpg", Graph(), ctx_factory())
        assert res.status == "error"


# ---------------- Bases de desaparecidos ----------------
class TestMissingDB:
    def test_genera_enlaces(self, ctx_factory):
        res = MissingDBModule().run("person", "Juan Perez", Graph(), ctx_factory())
        bases = {f["base"] for f in res.findings}
        assert any("SOS" in b for b in bases)
        assert any("NamUs" in b for b in bases)


# ---------------- Interpol (respuesta simulada) ----------------
class TestInterpol:
    def test_split_name(self):
        fore, apellidos = _split_name("Juan Perez Garcia")
        assert fore == "Juan" and "Garcia" in apellidos

    def test_parseo_red_notice(self, ctx_factory):
        red = {"total": 1, "_embedded": {"notices": [
            {"entity_id": "2019/1", "forename": "JOHN", "name": "SMITH",
             "date_of_birth": "1975", "nationalities": ["US"],
             "_links": {"self": {"href": "http://x"}}}]}}

        def handler(url, **kw):
            return FakeResponse(200, red if "red" in url else {"total": 0, "_embedded": {"notices": []}})

        g = Graph()
        res = InterpolModule().run("person", "John Smith", g, ctx_factory(session=FakeSession(handler)))
        assert res.status == "ok"
        notices = g.entities_by_type("notice")
        assert notices and notices[0].confidence <= 0.4  # baja por ser coincidencia de nombre

    def test_filtro_edad_nacionalidad(self, ctx_factory):
        captured = {}

        def handler(url, params=None, **kw):
            captured.update(params or {})
            return FakeResponse(200, {"total": 0, "_embedded": {"notices": []}})

        ctx = ctx_factory(session=FakeSession(handler),
                          settings={"subject_age": "34", "subject_nationality": "es", "subject_sex": "M"})
        InterpolModule().run("person", "Juan Perez", Graph(), ctx)
        assert captured.get("ageMin") == 34 and captured.get("nationality") == "ES"


# ---------------- Noticias (RSS simulado) ----------------
class TestNews:
    def test_parseo_rss(self, ctx_factory):
        rss = b"""<?xml version="1.0"?><rss><channel>
        <item><title>Buscan a X</title><link>http://n1</link>
        <pubDate>Mon, 19 Oct 2026 08:00:00 GMT</pubDate><source url="http://ep">El Pais</source></item>
        </channel></rss>"""

        def handler(url, **kw):
            return FakeResponse(200, content=rss)

        g = Graph()
        res = NewsModule().run("person", "Juan", g, ctx_factory(session=FakeSession(handler)))
        assert res.status == "ok"
        news = g.entities_by_type("news")
        assert news and news[0].attrs["medio"] == "El Pais"


# ---------------- Brechas gratis (XposedOrNot simulado) ----------------
class TestBreachesFree:
    def _handler(self, con_brecha=True):
        def handler(url, **kw):
            if "check-email" in url:
                if con_brecha:
                    return FakeResponse(200, {"breaches": [["DemoLeak"]]})
                return FakeResponse(200, {"Error": "Not found"})
            return FakeResponse(200, {"ExposedBreaches": {"breaches_details":
                [{"breach": "DemoLeak", "xposed_date": "2021", "verified": True, "xposed_data": ["Emails"]}]}})
        return handler

    def test_fetch_con_brecha(self):
        info = fetch_breaches("x@y.com", FakeSession(self._handler(True)))
        assert info["status"] == "ok" and "DemoLeak" in info["names"]

    def test_fetch_sin_brecha(self):
        info = fetch_breaches("x@y.com", FakeSession(self._handler(False)))
        assert info["status"] == "none"

    def test_ratelimit(self):
        info = fetch_breaches("x@y.com", FakeSession(lambda url, **k: FakeResponse(429)))
        assert info["status"] == "ratelimited"

    def test_modulo_crea_entidades(self, ctx_factory):
        g = Graph()
        res = BreachesFreeModule().run("email", "x@y.com", g,
                                       ctx_factory(session=FakeSession(self._handler(True))))
        assert res.status == "ok" and g.entities_by_type("breach")


# ---------------- Integración externa: parseo de holehe ----------------
class TestHolehe:
    # Fragmento de salida REAL de holehe (con --no-color --no-clear).
    SALIDA_REAL = (
        "********************\n"
        "   test@example.com\n"
        "********************\n"
        "[+] twitter.com\n"
        "[+] spotify.com ex****@gmail.com / +34 6** *** *12\n"
        "\n"
        "[+] Email used, [-] Email not used, [x] Rate limit\n"
        "121 websites checked in 3.2 seconds\n"
    )

    def test_ignora_leyenda(self):
        from osintlib.modules.external_tools import parse_holehe_output
        servicios = [s["servicio"] for s in parse_holehe_output(self.SALIDA_REAL)]
        assert servicios == ["twitter.com", "spotify.com"]

    def test_pista_recuperacion(self):
        from osintlib.modules.external_tools import parse_holehe_output
        res = parse_holehe_output(self.SALIDA_REAL)
        assert "ex****@gmail.com" in res[1]["extra"]

    def test_quita_colores_ansi(self):
        from osintlib.modules.external_tools import parse_holehe_output
        coloreado = "\x1b[32m[+] github.com\x1b[0m\n"
        assert parse_holehe_output(coloreado)[0]["servicio"] == "github.com"


class TestNormalizacionBrechas:
    def test_as_list_texto_y_lista(self):
        from osintlib.modules.breaches_free import as_list
        assert as_list("Email addresses;Passwords") == ["Email addresses", "Passwords"]
        assert as_list(["Emails", "IP"]) == ["Emails", "IP"]
        assert as_list(None) == []

    def test_as_bool_no_es_verdadero(self):
        from osintlib.modules.breaches_free import as_bool
        assert as_bool("Yes") and as_bool(True)
        assert not as_bool("No") and not as_bool(None)


class TestPermutacionesNoReetiqueta:
    def test_email_introducido_no_es_candidato(self):
        from osintlib.modules.base import Context
        from osintlib.utils import get_logger

        probados = []

        def handler(url, **kw):
            if "check-email" in url:
                probados.append(url.rsplit("/", 1)[-1])
                return FakeResponse(200, {"Error": "Not found"})
            return FakeResponse(200, {})

        g = Graph()
        g.add_entity(Entity("domain", "ejemplo.es", sources=["input"]))
        g.add_entity(Entity("email", "mateo.rivas@ejemplo.es", sources=["input"]))
        ctx = Context(config={"settings": {}}, session=FakeSession(handler), logger=get_logger("t"))
        PermutationsModule().run("person", "Mateo Rivas", g, ctx)
        assert "mateo.rivas@ejemplo.es" not in probados          # no se vuelve a consultar
        em = g.get("email", "mateo.rivas@ejemplo.es")
        assert em.attrs.get("origen") != "permutación del nombre"  # sigue siendo dato del usuario
