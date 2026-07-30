import unittest

from core.redirect_resolver import resolve_redirect_chain
from workflows.auxiliary_link_analysis import _resolve_intermediate_agendas


class RedirectResolverTests(unittest.TestCase):
    def test_resolves_allowed_redirect_without_reading_html(self):
        responses = {
            "https://example.test/start": _Response(
                302,
                {"Location": "/final?agenda=A&recurso=B"},
            ),
            "https://example.test/final?agenda=A&recurso=B": _Response(
                200,
                {},
            ),
        }

        result = resolve_redirect_chain(
            "https://example.test/start",
            {"example.test"},
            request_get=lambda url, **kwargs: responses[url],
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["redirect_count"], 1)
        self.assertEqual(
            result["final_url"],
            "https://example.test/final?agenda=A&recurso=B",
        )

    def test_blocks_redirect_to_external_domain(self):
        responses = {
            "https://example.test/start": _Response(
                302,
                {"Location": "https://external.test/final"},
            )
        }

        result = resolve_redirect_chain(
            "https://example.test/start",
            {"example.test"},
            request_get=lambda url, **kwargs: responses[url],
        )

        self.assertEqual(result["status"], "blocked_domain")

    def test_detects_redirect_cycle(self):
        responses = {
            "https://example.test/a": _Response(302, {"Location": "/b"}),
            "https://example.test/b": _Response(302, {"Location": "/a"}),
        }

        result = resolve_redirect_chain(
            "https://example.test/a",
            {"example.test"},
            request_get=lambda url, **kwargs: responses[url],
        )

        self.assertEqual(result["status"], "cycle_detected")

    def test_intermediate_agenda_uses_resolved_identity(self):
        appearance = {
            "appearance_id": "link_1::resource_1",
            "detected_url": "https://example.test/intermediate",
            "functional_kind": "agenda",
            "identity_key": "//example.test/intermediate",
            "identity_parameters": {},
        }

        def resolver(url, **kwargs):
            return {
                "status": "resolved",
                "original_url": url,
                "final_url": (
                    "https://www.montevideo.gub.uy/sae/"
                    "agendarReserva/Paso1.xhtml?agenda=A&recurso=B"
                ),
                "redirect_count": 1,
                "chain": [url, "final"],
                "error": None,
            }

        _resolve_intermediate_agendas([appearance], resolver=resolver)

        self.assertEqual(
            appearance["identity_parameters"],
            {"agenda": "A", "recurso": "B"},
        )
        self.assertIn("agenda=A", appearance["identity_key"])


class _Response:
    def __init__(self, status_code, headers):
        self.status_code = status_code
        self.headers = headers

    def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
