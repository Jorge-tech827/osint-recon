"""Tests de build_view (modelo de la vista) y de la generación del informe HTML."""

from osintlib.entity import Entity, Graph
from osintlib.orchestrator import Run
from osintlib.report import write_html
from osintlib.view import build_view, color_for


def _run_rico():
    """Un Run con datos variados para ejercitar la vista completa."""
    g = Graph()
    p = g.add_entity(Entity("person", "Mateo Rivas", sources=["input"]))
    # perfiles
    for red, u in [("GitHub", "mrivas"), ("Twitch", "mrivas")]:
        pr = g.add_entity(Entity("social_profile", f"https://{red}/{u}", label=red,
                                 sources=["usernames"], attrs={"red": red, "username": u,
                                 "url": f"https://{red}.com/{u}"}))
        g.add_relation(p, pr, "perfil_en", source="usernames")
    # email confirmado + brecha
    e1 = g.add_entity(Entity("email", "m@correo.es", sources=["input"]))
    b1 = g.add_entity(Entity("breach", "DemoLeak", sources=["breaches_free"],
                             attrs={"datos_expuestos": ["Emails", "IP"], "fecha": "2021"}))
    g.add_relation(e1, b1, "expuesto_en", source="breaches_free")
    # email candidato (permutación) + otra brecha
    e2 = g.add_entity(Entity("email", "mrivas@gmail.com", sources=["permutations"],
                             attrs={"origen": "permutación del nombre"}))
    b2 = g.add_entity(Entity("breach", "OtroLeak", sources=["permutations"],
                             attrs={"datos_expuestos": ["Emails"], "fecha": "2020"}))
    g.add_relation(p, e2, "email_posible", source="permutations")
    g.add_relation(e2, b2, "expuesto_en", source="permutations")
    # imagen + gps
    img = g.add_entity(Entity("image", "/f.jpg", sources=["exif"],
                              attrs={"fecha_foto": "2026:10:20 18:30", "dispositivo": "Samsung Galaxy S23"}))
    loc = g.add_entity(Entity("location", "40.4,-3.6", label="Foto EXIF", sources=["exif"],
                              attrs={"lat": 40.4, "lon": -3.6, "origen": "EXIF de foto", "fecha": "2026:10:20"}))
    g.add_relation(img, loc, "tomada_en", source="exif")
    # última vez visto
    g.add_entity(Entity("place", "Atocha, Madrid", sources=["input"]))
    g.add_entity(Entity("location", "40.4,-3.69", label="Última vez visto", sources=["geocode"],
                        attrs={"lat": 40.4, "lon": -3.69, "origen": "Última vez visto",
                               "lugar": "Atocha, Madrid", "fecha": "2026-10-18"}))
    # teléfono
    g.add_entity(Entity("phone", "+34600123456", label="+34 600 123 456", sources=["phone"],
                        attrs={"valido": True, "e164": "+34600123456", "pais": "España",
                               "operadora": "Vodafone", "tipo_linea": "móvil",
                               "zonas_horarias": ["Atlantic/Canary", "Europe/Madrid"]}))
    return Run(targets=[("person", "Mateo Rivas"), ("place", "Atocha, Madrid")], graph=g,
               results=[], started_at="", finished_at="",
               config={"settings": {"subject_age": "34", "subject_nationality": "ES",
                                     "last_seen_date": "2026-10-18"}})


class TestBuildView:
    def setup_method(self):
        self.v = build_view(_run_rico())

    def test_subject(self):
        assert self.v["subject"]["name"] == "Mateo Rivas"
        assert self.v["subject"]["age"] == "34"
        assert self.v["subject"]["last_seen"] == "Atocha, Madrid"

    def test_profiles_con_iniciales(self):
        assert self.v["profiles"] and all("ini" in p for p in self.v["profiles"])

    def test_brechas_agrupadas_por_email(self):
        grupos = {g["email"]: g for g in self.v["breaches_by_email"]}
        assert "m@correo.es" in grupos and "mrivas@gmail.com" in grupos
        assert grupos["mrivas@gmail.com"]["candidato"] is True
        assert grupos["m@correo.es"]["candidato"] is False
        # Cada brecha va con su email.
        assert grupos["m@correo.es"]["breaches"][0]["name"] == "DemoLeak"
        assert grupos["mrivas@gmail.com"]["breaches"][0]["name"] == "OtroLeak"

    def test_telefono_con_zona(self):
        assert self.v["phone"]["operadora"] == "Vodafone"
        assert "Europe/Madrid" in self.v["phone"]["zonas"]

    def test_exif_y_mapa(self):
        assert self.v["exif"]["gps"]
        assert len(self.v["map_points"]) == 2

    def test_leads_y_resumen(self):
        tipos = {l["type"] for l in self.v["leads"]}
        assert "location" in tipos and "exif" in tipos
        assert "encontrado" in self.v["summary_text"]

    def test_color_for(self):
        assert color_for("GitHub").startswith("#")


class TestWriteHtml:
    def test_genera_html_con_secciones(self, tmp_path):
        out = tmp_path / "informe.html"
        write_html(_run_rico(), str(out))
        h = out.read_text(encoding="utf-8")
        # Secciones clave del nuevo diseño.
        for marca in ["Resumen", "Pistas prioritarias", "Línea de tiempo", "Teléfono",
                      "Zona horaria", "Mateo Rivas", "m@correo.es", "mrivas@gmail.com",
                      "DemoLeak", "OtroLeak", "themebtn"]:
            assert marca in h, f"falta '{marca}' en el informe"

    def test_candidato_marcado(self, tmp_path):
        out = tmp_path / "informe.html"
        write_html(_run_rico(), str(out))
        assert "candidato" in out.read_text(encoding="utf-8").lower()
