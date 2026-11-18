from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from ..http_helpers import redirect_next_or


class RedirectHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_redirect_next_or_prefers_safe_next(self):
        request = self.factory.post("/action/", {"next": reverse("events")})

        response = redirect_next_or(request, "main-page")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("events"))

    def test_redirect_next_or_uses_fallback_for_unsafe_next(self):
        request = self.factory.post("/action/", {"next": "https://evil.example/steal"})

        response = redirect_next_or(request, "main-page")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("main-page"))

    def test_redirect_next_or_emits_hx_redirect_for_htmx(self):
        request = self.factory.post(
            "/action/",
            {"next": reverse("events")},
            HTTP_HX_REQUEST="true",
        )

        response = redirect_next_or(request, "main-page")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("events"))
