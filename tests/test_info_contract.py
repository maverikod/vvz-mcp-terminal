"""Host-safe contract tests for the paginated info command guide."""

from __future__ import annotations

import unittest

from mcp_terminal.commands.info_resources import (
    DEFAULT_INFO_PAGE_SIZE,
    MAX_INFO_PAGE_SIZE,
    TERMINAL_INFO_GUIDE_VERSION,
    TERMINAL_INFO_MARKDOWN,
    paginate_terminal_info,
)


class InfoContractTests(unittest.TestCase):
    def test_paginated_guide_exposes_cli_section(self) -> None:
        page = paginate_terminal_info(page=1, page_size=MAX_INFO_PAGE_SIZE)
        self.assertEqual(TERMINAL_INFO_GUIDE_VERSION, "1.2")
        self.assertIn("Developer CLI", TERMINAL_INFO_MARKDOWN)
        self.assertIn("pipeline --list", TERMINAL_INFO_MARKDOWN)
        self.assertIn("termgr status", TERMINAL_INFO_MARKDOWN)
        self.assertIn("CLI and automation expectations", TERMINAL_INFO_MARKDOWN)
        self.assertGreaterEqual(page.total_pages, 1)

    def test_paginate_terminal_info_returns_navigation_metadata(self) -> None:
        page = paginate_terminal_info(page=2, page_size=2)
        self.assertEqual(page.page, 2)
        self.assertEqual(page.page_size, 2)
        self.assertEqual(len(page.sections), 2)
        self.assertTrue(page.has_prev)
        self.assertGreaterEqual(page.total_pages, 2)

    def test_paginate_terminal_info_rejects_invalid_requests(self) -> None:
        with self.assertRaises(ValueError):
            paginate_terminal_info(page=0, page_size=DEFAULT_INFO_PAGE_SIZE)
        with self.assertRaises(ValueError):
            paginate_terminal_info(page=1, page_size=MAX_INFO_PAGE_SIZE + 1)


if __name__ == "__main__":
    unittest.main()
