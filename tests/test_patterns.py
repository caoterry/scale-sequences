# SPDX-License-Identifier: MIT
"""Hand-written index streams for small boxes -- the pattern code must reproduce them exactly."""
import pytest

from scaleseq.patterns import PATTERNS, Pattern, get_pattern


def flat(*groups):
    return [x for g in groups for x in g]


CASES = {
    ("3s", 6): flat([0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5], [5, 4, 3], [4, 3, 2], [3, 2, 1], [2, 1, 0]),
    ("4s", 6): flat([0, 1, 2, 3], [1, 2, 3, 4], [2, 3, 4, 5], [5, 4, 3, 2], [4, 3, 2, 1], [3, 2, 1, 0]),
    ("neighbor3", 5): flat([0], [1, 0, 1], [2, 1, 2], [3, 2, 3], [4, 3, 4], [3, 2, 3], [2, 1, 2], [1, 0, 1], [0]),
    ("1231", 5): flat([0, 1, 2, 0], [1, 2, 3, 1], [2, 3, 4, 3], [2, 4, 3, 2], [1, 3, 2, 1], [0, 2, 1, 0]),
    ("upper-neighbor3", 4): flat([0, 1, 0], [1, 2, 1], [2, 3, 2], [1, 2, 1], [0, 1, 0]),
    ("6s", 7): flat([0, 1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1], [5, 4, 3, 2, 1, 0]),
    ("thirds", 4): flat([0, 2], [1, 3], [3, 1], [2, 0]),
    ("scale", 4): [0, 1, 2, 3, 2, 1, 0],
}


@pytest.mark.parametrize("name,n", list(CASES))
def test_stream_matches_hand_written(name, n):
    assert get_pattern(name).stream(n) == CASES[(name, n)]


# desc_skip / desc_stop / repeat_top are for patterns added to match an exercise the user has; no built-in
# pattern uses them, so they are checked here on patterns defined in the test.
@pytest.mark.parametrize("pattern,n,want", [
    (Pattern("t", (0, 2), "", desc_skip=(1,)), 5, flat([0, 2], [1, 3], [2, 4], [4, 2], [2, 0])),
    (Pattern("t", (0, 1), "", desc_stop=2), 5, flat([0, 1], [1, 2], [2, 3], [3, 4], [4, 3], [3, 2], [0])),
    (Pattern("t", (0, 2), "", repeat_top=False), 5, flat([0, 2], [1, 3], [2, 4], [3, 1], [2, 0])),
])
def test_descent_parameters(pattern, n, want):
    assert pattern.stream(n) == want


def test_aliases():
    assert get_pattern("1234") is get_pattern("4s") is get_pattern("fours")
    assert get_pattern("threes").name == "3s" and get_pattern("sixes").name == "6s"


@pytest.mark.parametrize("name", list(PATTERNS))
@pytest.mark.parametrize("n", [8, 14, 15, 16])
def test_every_pattern_bottom_to_top_and_back(name, n):
    s = get_pattern(name).stream(n)
    assert s[0] == 0 and s[-1] == 0 and max(s) == n - 1 and min(s) == 0
    assert set(s) == set(range(n))  # every box note is played


def test_too_small_box():
    with pytest.raises(ValueError):
        get_pattern("6s").stream(4)
