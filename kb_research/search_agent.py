#!/usr/bin/env python3
"""A small tool-calling web research harness for an OpenAI-compatible Qwen server.

Local copy of ~/kbagent/search_agent.py for the textbook knowledge-base experiment (textbook_kb.py). Changes from
the original: fetched pages are capped (`max_chars`) so a few long pages cannot overflow the model's context, the
system prompt can be replaced, and `research()` returns the answer with the pages actually fetched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from tavily import TavilyClient


SYSTEM_PROMPT = """You are a careful internet research agent. Answer the user's question accurately from authoritative web sources.

You have two tools:
- web_search: broad discovery through Tavily. Use short, varied search queries.
- fetch_url: retrieve the complete rendered Markdown of a promising page through Obscura.

Research rules:
1. Search broadly before answering. Prefer primary sources: government and institutional sites, official documentation, standards bodies, original research, and direct company statements. Treat blogs, aggregators, and search snippets only as leads.
2. Fetch and read the pages you rely on. Do not cite a search snippet as evidence.
3. Cross-check important or disputed claims when possible. If reliable sources disagree, say so.
4. Answer the exact question. Separate established facts from inference and state material uncertainty.
5. Cite claims inline with Markdown links to the fetched source pages, for example [WHO](https://www.who.int/...). Finish with a short `Sources` list of the most important fetched pages. Never invent a URL or cite a URL you did not fetch.
6. You have at most 5 searches and 50 URL fetches. Stop early once the evidence is sufficient.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Broadly search the public web. Returns titles, URLs, relevance scores, and short discovery snippets; fetch a result before citing it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A concise web search query, no more than 400 characters.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch all readable content from one HTTP(S) URL as rendered Markdown. Use this on sources before relying on or citing them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The complete HTTP(S) URL to fetch."}
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
]


class HarnessError(RuntimeError):
    pass


def canonical_url(url: str) -> str:
    """Normalize enough for citation validation without changing URL semantics."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


@dataclass
class ResearchTools:
    tavily: Any
    obscura_path: Path
    max_searches: int = 5
    max_fetches: int = 50
    search_results: int = 10
    fetch_timeout: int = 60
    max_chars: int = 16000
    total_chars: int | None = None      # all fetched pages together, so the conversation fits the model's context
    chars_used: int = 0
    searches_used: int = 0
    fetches_used: int = 0
    fetched_urls: set[str] = field(default_factory=set)
    fetch_cache: dict[str, str] = field(default_factory=dict)

    def search(self, query: str) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {"error": "query must not be empty"}
        if len(query) > 400:
            return {"error": "query exceeds Tavily's 400-character limit"}
        if self.searches_used >= self.max_searches:
            return {"error": f"search budget exhausted ({self.max_searches}/{self.max_searches})"}

        self.searches_used += 1
        try:
            response = self.tavily.search(
                query=query,
                search_depth="advanced",
                max_results=self.search_results,
                include_answer=False,
                include_raw_content=False,
            )
        except Exception as exc:  # SDK exception types have changed between releases.
            return {"error": f"Tavily search failed: {exc}"}

        results = []
        for item in response.get("results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "score": item.get("score"),
                    "snippet": item.get("content", ""),
                }
            )
        return {
            "query": query,
            "results": results,
            "budget": {"searches_used": self.searches_used, "searches_left": self.max_searches - self.searches_used},
        }

    def fetch(self, url: str) -> dict[str, Any]:
        url = url.strip()
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return {"error": "fetch_url accepts only absolute HTTP(S) URLs"}

        normalized = canonical_url(url)
        if normalized in self.fetch_cache:
            return {"url": url, "content": self.fetch_cache[normalized], "cached": True}
        if self.fetches_used >= self.max_fetches:
            return {"error": f"fetch budget exhausted ({self.max_fetches}/{self.max_fetches})"}

        room = self.max_chars if self.total_chars is None else min(self.max_chars, self.total_chars - self.chars_used)
        if room < 2000:
            return {"error": "page text budget exhausted: answer from the pages already fetched"}
        self.fetches_used += 1
        try:
            completed = subprocess.run(
                [str(self.obscura_path), "fetch", "--dump", "markdown", "--timeout", str(self.fetch_timeout), url],
                text=True,
                capture_output=True,
                timeout=self.fetch_timeout + 10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"error": f"Obscura fetch failed: {exc}"}

        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit status {completed.returncode}"
            return {"error": f"Obscura fetch failed: {detail}"}

        content = completed.stdout
        if len(content) > room:
            content = content[:room] + f"\n\n[... page truncated at {room} characters]"
        self.chars_used += len(content)
        self.fetch_cache[normalized] = content
        self.fetched_urls.add(normalized)
        return {
            "url": url,
            "content": content,
            "characters": len(content),
            "budget": {"fetches_used": self.fetches_used, "fetches_left": self.max_fetches - self.fetches_used},
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "web_search":
            return self.search(str(arguments.get("query", "")))
        if name == "fetch_url":
            return self.fetch(str(arguments.get("url", "")))
        return {"error": f"unknown tool: {name}"}


class QwenClient:
    def __init__(self, base_url: str, model: str | None, api_key: str | None = None, timeout: float = 180.0,
                 max_tokens: int = 4096) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.Client(timeout=timeout, headers=headers)

    def discover_model(self) -> str:
        if self.model:
            return self.model
        try:
            response = self.client.get(f"{self.base_url}/models")
            response.raise_for_status()
            models = response.json().get("data", [])
            if not models:
                raise HarnessError("the model server returned no models")
            self.model = str(models[0]["id"])
            return self.model
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise HarnessError(f"cannot discover a model at {self.base_url}/models: {exc}") from exc

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = TOOLS) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.discover_model(),
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": self.max_tokens,     # unset, a server may reserve its whole context for the reply
        }
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        try:
            response = self.client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            detail = ""
            if isinstance(exc, httpx.HTTPStatusError):
                detail = f"; response: {exc.response.text[:1000]}"
            raise HarnessError(f"Qwen request failed: {exc}{detail}") from exc


def cited_fetched_urls(answer: str, fetched_urls: set[str]) -> set[str]:
    found = re.findall(r"https?://[^\s<>\])}]+", answer)
    cited: set[str] = set()
    for raw in found:
        candidate = raw.rstrip(".,;:'\"")
        try:
            normalized = canonical_url(candidate)
        except ValueError:
            continue
        if normalized in fetched_urls:
            cited.add(normalized)
    return cited


def run_agent(question: str, qwen: QwenClient, research: ResearchTools, max_steps: int = 60, verbose: bool = False,
              system_prompt: str = SYSTEM_PROMPT) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    answer = ""
    nudges = 2
    for step in range(1, max_steps + 1):
        raw_message = qwen.complete(messages)
        message = {
            key: raw_message[key]
            for key in ("role", "content", "tool_calls")
            if key in raw_message
        }
        message.setdefault("role", "assistant")
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            answer = (message.get("content") or "").strip()
            # A question the model can work out itself tempts it to answer (or say nothing) without sources:
            # send it back to the tools rather than fail.
            if (not answer or not research.fetched_urls) and nudges:
                nudges -= 1
                messages.append({"role": "user", "content": "Do not answer yet: an answer must rest on sources. "
                                 "Call the search tool now, fetch the most authoritative results, then answer "
                                 "with inline citations to the fetched pages."})
                answer = ""
                continue
            break

        for call in tool_calls:
            function = call.get("function", {})
            name = str(function.get("name", ""))
            raw_arguments = function.get("arguments", "{}")
            arguments: dict[str, Any] = {}
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
                result = research.execute(name, arguments)
            except (json.JSONDecodeError, ValueError) as exc:
                result = {"error": f"invalid tool arguments: {exc}"}
            if verbose:
                print(
                    f"[{step}] {name} {json.dumps(arguments)} -> "
                    f"{len(json.dumps(result))} bytes",
                    file=sys.stderr,
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", f"call-{step}"),
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        messages.append(
            {
                "role": "user",
                "content": "The research step limit is reached. Answer now using only fetched evidence, with inline citations.",
            }
        )
        answer = (qwen.complete(messages, tools=None).get("content") or "").strip()

    if not answer:
        raise HarnessError("Qwen returned an empty answer")
    if not research.fetched_urls:
        raise HarnessError("the agent produced an answer without successfully fetching a source")

    if not cited_fetched_urls(answer, research.fetched_urls):
        allowed = "\n".join(sorted(research.fetched_urls))
        messages.extend(
            [
                {"role": "assistant", "content": answer},
                {
                    "role": "user",
                    "content": (
                        "Revise the answer so factual claims have inline Markdown citations. Cite only the fetched URLs "
                        f"listed below and retain a Sources section.\n\n{allowed}"
                    ),
                },
            ]
        )
        answer = (qwen.complete(messages, tools=None).get("content") or "").strip()
        if not cited_fetched_urls(answer, research.fetched_urls):
            raise HarnessError("Qwen did not cite any successfully fetched source")
    return answer


def research(question: str, qwen: QwenClient, tools: ResearchTools, *, max_steps: int = 20,
             verbose: bool = False, system_prompt: str = SYSTEM_PROMPT) -> dict[str, Any]:
    """One bounded research run: the cited answer, the pages it cites and every page fetched."""
    answer = run_agent(question, qwen, tools, max_steps, verbose, system_prompt)
    return {
        "question": question,
        "answer": answer,
        "cited": sorted(cited_fetched_urls(answer, tools.fetched_urls)),
        "fetched": sorted(tools.fetched_urls),
        "searches_used": tools.searches_used,
        "fetches_used": tools.fetches_used,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="+", help="Question to research")
    parser.add_argument("--base-url", default="http://127.0.0.1:7001/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--model", help="Qwen model ID; defaults to the first model reported by /v1/models")
    parser.add_argument("--vllm-api-key", default=os.environ.get("VLLM_API_KEY"), help="Defaults to VLLM_API_KEY")
    parser.add_argument("--tavily-api-key", default=os.environ.get("TAVILY_API_KEY"), help="Defaults to TAVILY_API_KEY")
    parser.add_argument("--obscura", type=Path, default=Path(__file__).with_name("obscura"))
    parser.add_argument("--max-searches", type=int, default=5, choices=range(1, 6), metavar="1..5")
    parser.add_argument("--max-fetches", type=int, default=50, choices=range(1, 51), metavar="1..50")
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.tavily_api_key:
        print("error: set TAVILY_API_KEY or pass --tavily-api-key", file=sys.stderr)
        return 2
    if not args.obscura.is_file():
        print(f"error: Obscura executable not found: {args.obscura}", file=sys.stderr)
        return 2

    research = ResearchTools(
        tavily=TavilyClient(api_key=args.tavily_api_key),
        obscura_path=args.obscura.resolve(),
        max_searches=args.max_searches,
        max_fetches=args.max_fetches,
    )
    try:
        answer = run_agent(
            " ".join(args.question),
            QwenClient(args.base_url, args.model, args.vllm_api_key),
            research,
            args.max_steps,
            args.verbose,
        )
    except (HarnessError, KeyboardInterrupt) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(answer)
    print(f"\nUsage: {research.searches_used}/{research.max_searches} searches, "
          f"{research.fetches_used}/{research.max_fetches} fetches", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
