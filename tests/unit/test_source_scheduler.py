from gamecrafter.infrastructure.ingestion.scheduler import HostAccessScheduler


def test_scheduler_reserves_minimum_spacing_per_host() -> None:
    now = [10.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    scheduler = HostAccessScheduler(
        global_concurrency=2,
        per_host_concurrency=1,
        min_interval_seconds=1.0,
        monotonic=lambda: now[0],
        sleep=sleep,
    )

    with scheduler.slot("https://nte.perfectworld.com/en/main.html"):
        pass
    with scheduler.slot("https://nte.perfectworld.com/en/article/news/index.html"):
        pass

    assert sleeps == [1.0]


def test_robots_interval_can_only_raise_the_configured_floor() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    scheduler = HostAccessScheduler(
        global_concurrency=1,
        per_host_concurrency=1,
        min_interval_seconds=1.0,
        monotonic=lambda: now[0],
        sleep=sleep,
    )

    url = "https://nte.perfectworld.com/en/main.html"
    with scheduler.slot(url):
        pass
    scheduler.update_host_interval("nte.perfectworld.com", 0.5)
    with scheduler.slot(url):
        pass
    scheduler.update_host_interval("nte.perfectworld.com", 3.0)
    with scheduler.slot(url):
        pass
    with scheduler.slot(url):
        pass

    assert sleeps == [1.0, 1.0, 3.0]
