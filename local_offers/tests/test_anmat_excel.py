from io import BytesIO

from openpyxl import Workbook

from app.anmat_excel import _score, export_candidates, parse_export


def _xlsx_bytes():
    wb = Workbook()
    ws = wb.active
    ws.append(["Listado Integrado ALG"])
    ws.append(["Marca/Nombre de Fantasía", "Denominación", "RNPA", "Estado del Producto"])
    ws.append(["La Serenísima", "Leche entera UAT", "04-12345", "Vigente"])
    ws.append(["La Serenísima", "Postre chocolate", "04-99999", "Baja permanente"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_complete_excel_and_state():
    rows, kind = parse_export(_xlsx_bytes())
    assert kind == "xlsx"
    assert len(rows) == 2
    good = {"brand": "La Serenisima", "name": "Leche entera", "variant": None}
    wrong = {"brand": "La Serenisima", "name": "Galletitas chocolate", "variant": None}
    assert _score(good, rows[0]) > 0.82
    assert _score(wrong, rows[0]) < 0.82
    assert _score(good, rows[1]) == 0.0  # baja permanente can never become green


def test_export_button_is_discovered_with_hidden_fields():
    html = """
    <form method="post" action="/HomeGu">
      <input type="hidden" name="__token" value="abc">
      <input name="Marca" value="">
      <button type="submit" name="accion" value="excel">Exportar a Excel</button>
    </form>
    """
    candidates = export_candidates(html, "https://listadoalg.anmat.gob.ar/Home")
    method, url, payload = candidates[0]
    assert method == "post"
    assert url == "https://listadoalg.anmat.gob.ar/HomeGu"
    assert payload["__token"] == "abc"
    assert payload["accion"] == "excel"
