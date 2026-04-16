"""Test wiki-to-wiki auto-linking (_auto_link_wiki_to_wiki)."""
from __future__ import annotations
from pathlib import Path
import tempfile
import pytest

from vaultsmith.kb import (
    _auto_link_wiki_to_wiki,
    _ensure_kb_dirs,
    _iter_md,
    WIKI_DIR,
)


class Test_auto_link_wiki_to_wiki:
    def test_creates_bidirectional_links(self, tmp_vault: Path) -> None:
        """Two wiki pages with shared terms should link to each other bidirectionally."""
        wiki_dir = tmp_vault / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)

        page_a = wiki_dir / "Artificial Intelligence.md"
        page_a.write_text(
            "# Artificial Intelligence\n\n"
            "AI is transforming technology. Machine learning is a key subset of AI.\n",
            encoding="utf-8",
        )

        page_b = wiki_dir / "Machine Learning.md"
        page_b.write_text(
            "# Machine Learning\n\n"
            "ML is a subset of AI that enables systems to learn from data.\n",
            encoding="utf-8",
        )

        result = _auto_link_wiki_to_wiki(tmp_vault, max_pairs=50, min_shared_terms=2)

        assert result >= 1, f"Expected at least 1 link pair, got {result}"

        text_a = page_a.read_text(encoding="utf-8")
        text_b = page_b.read_text(encoding="utf-8")

        # A should link to B
        assert "Machine Learning" in text_a, f"page_a should link to page_b: {text_a}"
        # B should link to A (bidirectional)
        assert "Artificial Intelligence" in text_b, f"page_b should link to page_a: {text_b}"

    def test_respects_max_pairs(self, tmp_vault: Path) -> None:
        """Should not create more links than max_pairs."""
        wiki_dir = tmp_vault / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)

        for i in range(10):
            p = wiki_dir / f"Topic {i}.md"
            p.write_text(
                f"# Topic {i}\n\nCommon shared content about technology and science and systems.\n",
                encoding="utf-8",
            )

        result = _auto_link_wiki_to_wiki(tmp_vault, max_pairs=5, min_shared_terms=2)

        assert result <= 5, f"Result {result} exceeds max_pairs=5"

    def test_skips_already_linked_pages(self, tmp_vault: Path) -> None:
        """Should not create duplicate links when A already links to B."""
        wiki_dir = tmp_vault / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)

        # page_a already links to page_b via "Auto Links" section
        page_a = wiki_dir / "Alpha.md"
        page_a.write_text(
            "# Alpha\n\nBeta is a related concept.\n"
            "## Auto Links\n"
            "- [[Beta]]\n",
            encoding="utf-8",
        )

        page_b = wiki_dir / "Beta.md"
        page_b.write_text("# Beta\n\nAlpha is a related concept.\n", encoding="utf-8")

        result = _auto_link_wiki_to_wiki(tmp_vault, max_pairs=50, min_shared_terms=1)

        # page_b should NOT have a duplicate link to page_a added
        # (page_a already had the forward link; page_b already has the backward link)
        text_b = page_b.read_text(encoding="utf-8")
        # Should not have 2 "Alpha" references (one in body, one in link)
        assert text_b.count("Alpha") == 1, (
            f"page_b should not have duplicate link to page_a: {text_b}"
        )

    def test_no_wiki_pages_returns_zero(self, tmp_vault: Path) -> None:
        """Should return 0 when no wiki pages exist."""
        _ensure_kb_dirs(tmp_vault)
        result = _auto_link_wiki_to_wiki(tmp_vault)
        assert result == 0

    def test_single_wiki_page_returns_zero(self, tmp_vault: Path) -> None:
        """Should return 0 when only one wiki page exists."""
        wiki_dir = tmp_vault / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)

        page_a = wiki_dir / "Only One.md"
        page_a.write_text("# Only One\n\nContent.\n", encoding="utf-8")

        result = _auto_link_wiki_to_wiki(tmp_vault)
        assert result == 0

    def test_insufficient_shared_terms_returns_zero(self, tmp_vault: Path) -> None:
        """Should return 0 when min_shared_terms is too high."""
        wiki_dir = tmp_vault / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)

        page_a = wiki_dir / "Foo.md"
        page_a.write_text("# Foo\n\nUnique word alpha.\n", encoding="utf-8")

        page_b = wiki_dir / "Bar.md"
        page_b.write_text("# Bar\n\nUnique word beta.\n", encoding="utf-8")

        result = _auto_link_wiki_to_wiki(tmp_vault, min_shared_terms=5)
        assert result == 0

    def test_does_not_create_self_links(self, tmp_vault: Path) -> None:
        """A page should never link to itself."""
        wiki_dir = tmp_vault / WIKI_DIR
        wiki_dir.mkdir(parents=True, exist_ok=True)

        page_a = wiki_dir / "Test.md"
        page_a.write_text(
            "# Test\n\nThis page has Test and also itself as a concept.\n",
            encoding="utf-8",
        )

        page_b = wiki_dir / "Example.md"
        page_b.write_text("# Example\n\nAnother page with Test content.\n", encoding="utf-8")

        result = _auto_link_wiki_to_wiki(tmp_vault, max_pairs=50, min_shared_terms=1)

        text_a = page_a.read_text(encoding="utf-8")
        # page_a should NOT link to itself
        lines_a = text_a.splitlines()
        auto_link_lines = [
            ln for ln in lines_a if ln.strip().startswith("- [[")
        ]
        self_links = [ln for ln in auto_link_lines if "Test" in ln and "Example" not in ln]
        assert len(self_links) == 0, f"page_a should not self-link: {text_a}"


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a minimal vault structure for testing."""
    _ensure_kb_dirs(tmp_path)
    return tmp_path
