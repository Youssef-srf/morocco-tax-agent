from morocco_tax_agent.ratelimit import RateLimiter


def test_sliding_window():
    limiter = RateLimiter([(2, 60)])
    assert limiter.hit("ip", now=0) is None
    assert limiter.hit("ip", now=10) is None
    assert limiter.hit("ip", now=20) == 40  # wait until the first hit leaves the window
    assert limiter.hit("ip", now=60) is None  # first hit expired
    assert limiter.hit("other", now=20) is None  # keys are independent


def test_every_limit_applies():
    limiter = RateLimiter([(10, 60), (3, 86400)])
    for t in (0, 100, 200):
        assert limiter.hit("ip", now=t) is None
    assert limiter.hit("ip", now=300) == 86400 - 300  # daily limit, though the minute is free


def test_refused_requests_are_not_counted():
    limiter = RateLimiter([(1, 60)])
    limiter.hit("ip", now=0)
    for t in range(1, 50):
        limiter.hit("ip", now=t)  # refused
    assert limiter.hit("ip", now=60) is None
