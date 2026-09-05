from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")))
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


class FrontDoorLinkTests(unittest.TestCase):
    def test_all_local_markdown_links_resolve(self) -> None:
        for document in DOCUMENTS:
            text = document.read_text(encoding="utf-8")
            for raw in LINK.findall(text):
                target = raw.strip().split(maxsplit=1)[0].strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                resolved = (document.parent / unquote(parsed.path)).resolve()
                self.assertTrue(
                    resolved == ROOT or ROOT in resolved.parents,
                    f"{document.relative_to(ROOT)} link escapes repository: {raw}",
                )
                self.assertTrue(
                    resolved.exists(),
                    f"{document.relative_to(ROOT)} has a broken link: {raw}",
                )

    def test_scientific_routes_use_one_entry(self) -> None:
        index = (ROOT / "docs" / "PLAYGROUND_INDEX.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(index.count("(SCIENTIFIC_RUN_ENTRY.md)"), 8)
        self.assertFalse(list(ROOT.rglob("*HONESTY_PREFLIGHT*.md")))


if __name__ == "__main__":
    unittest.main()
