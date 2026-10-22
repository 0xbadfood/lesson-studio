import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import json

from search_agent import HarnessError, ResearchTools, canonical_url, cited_fetched_urls, complete_fitting


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



class OverflowTests(unittest.TestCase):
    def test_an_overflowing_conversation_is_shortened_and_asked_again(self):
        page = {"url": "https://example.org/a", "content": "x" * 60000}
        messages = [{"role": "user", "content": "q"},
                    {"role": "tool", "name": "fetch_url", "content": json.dumps(page)}]

        class Qwen:
            max_tokens = 4096
            calls = 0

            def complete(self, messages, **kwargs):
                self.calls += 1
                size = sum(len(m["content"]) for m in messages) // 2      # 2 characters a token
                if size + self.max_tokens > 32768:
                    raise HarnessError(f"Qwen request failed: 400; response: This model's maximum context length is "
                                       f"32768 tokens. However, you requested {size + self.max_tokens} tokens")
                return {"content": "answer"}

        qwen = Qwen()
        self.assertEqual(complete_fitting(qwen, messages), {"content": "answer"})
        self.assertEqual(qwen.calls, 2)
        self.assertIn("page shortened", json.loads(messages[1]["content"])["content"])


if __name__ == "__main__":
    unittest.main()
