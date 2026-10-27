"""Replacement adjacency with fixed, public participation and sample size.

One release splits epsilon 1/2 : 1/4 : 1/4 between the means vector,
five-bin submission histogram, and bounded public-vocabulary text vector.
This floating-point implementation is not a formally verified DP library.
"""

import math
import secrets

VOCABULARY = ("作业", "反馈", "节奏", "实验", "清晰", "互动", "实践", "例子", "考核", "答疑", "难度", "内容")


def laplace(scale, *, random=None):
    if not finite(scale, 0, 1e12):
        raise ValueError("Invalid noise scale")
    if scale == 0:
        return 0.0
    random = random or secrets.SystemRandom().random
    for _ in range(16):
        value = random()
        if not finite(value, 0, 1):
            raise ValueError("Invalid random sample")
        if 0 < value < 1:
            centered = value - .5
            return -scale * math.copysign(1, centered) * math.log1p(-2 * abs(centered))
    raise ValueError("Random source repeatedly returned endpoints")


def finite(value, low, high):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def whole(value, low, high):
    return type(value) is int and low <= value <= high


def normalized_counts(noisy, total):
    positive = [max(0, value) for value in noisy]
    summed = sum(positive)
    shares = [total * value / summed for value in positive] if summed else [total / 5] * 5
    counts = [math.floor(value) for value in shares]
    order = sorted(range(5), key=lambda i: shares[i] - counts[i], reverse=True)
    for i in order[:total - sum(counts)]:
        counts[i] += 1
    return [{"score": i + 1, "count": count} for i, count in enumerate(counts)]


def release(means, histogram, word_counts, text_count, n, weights, epsilon, *, noise=None):
    if (not whole(n, 1, 2**53) or not 1 <= len(means) <= 10 or len(weights) != len(means)
            or not all(finite(v, 1, 5) for v in means)
            or not all(finite(v, 0, 1) and v > 0 for v in weights)
            or not math.isclose(sum(weights), 1, abs_tol=1e-9)
            or not finite(epsilon, .01, 1) or len(histogram) != 5
            or not all(whole(v, 0, n) for v in histogram) or sum(histogram) != n
            or len(word_counts) != len(VOCABULARY) or not whole(text_count, 0, n)
            or not all(whole(v, 0, text_count) for v in word_counts)):
        raise ValueError("Invalid bounded aggregate")
    noise = noise or laplace
    d = len(means)
    mean_scale = (4 * d / n) / (epsilon / 2)
    values = [min(5, max(1, value + noise(mean_scale))) for value in means]
    pooled = round(sum(v * w for v, w in zip(values, weights)) / sum(weights), 2)
    rounded = [round(v, 2) for v in values]
    # Union bound over all dimension noises: P(any |noise| > b ln(10d)) <= .1.
    interval = min(4, math.ceil((mean_scale * math.log(10 * d) + .005) * 100) / 100)
    spread = round(max(rounded) - min(rounded), 2)
    distribution = normalized_counts([value + noise(2 / (epsilon / 4)) for value in histogram], n)
    text_scale = 7 / (epsilon / 4)
    # Every coordinate is always sampled, including absent words and empty texts.
    noisy_words = [value + noise(text_scale) for value in word_counts]
    responses = min(n, max(0, round(text_count + noise(text_scale))))
    terms = [{"word": word, "count": min(responses, max(0, round(value)))}
             for word, value in zip(VOCABULARY, noisy_words)]
    terms = sorted((term for term in terms if term["count"] > 0), key=lambda term: -term["count"])
    return {"values": rounded, "pooledMean": pooled, "interval": interval, "spread": spread,
            "distinguishable": spread > 2 * interval, "distribution": distribution,
            "openText": {"responses": responses, "terms": terms}}
