from pipeline.models import Company
from pipeline.normalize import looks_like_company_name, parse_hn_title


class TestParseHnTitle:
    def test_extracts_name_and_batch(self):
        assert parse_hn_title(
            "Launch HN: RunAnywhere (YC W26) – Faster AI Inference"
        ) == ("RunAnywhere", "W26")

    def test_show_hn_without_batch(self):
        assert parse_hn_title("Show HN: Semble – Code search for agents") == ("Semble", None)

    def test_falls_back_to_whole_title(self):
        name, batch = parse_hn_title("Show HN: I built a voice agent from scratch")
        assert name.startswith("I built a voice agent")
        assert batch is None


class TestCompany:
    def _company(self, **kw) -> Company:
        return Company(source="yc", source_key="x", name="Acme", **kw)

    def test_unusable_without_name(self):
        assert not Company(source="yc", source_key="x", name="  ",
                           website="https://acme.dev").is_usable

    def test_usable_without_website(self):
        """Launch HN text posts have no URL and are still real companies."""
        assert self._company(website=None).is_usable

    def test_usable_with_website(self):
        assert self._company(website="https://acme.dev").is_usable
