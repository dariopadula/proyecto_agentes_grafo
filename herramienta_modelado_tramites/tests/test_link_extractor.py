import unittest

from core.link_extractor import extract_candidate_links
from core.link_extractor import extract_pagination_urls


class LinkExtractorTests(unittest.TestCase):
    def test_official_result_list_does_not_filter_by_url_category(self):
        html = """
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="/tramites-y-tributos/solicitud/conexion">Conexión</a>
        </div></div>
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="/tramites-y-tributos/consulta/reglamentacion">Consulta</a>
        </div></div>
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="/tramites-y-tributos/denuncia/hundimiento">Denuncia</a>
        </div></div>
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="/tramite/estructura-alternativa">Otra estructura</a>
        </div></div>
        """

        links = extract_candidate_links(
            html,
            "https://tramites.montevideo.gub.uy/buscador_tramites/Saneamiento",
        )

        self.assertEqual(len(links), 4)
        self.assertEqual(
            [item["url_category"] for item in links],
            ["solicitud", "consulta", "denuncia", ""],
        )

    def test_result_list_still_rejects_external_and_duplicate_urls(self):
        html = """
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="/tramites-y-tributos/reclamo/tarifa">Reclamo</a>
        </div></div>
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="/tramites-y-tributos/reclamo/tarifa#detalle">Repetido</a>
        </div></div>
        <div class="listado-tramites views-row"><div class="views-field-title">
          <a href="https://example.test/no-oficial">Externo</a>
        </div></div>
        """

        links = extract_candidate_links(
            html,
            "https://tramites.montevideo.gub.uy/buscador_tramites/Saneamiento",
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["url_category"], "reclamo")

    def test_pagination_accepts_only_numeric_pages_of_same_search(self):
        html = """
        <a href="?page=2">3</a><a href="?page=1">2</a><a href="?page=0">1</a>
        <a href="?page=1">Repetida</a><a href="?page=siguiente">Inválida</a>
        <a href="/buscador_tramites/Otro?page=3">Otra búsqueda</a>
        <a href="https://example.test/buscador_tramites/Saneamiento?page=4">Externa</a>
        """
        urls = extract_pagination_urls(
            html,
            "https://tramites.montevideo.gub.uy/buscador_tramites/Saneamiento",
            "https://tramites.montevideo.gub.uy/buscador_tramites/Saneamiento",
        )
        self.assertEqual(
            urls,
            [
                "https://tramites.montevideo.gub.uy/buscador_tramites/Saneamiento?page=1",
                "https://tramites.montevideo.gub.uy/buscador_tramites/Saneamiento?page=2",
            ],
        )


if __name__ == "__main__":
    unittest.main()
