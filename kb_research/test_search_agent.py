import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from search_agent import ResearchTools, canonical_url, cited_fetched_urls


class FakeTavily:
    def search(self, **kwargs):
        return {"results": [{"title": "Official", "url": "https://example.gov/fact", "score": 0.9, "content": "fact"}]}


class ResearchToolsTests(unittest.TestCase):
    def make_tools(self, **kwargs):
        return ResearchTools(FakeTavily(), Path("/tmp/obscura"), **kwargs)

    def test_search_budget_is_enforced(self):
        tools = self.make_tools(max_searches=1)
        self.assertEqual(len(tools.search("first")["results"]), 1)
        self.assertIn("budget exhausted", tools.search("second")["error"])

    @patch("search_agent.subprocess.run")
    def test_fetch_cache_does_not_spend_budget(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout="# Complete page", stderr="")
        tools = self.make_tools(max_fetches=1)
        first = tools.fetch("https://Example.GOV/fact/")
        second = tools.fetch("https://example.gov/fact")
        self.assertEqual(first["content"], "# Complete page")
        self.assertTrue(second["cached"])
        self.assertEqual(tools.fetches_used, 1)
        run.assert_called_once()

    @patch("search_agent.subprocess.run")
    def test_total_page_text_is_capped_to_fit_the_context(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout="x" * 10000, stderr="")
        tools = self.make_tools(max_chars=8000, total_chars=12000)
        self.assertEqual(tools.fetch("https://a.gov/1")["content"].count("x"), 8000)
        self.assertLess(tools.fetch("https://a.gov/2")["content"].count("x"), 4000)     # what is left of the budget
        self.assertIn("budget exhausted", tools.fetch("https://a.gov/3")["error"])
        self.assertEqual(tools.fetches_used, 2)

    def test_only_fetched_urls_count_as_citations(self):
        fetched = {canonical_url("https://example.gov/fact")}
        answer = "Supported by [the agency](https://example.gov/fact). Not https://blog.example/x"
        self.assertEqual(cited_fetched_urls(answer, fetched), fetched)


if __name__ == "__main__":
    unittest.main()
