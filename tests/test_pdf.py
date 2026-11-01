"""Test del export a PDF. Se omite si no hay Chromium/Chrome en el sistema."""

import pytest

from osintlib.pdfexport import find_chrome, html_to_pdf

_HAS_CHROME = find_chrome() is not None


@pytest.mark.skipif(not _HAS_CHROME, reason="No hay Chromium/Chrome instalado")
def test_html_a_pdf(tmp_path):
    html = tmp_path / "x.html"
    html.write_text("<!doctype html><html><body><h1>Prueba PDF</h1></body></html>", encoding="utf-8")
    pdf = tmp_path / "x.pdf"
    ok, msg = html_to_pdf(str(html), str(pdf))
    assert ok, msg
    assert pdf.exists() and pdf.stat().st_size > 0
    assert pdf.read_bytes().startswith(b"%PDF")


def test_find_chrome_no_revienta():
    # Solo debe devolver una ruta o None, sin lanzar.
    r = find_chrome()
    assert r is None or isinstance(r, str)
