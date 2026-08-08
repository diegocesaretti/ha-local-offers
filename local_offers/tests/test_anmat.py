from app.anmat import _choose_search_form, _form_payload, _parse_rows, _score


FORM_HTML = """
<html><body>
<form method="post" action="/HomeGu">
  <input type="hidden" name="__token" value="abc">
  <label for="Marca">Marca/Nombre de fantasía</label>
  <input id="Marca" name="Marca" type="text">
  <label for="Estado">Estado del Producto</label>
  <select id="Estado" name="Estado">
    <option value="">Todos</option>
    <option value="V">Vigente</option>
    <option value="B">Baja permanente</option>
  </select>
  <input type="submit" name="Buscar" value="Buscar">
</form>
</body></html>
"""


TABLE_HTML = """
<table>
<tr><th>Marca/Nombre de fantasía</th><th>Denominación</th><th>RNPA</th><th>Estado</th></tr>
<tr><td>La Serenísima</td><td>Leche entera UAT</td><td>04-12345</td><td>Vigente</td></tr>
<tr><td>La Serenísima</td><td>Postre chocolate</td><td>04-99999</td><td>Baja permanente</td></tr>
</table>
"""


def test_form_discovery_and_payload():
    form = _choose_search_form(FORM_HTML)
    assert form is not None
    payload, field = _form_payload(form, "La Serenísima")
    assert field == "Marca"
    assert payload["Marca"] == "La Serenísima"
    assert payload["Estado"] == "V"
    assert payload["__token"] == "abc"


def test_parse_only_vigente_rows():
    rows = _parse_rows(TABLE_HTML)
    assert len(rows) == 1
    assert "Leche entera" in rows[0]["_text"]
    assert "Vigente" in rows[0]["_text"]


def test_conservative_product_match():
    row = _parse_rows(TABLE_HTML)[0]
    good = {"brand": "La Serenisima", "name": "Leche entera", "variant": None, "presentation": "1 L"}
    wrong = {"brand": "La Serenisima", "name": "Galletitas chocolate", "variant": None, "presentation": "200 g"}
    assert _score(good, row) > 0.82
    assert _score(wrong, row) < 0.82
