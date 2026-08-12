"""The provider layer, offline.

What is testable without a network: the registry, credential detection, model
defaulting, effort mapping, content-part conversion, and the response-walking
helpers that pull sources out of each provider's very different result shapes.

Those walkers are the highest-risk code in the multi-provider work — three
different response schemas, one output type — so they are exercised here
against hand-built objects shaped like the real ones.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pitches_peaches import providers
from pitches_peaches.config import Config
from pitches_peaches.llm import LLM
from pitches_peaches.providers import PDF, ProviderError, Text, select
from pitches_peaches.providers.base import (
    as_parts,
    clamp_effort,
    dedupe,
    flatten_text,
)

PDF_BYTES = b"%PDF-1.4\n%fake\n"


@pytest.fixture
def pdf(tmp_path) -> Path:
    path = tmp_path / "cv.pdf"
    path.write_bytes(PDF_BYTES)
    return path


# -- registry ----------------------------------------------------------------


def test_all_three_providers_are_registered():
    assert set(providers.names()) == {"anthropic", "openai", "gemini"}


@pytest.mark.parametrize("name", ["anthropic", "openai", "gemini"])
def test_each_provider_satisfies_the_protocol(name):
    provider = select(name)
    for method in ("available", "parse", "write", "research"):
        assert callable(getattr(provider, method)), f"{name} lacks {method}"
    assert provider.name == name
    assert provider.default_model and provider.env_key


def test_unknown_provider_lists_the_real_ones():
    with pytest.raises(ProviderError) as err:
        select("openrouter")
    assert "anthropic" in str(err.value) and "gemini" in str(err.value)


def test_availability_follows_the_environment(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert not select("anthropic").available()
    assert not select("openai").available()
    assert not select("gemini").available()

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert select("openai").available()
    assert not select("anthropic").available()


def test_gemini_accepts_either_google_key_name(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    assert select("gemini").available()


def test_auto_picks_the_provider_that_has_a_credential(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert select("auto").name == "gemini"


def test_auto_with_no_credential_names_every_variable(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ProviderError) as err:
        select("auto")
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        assert key in str(err.value)


# -- model defaulting --------------------------------------------------------


@pytest.mark.parametrize(
    "provider,expected_prefix",
    [("anthropic", "claude"), ("openai", "gpt"), ("gemini", "gemini")],
)
def test_auto_model_resolves_per_provider(tmp_path, provider, expected_prefix):
    """Switching provider must not also require switching model."""
    llm = LLM(Config.load(tmp_path, provider=provider), provider=select(provider))
    assert llm.model.startswith(expected_prefix)


def test_an_explicit_model_is_never_overridden(tmp_path):
    llm = LLM(
        Config.load(tmp_path, provider="openai", model="gpt-4.1"),
        provider=select("openai"),
    )
    assert llm.model == "gpt-4.1"
    assert llm.describe() == "openai/gpt-4.1"


def test_blank_model_falls_back_to_the_default(tmp_path):
    llm = LLM(Config.load(tmp_path, provider="openai", model="  "), provider=select("openai"))
    assert llm.model == select("openai").default_model


# -- effort mapping ----------------------------------------------------------


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_anthropic_and_openai_share_the_whole_ladder(effort):
    from pitches_peaches.providers.anthropic import EFFORTS as ANTHROPIC
    from pitches_peaches.providers.openai import EFFORTS as OPENAI

    assert clamp_effort(effort, ANTHROPIC) == effort
    assert clamp_effort(effort, OPENAI) == effort


@pytest.mark.parametrize(
    "requested,expected",
    [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "high"), ("max", "high")],
)
def test_gemini_steps_down_rather_than_failing(requested, expected):
    """`--effort max` must stay usable on a provider whose ladder stops lower."""
    from pitches_peaches.providers.gemini import EFFORTS as GEMINI

    assert clamp_effort(requested, GEMINI) == expected


def test_unknown_effort_falls_back_to_high():
    assert clamp_effort("turbo", ("low", "medium", "high")) == "high"
    assert clamp_effort("", ("low", "medium", "high")) == "high"


# -- content parts -----------------------------------------------------------


def test_a_bare_string_becomes_one_text_part():
    parts = as_parts("hello")
    assert len(parts) == 1 and isinstance(parts[0], Text)
    assert flatten_text("hello") == "hello"


def test_flatten_text_skips_binary_parts(pdf):
    assert flatten_text([Text("a"), PDF(pdf), Text("b")]) == "a\n\nb"


def test_dedupe_preserves_order_and_drops_blanks():
    assert dedupe(["b", "a", "b", "", None, "c"]) == ["b", "a", "c"]


def test_anthropic_builds_a_document_block(pdf):
    from pitches_peaches.providers.anthropic import _blocks

    blocks = _blocks([Text("hi"), PDF(pdf)])
    assert blocks[0] == {"type": "text", "text": "hi"}
    assert blocks[1]["type"] == "document"
    assert blocks[1]["source"]["media_type"] == "application/pdf"
    assert blocks[1]["source"]["data"]  # base64, non-empty


def test_openai_builds_an_input_file_part(pdf):
    from pitches_peaches.providers.openai import _input

    message = _input([Text("hi"), PDF(pdf)])[0]
    assert message["role"] == "user"
    parts = message["content"]
    assert parts[0] == {"type": "input_text", "text": "hi"}
    assert parts[1]["type"] == "input_file"
    assert parts[1]["filename"] == "cv.pdf"
    assert parts[1]["file_data"].startswith("data:application/pdf;base64,")


def test_gemini_builds_inline_pdf_bytes(pdf):
    parts = select("gemini")._contents([Text("hi"), PDF(pdf)])[0].parts
    assert parts[0].text == "hi"
    assert parts[1].inline_data.mime_type == "application/pdf"
    assert parts[1].inline_data.data == PDF_BYTES


# -- response walking: three shapes, one output -----------------------------


def test_anthropic_extracts_searches_and_sources():
    from pitches_peaches.providers.anthropic import _searches_in, _sources_in

    blocks = [
        NS(type="server_tool_use", input={"query": "semgrep funding"}),
        NS(type="web_search_tool_result", content=[NS(url="https://a"), NS(url="https://b")]),
        NS(type="text", text="prose"),
    ]
    assert _searches_in(blocks) == ["semgrep funding"]
    assert _sources_in(blocks) == ["https://a", "https://b"]


def test_anthropic_survives_a_search_error_block():
    """On failure `content` is an error object, not a list of results."""
    from pitches_peaches.providers.anthropic import _sources_in

    blocks = [NS(type="web_search_tool_result", content=NS(error_code="max_uses_exceeded"))]
    assert _sources_in(blocks) == []


def test_openai_extracts_searches_and_citation_urls():
    from pitches_peaches.providers.openai import _searches_in, _sources_in

    response = NS(
        output=[
            NS(type="web_search_call", action=NS(query="semgrep funding"), content=None),
            NS(
                type="message",
                content=[
                    NS(
                        annotations=[
                            NS(type="url_citation", url="https://a"),
                            NS(type="file_citation", url=None),
                        ]
                    )
                ],
            ),
        ]
    )
    assert _searches_in(response) == ["semgrep funding"]
    assert _sources_in(response) == ["https://a"]


def test_openai_walkers_tolerate_an_empty_response():
    from pitches_peaches.providers.openai import _searches_in, _sources_in

    assert _searches_in(NS(output=None)) == []
    assert _sources_in(NS(output=[])) == []


def test_gemini_extracts_grounding_chunks():
    from pitches_peaches.providers.gemini import _grounding

    event = NS(
        candidates=[
            NS(
                grounding_metadata=NS(
                    web_search_queries=["semgrep funding"],
                    grounding_chunks=[
                        NS(web=NS(uri="https://a", title="A")),
                        NS(web=None),
                    ],
                )
            )
        ]
    )
    sources, searches = _grounding(event)
    assert sources == ["https://a"]
    assert searches == ["semgrep funding"]


def test_gemini_tolerates_an_ungrounded_event():
    from pitches_peaches.providers.gemini import _grounding

    assert _grounding(NS(candidates=[NS(grounding_metadata=None)])) == ([], [])
    assert _grounding(NS(candidates=None)) == ([], [])


# -- structured output portability ------------------------------------------


@pytest.mark.parametrize(
    "schema_name",
    ["Recon", "Profile", "MatchDraft", "Playbook", "Gate", "Diagrams"],
)
def test_every_schema_converts_for_openai_strict_mode(schema_name):
    """OpenAI rejects some JSON Schema keywords outright; catch it here, cheaply."""
    from openai.lib._pydantic import to_strict_json_schema

    import pitches_peaches.models as models

    to_strict_json_schema(getattr(models, schema_name))


@pytest.mark.parametrize(
    "schema_name",
    ["Recon", "Profile", "MatchDraft", "Playbook", "Gate", "Diagrams"],
)
def test_every_schema_is_accepted_by_gemini(schema_name):
    from google.genai import types

    import pitches_peaches.models as models

    types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=getattr(models, schema_name),
    )
