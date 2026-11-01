"""Núcleo offline: detección de entrada, modelo de grafo, timeline, saneado, mapa."""

import osint
from osintlib.entity import Entity, Graph
from osintlib.mapexport import build_map_page, collect_points
from osintlib.timeline import build_timeline
from osintlib.utils import detect_input_type, domain_of_email, localpart_of_email


# ---------------- Detección del tipo de entrada ----------------
class TestDetectInput:
    def test_email(self):
        assert detect_input_type("juan@ejemplo.com") == "email"

    def test_domain(self):
        assert detect_input_type("ejemplo.com") == "domain"

    def test_phone(self):
        assert detect_input_type("+34 600 123 456") == "phone"

    def test_username(self):
        assert detect_input_type("juanp") == "username"

    def test_person(self):
        assert detect_input_type("Juan Perez") == "person"

    def test_email_no_es_dominio(self):
        # Un email contiene un dominio: debe ganar 'email'.
        assert detect_input_type("a@b.com") != "domain"

    def test_helpers(self):
        assert domain_of_email("a@b.com") == "b.com"
        assert localpart_of_email("a.b@c.com") == "a.b"
        assert domain_of_email("no-es-email") is None


# ---------------- Modelo de entidades / grafo ----------------
class TestGraph:
    def test_dedup_por_clave(self):
        g = Graph()
        a = g.add_entity(Entity("email", "X@Y.com", sources=["m1"]))
        b = g.add_entity(Entity("email", "x@y.com", sources=["m2"]))  # misma clave (normaliza)
        assert a is b
        assert set(b.sources) == {"m1", "m2"}
        assert len(g.entities_by_type("email")) == 1

    def test_id_estable(self):
        e1 = Entity("username", "pepe")
        e2 = Entity("username", "pepe")
        assert e1.id == e2.id

    def test_relaciones_idempotentes(self):
        g = Graph()
        p = g.add_entity(Entity("person", "Juan"))
        e = g.add_entity(Entity("email", "j@e.com"))
        g.add_relation(p, e, "tiene", source="t")
        g.add_relation(p, e, "tiene", source="t")
        assert len(g.relations) == 1

    def test_stats(self):
        g = Graph()
        g.add_entity(Entity("email", "a@b.com"))
        g.add_entity(Entity("username", "u"))
        s = g.stats()
        assert s["_entidades_total"] == 2
        assert s["email"] == 1

    def test_to_dict_serializable(self):
        g = Graph()
        p = g.add_entity(Entity("person", "Juan"))
        e = g.add_entity(Entity("email", "j@e.com"))
        g.add_relation(p, e, "tiene", source="t")
        d = g.to_dict()
        assert d["entities"] and d["relations"]
        assert "stats" in d


# ---------------- Línea de tiempo ----------------
class TestTimeline:
    def _graph(self):
        g = Graph()
        g.add_entity(Entity("image", "/f.jpg", attrs={"fecha_foto": "2026:10:20 18:30:45"}))
        g.add_entity(Entity("news", "http://n", attrs={"fecha": "Mon, 19 Oct 2026 08:00:00 GMT",
                                                       "titulo": "T", "medio": "M"}))
        g.add_entity(Entity("location", "41,2", attrs={"lat": 41, "lon": 2, "origen": "Última vez visto",
                                                       "lugar": "BCN", "fecha": "2026-10-18"}))
        return g

    def test_orden_cronologico(self):
        tl = build_timeline(self._graph())
        fechas = [e["fecha"] for e in tl]
        # 18 (ISO) < 19 (RFC822) < 20 (EXIF)
        assert fechas[0].startswith("2026-10-18")
        assert "19 Oct 2026" in fechas[1]
        assert fechas[2].startswith("2026:10:20")

    def test_incluye_relativo(self):
        tl = build_timeline(self._graph())
        assert all("rel" in e for e in tl)
        assert any("hace" in e["rel"] or e["rel"] in ("hoy", "ayer") for e in tl)


# ---------------- Saneado del nombre de reporte ----------------
class TestSanitize:
    def test_quita_ruta(self):
        assert osint.sanitize_basename("../../etc/passwd", "def") == "passwd"

    def test_quita_extension(self):
        assert osint.sanitize_basename("reporte.html", "def") == "reporte"

    def test_espacios_a_guion(self):
        assert osint.sanitize_basename("Informe Cliente A", "def") == "Informe_Cliente_A"

    def test_vacio_usa_fallback(self):
        assert osint.sanitize_basename("   ", "def_fecha") == "def_fecha"

    def test_caracteres_no_seguros(self):
        assert osint.sanitize_basename("caso#1 (urgente)!", "def") == "caso1_urgente"


# ---------------- Exportación de mapa ----------------
class TestMap:
    def test_collect_points(self):
        g = Graph()
        g.add_entity(Entity("location", "40,3", attrs={"lat": 40.1, "lon": -3.7, "origen": "x"}))
        g.add_entity(Entity("location", "sin-coords", attrs={"origen": "y"}))  # sin lat/lon
        pts = collect_points(g)
        assert len(pts) == 1
        assert pts[0]["lat"] == 40.1

    def test_map_page_tiene_respaldo(self):
        pts = [{"lat": 40.1, "lon": -3.7, "label": "L", "origen": "o", "fecha": ""}]
        html = build_map_page(pts)
        assert "leaflet" in html.lower()
        assert "OpenStreetMap" in html and "Google Maps" in html  # enlaces de respaldo


# ---------------- Variantes de nombre (convención española) ----------------
class TestNameVariants:
    def test_prioriza_primer_apellido(self):
        from osintlib.utils import name_variants
        v = name_variants("Mateo Rivas Olmedo")
        assert v[0] == "mateorivas"           # nombre + primer apellido, lo primero
        assert "mrivas" in v and "mrivaso" in v

    def test_sin_palabras_sueltas(self):
        from osintlib.utils import name_variants
        v = name_variants("Mateo Rivas Olmedo")
        assert "mateo" not in v and "rivas" not in v  # demasiado genéricos

    def test_tope(self):
        from osintlib.utils import name_variants
        assert len(name_variants("Ana Maria Lopez Ruiz", max_n=10)) <= 10

    def test_nombre_de_pila_en_emails(self):
        from osintlib.modules.permutations import email_patterns
        assert "mateo" in email_patterns("Mateo Rivas")  # mateo@dominio-propio es habitual


class TestFechasLegibles:
    def test_formatos(self):
        from osintlib.timeline import fmt_fecha
        assert fmt_fecha("Mon, 19 Oct 2026 09:15:00 GMT") == "19 oct 2026 · 09:15"
        assert fmt_fecha("2026:10:20 18:30:45") == "20 oct 2026 · 18:30"
        assert fmt_fecha("2026-10-18") == "18 oct 2026"
        assert fmt_fecha("texto raro") == "texto raro"   # si no se reconoce, se deja

    def test_foto_no_duplicada_en_timeline(self):
        g = Graph()
        g.add_entity(Entity("image", "/f.jpg", attrs={"fecha_foto": "2026:10:20 18:30:45",
                                                      "dispositivo": "Samsung"}))
        g.add_entity(Entity("location", "40.4,-3.6", attrs={"lat": 40.4, "lon": -3.6,
                                                           "origen": "EXIF de foto",
                                                           "fecha": "2026:10:20"}))
        tl = build_timeline(g)
        assert len(tl) == 1 and "40.4" in tl[0]["evento"]
