import math

import pytest

from taces.business.privacy.mechanism import VOCABULARY, laplace, release


def test_release_allocates_one_epsilon_across_all_coordinates():
    scales = []
    def noise(scale):
        scales.append(scale)
        return 0
    result = release([4, 3, 2], [0, 0, 10, 0, 0], [0] * len(VOCABULARY), 0,
                     10, [1 / 3] * 3, .2, noise=noise)
    assert scales == pytest.approx([12] * 3 + [40] * 5 + [140] * (len(VOCABULARY) + 1))
    assert result["values"] == [4, 3, 2]
    assert result["pooledMean"] == 3
    assert result["interval"] == 4
    assert not result["distinguishable"]
    assert result["openText"] == {"responses": 0, "terms": []}


def test_interval_and_comparison_are_computed_from_noise_scale():
    result = release([1, 5], [0, 0, 100000, 0, 0], [0] * len(VOCABULARY), 0,
                     100000, [.5, .5], 1, noise=lambda _: 0)
    assert result["pooledMean"] == 3
    assert result["interval"] == .01
    assert result["spread"] == 4
    assert result["distinguishable"] is True


def test_postprocessing_preserves_public_total_and_bounds():
    result = release([4, 3], [1, 1, 1, 1, 1], [0] * len(VOCABULARY), 0,
                     5, [.5, .5], .1, noise=lambda _: -100000)
    assert result["values"] == [1, 1]
    assert result["pooledMean"] == 1
    assert sum(row["count"] for row in result["distribution"]) == 5
    assert all(row["count"] >= 0 for row in result["distribution"])
    assert result["openText"] == {"responses": 0, "terms": []}


@pytest.mark.parametrize("uniform,expected", [(.25, -2 * math.log(2)), (.75, 2 * math.log(2)), (.5, 0)])
def test_inverse_laplace_matches_known_quantiles(uniform, expected):
    assert laplace(2, random=lambda: uniform) == pytest.approx(expected)


def test_laplace_retries_endpoints_without_infinite_noise():
    values = iter([0, 1, .5])
    assert laplace(2, random=lambda: next(values)) == 0
    with pytest.raises(ValueError):
        laplace(2, random=lambda: 0)


@pytest.mark.parametrize("bad", [0, -1, float("inf"), True])
def test_release_rejects_invalid_sample_size(bad):
    with pytest.raises(ValueError):
        release([3], [0, 0, 1, 0, 0], [0] * len(VOCABULARY), 0, bad, [1], .1)
