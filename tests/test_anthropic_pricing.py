import pytest

from my_agent_crew.llm.anthropic_pricing import cost_usd, family
from my_agent_crew.llm.anthropic_stream import usage_from


def test_a_plain_call_costs_its_input_and_output_at_the_model_rate():
    # Claude Sonnet 5.5: $2 in, $10 out per million tokens.
    assert cost_usd("claude-sonnet-5-5", fresh=1_000_000, output=100_000) == pytest.approx(3.0)


def test_cache_reads_and_writes_are_priced_at_their_own_rates():
    # Claude Opus 5.5: $4 in, $20 out, $0.20 cache read; writes 1.25x (5 min), 2x (1 h).
    cost = cost_usd(
        "claude-opus-5-5",
        fresh=100_000,
        cache_read=1_000_000,
        write_5m=200_000,
        write_1h=100_000,
        output=10_000,
    )
    expected = 0.4 + 0.2 + 200_000 * 4 * 1.25 / 1e6 + 100_000 * 4 * 2 / 1e6 + 0.2
    assert cost == pytest.approx(expected)


def test_claude_haiku_5_5_bills_a_long_prompt_at_its_higher_tier():
    short = cost_usd("claude-haiku-5-5", fresh=100_000, output=1_000_000)
    long = cost_usd("claude-haiku-5-5", fresh=50_000, cache_read=60_000, output=1_000_000)
    assert short == pytest.approx(0.01 + 0.5)
    assert long == pytest.approx(50_000 * 0.5 / 1e6 + 60_000 * 0.05 / 1e6 + 2.5)


def test_a_dated_id_finds_its_family_and_the_longest_family_wins():
    assert family("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert family("claude-opus-5-5") == "claude-opus-5-5"
    assert family("claude-opus-5") == "claude-opus-5"
    assert family("claude-fable-5-1") == "claude-fable-5-1"
    assert family("claude-sonnet-50") is None


def test_an_unknown_model_has_no_price_rather_than_a_guess():
    assert cost_usd("claude-unknown-9", fresh=1000, output=1000) is None


def test_usage_counts_the_whole_prompt_and_the_cached_part():
    usage = usage_from(
        {
            "input_tokens": 50,
            "cache_read_input_tokens": 9000,
            "cache_creation_input_tokens": 1000,
            "cache_creation": {"ephemeral_5m_input_tokens": 600, "ephemeral_1h_input_tokens": 400},
            "output_tokens": 300,
        },
        "claude-sonnet-5-5",
    )
    assert usage.prompt_tokens == 10_050
    assert usage.cached_tokens == 9000
    assert usage.completion_tokens == 300
    expected = (50 * 2 + 9000 * 0.2 + 600 * 2.5 + 400 * 4 + 300 * 10) / 1e6
    assert usage.cost_usd == pytest.approx(expected)


def test_writes_without_a_lifetime_split_are_priced_as_five_minute_writes():
    usage = usage_from(
        {"input_tokens": 0, "cache_creation_input_tokens": 1000, "output_tokens": 0},
        "claude-sonnet-5-5",
    )
    assert usage.cost_usd == pytest.approx(1000 * 2.5 / 1e6)
