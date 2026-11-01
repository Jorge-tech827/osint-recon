"""Tests de la fase de correlación del orquestador (offline, sin módulos)."""

from osintlib.entity import Entity, Graph
from osintlib.orchestrator import Orchestrator


def _orq():
    # Sin módulos: solo probamos la lógica de correlación.
    return Orchestrator(config={"settings": {}}, enabled_modules=[])


class TestCorrelacion:
    def test_email_username_misma_persona(self):
        g = Graph()
        g.add_entity(Entity("email", "pepe@x.com"))
        g.add_entity(Entity("username", "pepe"))
        _orq()._correlate(g, [("email", "pepe@x.com"), ("username", "pepe")])
        labels = {r.label for r in g.relations}
        assert "misma_persona?" in labels

    def test_persona_enlaza_objetivos(self):
        g = Graph()
        g.add_entity(Entity("person", "Juan Perez"))
        g.add_entity(Entity("email", "j@x.com"))
        _orq()._correlate(g, [("person", "Juan Perez"), ("email", "j@x.com")])
        assert any(r.label == "investigacion" for r in g.relations)

    def test_telefono_brecha_posible_filtracion(self):
        g = Graph()
        p = g.add_entity(Entity("person", "Juan"))
        em = g.add_entity(Entity("email", "j@x.com"))
        ph = g.add_entity(Entity("phone", "+34600123456"))
        b1 = g.add_entity(Entity("breach", "ConTelefonos",
                                 attrs={"datos_expuestos": ["Emails", "Phone numbers"]}))
        b2 = g.add_entity(Entity("breach", "SoloEmails",
                                 attrs={"datos_expuestos": ["Emails"]}))
        g.add_relation(em, b1, "expuesto_en", source="x")
        g.add_relation(em, b2, "expuesto_en", source="x")
        _orq()._correlate_phone_breaches(g)
        # El teléfono se enlaza SOLO a la brecha que expuso teléfonos.
        destinos = [r.dst_id for r in g.relations
                    if r.src_id == ph.id and r.label == "posible_filtracion"]
        assert b1.id in destinos
        assert b2.id not in destinos

    def test_breach_expuso_telefonos_helper(self):
        f = Orchestrator._breach_expuso_telefonos
        assert f(Entity("breach", "x", attrs={"datos_expuestos": ["Teléfonos"]}))
        assert f(Entity("breach", "x", attrs={"datos_expuestos": ["Phone numbers"]}))
        assert not f(Entity("breach", "x", attrs={"datos_expuestos": ["Emails"]}))


class TestOrquestadorFiltro:
    def test_modulos_filtrados(self):
        o = Orchestrator(config={}, enabled_modules=["phone", "exif"])
        assert sorted(m.name for m in o.modules) == ["exif", "phone"]

    def test_run_clasifica_y_siembra(self):
        # Habilitamos solo 'phone' (offline y que NO acepta person/email), así el
        # run clasifica y siembra sin ejecutar módulos de red.
        o = Orchestrator(config={}, enabled_modules=["phone"])
        run = o.run(["Juan Perez", "j@x.com"])
        tipos = {t for t, _ in run.targets}
        assert "person" in tipos and "email" in tipos
        assert run.graph.get("person", "Juan Perez") is not None
        # phone no corre sobre person/email → sin resultados de red.
        assert run.results == []
