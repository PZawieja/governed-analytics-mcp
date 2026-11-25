import pytest

from governed_analytics_mcp.scoring import fact_found, figure_mentioned


@pytest.mark.parametrize(
    "answer",
    [
        "Washington made $1,150,000.",
        "Washington: 1150000",
        "about $1.15M in Washington",
        "roughly 1.15 million",
    ],
)
def test_figure_mentioned_catches_formats(answer):
    assert figure_mentioned(1_150_000, answer)


def test_figure_mentioned_ignores_other_numbers():
    assert not figure_mentioned(870_000, "Oregon made $680,000 in October.")
    assert not figure_mentioned(1_150_000, "Store 11150000x")


def test_fact_found_is_the_vendored_behavior():
    assert fact_found("680000", "Oregon: $680,000.00")
