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
from pitches_peaches.providers import (
    PDF,
    CredentialError,
    PackageMissing,
    ProviderError,
    Text,
    resolve,
    select,
)
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


def test_every_provider_declares_its_sdk_and_extra():
    for name in providers.names():
        provider = select(name)
        assert provider.package
        assert provider.installed() in (True, False)


# -- resolution: the composition root ---------------------------------------


@pytest.fixture
def no_keys(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    "provider,expected_prefix",
    [("anthropic", "claude"), ("openai", "gpt"), ("gemini", "gemini")],
)
def test_model_defaults_per_provider(no_keys, monkeypatch, provider, expected_prefix):
    """Switching provider must not also require switching model."""
    monkeypatch.setenv(select(provider).env_key, "x")
    assert resolve(provider).model.startswith(expected_prefix)


def test_an_explicit_model_is_never_overridden(no_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert resolve("openai", model="gpt-4.1").model == "gpt-4.1"


@pytest.mark.parametrize("model", [None, "", "  ", "auto", "AUTO"])
def test_blank_or_auto_model_falls_back_to_the_default(no_keys, monkeypatch, model):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert resolve("openai", model=model).model == select("openai").default_model


def test_auto_is_the_default_and_picks_the_key_you_have(no_keys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    for requested in (None, "auto", "AUTO", "  "):
        resolution = resolve(requested)
        assert resolution.name == "gemini"
        assert "only provider you have a key for" in resolution.reason


def test_auto_with_several_keys_is_deterministic_and_says_so(no_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    resolution = resolve("auto")
    assert resolution.name == "openai"          # registry order
    assert "gemini" in resolution.reason        # and it tells you about the other
    assert "--provider" in resolution.reason


def test_llm_is_built_from_a_resolution_not_a_lookup(tmp_path, no_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    llm = LLM.from_config(Config.load(tmp_path, provider="openai"))
    assert llm.describe() == "openai/" + select("openai").default_model
    # the provider is held, not re-selected on each access
    assert llm.provider is llm.provider


# -- the errors are the feature ----------------------------------------------


def test_no_key_at_all_lists_every_provider_and_the_env_path(no_keys, tmp_path):
    with pytest.raises(CredentialError) as err:
        resolve("auto", workdir=tmp_path)
    message = str(err.value)
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        assert key in message
    assert str(tmp_path.resolve() / ".env") in message
    assert ".env.sample" in message


def test_wrong_provider_for_the_key_you_have_says_exactly_what_to_do(
    no_keys, monkeypatch
):
    """The complaint that motivated this: an OpenAI key and an Anthropic default."""
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(CredentialError) as err:
        resolve("anthropic")
    message = str(err.value)
    assert "ANTHROPIC_API_KEY" in message and "not set" in message
    assert "You do have OPENAI_API_KEY set" in message
    assert "--provider openai" in message
    assert "PEACHES_PROVIDER=openai" in message
    assert 'provider = "openai"' in message


def test_missing_sdk_names_the_extra_that_installs_it(no_keys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(
        "pitches_peaches.providers.openai.OpenAIProvider.installed", lambda self: False
    )
    with pytest.raises(PackageMissing) as err:
        resolve("openai")
    assert "pitches-peaches[openai]" in str(err.value)


def test_unknown_provider_lists_the_real_ones_and_auto():
    with pytest.raises(ProviderError) as err:
        resolve("openrouter")
    message = str(err.value)
    assert "anthropic" in message and "gemini" in message and "auto" in message


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


SCHEMAS = ["Recon", "Profile", "MatchDraft", "Playbook", "Gate", "Diagrams"]


@pytest.mark.parametrize("schema_name", SCHEMAS)
def test_every_schema_converts_for_openai_strict_mode(schema_name):
    """OpenAI rejects some JSON Schema keywords outright; catch it here, cheaply."""
    from openai.lib._pydantic import to_strict_json_schema

    import pitches_peaches.models as models

    to_strict_json_schema(getattr(models, schema_name))


def _walk(node, path="()"):
    """Yield (path, object-schema) for every object in a JSON schema."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield path, node
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


@pytest.mark.parametrize("schema_name", SCHEMAS)
def test_no_schema_contains_a_free_form_object(schema_name):
    """A `dict[str, str]` field passes local conversion and is refused by the API.

    OpenAI strict mode requires `required` to list every key in `properties`,
    which an object with arbitrary keys cannot satisfy — the SDK emits it
    happily and the server returns 400. This is the check that would have
    caught `Profile.contact` before it cost a live call.
    """
    from openai.lib._pydantic import to_strict_json_schema

    import pitches_peaches.models as models

    schema = to_strict_json_schema(getattr(models, schema_name))
    for path, obj in _walk(schema):
        extra = obj.get("additionalProperties")
        assert extra is False or extra is None, (
            f"{schema_name} at {path} allows arbitrary keys "
            f"(additionalProperties={extra!r}). Model it as a list of typed "
            "items instead — a free-form object is not expressible in a "
            "strict JSON schema."
        )
        required = set(obj.get("required", []))
        properties = set(obj.get("properties", {}))
        assert required == properties, (
            f"{schema_name} at {path}: required and properties disagree "
            f"(only in required: {sorted(required - properties)}; "
            f"only in properties: {sorted(properties - required)})"
        )


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


# -- SDK exceptions become readable errors ----------------------------------


class _FakeStatusError(Exception):
    """Shaped like an SDK's HTTP error: carries a status code."""

    def __init__(self, status_code: int):
        super().__init__(f"Error code: {status_code}")
        self.status_code = status_code


def _llm_over(provider_name: str, tmp_path, monkeypatch, raising: Exception):
    monkeypatch.setenv(select(provider_name).env_key, "x")
    provider = select(provider_name)

    def boom(*args, **kwargs):
        raise raising

    monkeypatch.setattr(provider, "research", boom, raising=False)
    monkeypatch.setattr(provider, "write", boom, raising=False)
    monkeypatch.setattr(provider, "parse", boom, raising=False)
    return LLM(Config.load(tmp_path), provider, "some-model")


def test_401_says_the_key_was_rejected_and_how_to_check(tmp_path, monkeypatch):
    """The traceback that started this: a stray character in front of the key."""
    llm = _llm_over("openai", tmp_path, monkeypatch, _FakeStatusError(401))
    with pytest.raises(ProviderError) as err:
        llm.write(system="s", content="c")
    message = str(err.value)
    assert "openai rejected OPENAI_API_KEY" in message
    assert "stray character" in message
    assert "OPENAI_API_KEY" in message


def test_404_names_the_model_and_the_fallback(tmp_path, monkeypatch):
    llm = _llm_over("openai", tmp_path, monkeypatch, _FakeStatusError(404))
    with pytest.raises(ProviderError) as err:
        llm.parse(Config, system="s", content="c")
    message = str(err.value)
    assert "'some-model'" in message
    assert "--model" in message


def test_429_mentions_quota_and_effort(tmp_path, monkeypatch):
    llm = _llm_over("openai", tmp_path, monkeypatch, _FakeStatusError(429))
    with pytest.raises(ProviderError) as err:
        llm.research(system="s", content="c")
    assert "quota" in str(err.value) and "--effort" in str(err.value)


def test_5xx_is_attributed_to_the_provider(tmp_path, monkeypatch):
    llm = _llm_over("anthropic", tmp_path, monkeypatch, _FakeStatusError(503))
    with pytest.raises(ProviderError) as err:
        llm.write(system="s", content="c")
    assert "their side" in str(err.value)


def test_a_status_on_the_response_object_is_also_found(tmp_path, monkeypatch):
    class WithResponse(Exception):
        def __init__(self):
            super().__init__("boom")
            self.response = NS(status_code=401)

    llm = _llm_over("openai", tmp_path, monkeypatch, WithResponse())
    with pytest.raises(ProviderError) as err:
        llm.write(system="s", content="c")
    assert "rejected" in str(err.value)


def test_an_error_with_no_status_is_left_alone(tmp_path, monkeypatch):
    """Don't swallow programming errors — only translate HTTP failures."""
    llm = _llm_over("openai", tmp_path, monkeypatch, ValueError("a real bug"))
    with pytest.raises(ValueError, match="a real bug"):
        llm.write(system="s", content="c")


def test_provider_errors_pass_through_untranslated(tmp_path, monkeypatch):
    llm = _llm_over("openai", tmp_path, monkeypatch, ProviderError("already clear"))
    with pytest.raises(ProviderError, match="already clear"):
        llm.write(system="s", content="c")


def test_a_stream_that_stops_early_is_not_a_traceback():
    """The SDK raises a bare RuntimeError with no status, so it slipped past.

    It surfaced as a forty-line traceback at the last stage of a run whose
    every earlier stage had already been paid for.
    """
    from pitches_peaches.providers.base import ProviderError, api_errors

    class _P:
        name = "openai"
        env_key = "OPENAI_API_KEY"

    with pytest.raises(ProviderError) as err:
        with api_errors(_P(), "gpt-5.4-mini"):
            raise RuntimeError("Didn't receive a `response.completed` event.")

    message = str(err.value)
    assert "already written to disk" in message
    assert "again" in message, "and it must name what to do about it"


def test_an_unrelated_runtime_error_still_propagates():
    """Only a truncated stream is translated; a real bug must stay a real bug."""
    from pitches_peaches.providers.base import api_errors

    class _P:
        name = "openai"
        env_key = "OPENAI_API_KEY"

    with pytest.raises(RuntimeError, match="something else entirely"):
        with api_errors(_P(), "gpt-5.4-mini"):
            raise RuntimeError("something else entirely")
