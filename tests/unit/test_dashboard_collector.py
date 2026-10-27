"""Synthetic REST payloads, not captured PRs or evidence of real coverage."""

from copy import deepcopy

import pytest

from orchestra.dashboard.collector import (
    CollectionState,
    LastGood,
    Page,
    Repository,
    Request,
    collect,
)

NOW = 1_793_145_600.0
REPO = Repository("github.com", "matteocervelli", "synthetic")


def payload(
    number=1,
    *,
    base="auto/integration",
    state="open",
    repository="synthetic",
    **changes,
):
    row = {
        "number": number,
        "url": f"https://api.github.com/repos/matteocervelli/{repository}/pulls/{number}",
        "html_url": f"https://github.com/matteocervelli/{repository}/pull/{number}",
        "title": f"Synthetic change {number}",
        "body": "Synthetic description; refs #999 is not an issue association",
        "state": state,
        "created_at": "2026-10-20T00:00:00Z",
        "updated_at": "2026-10-21T00:00:00Z",
        "closed_at": None if state == "open" else "2026-10-21T00:00:00Z",
        "merged_at": None,
        "merge_commit_sha": "b" * 40,
        "head": {"ref": "work", "sha": "a" * 40, "repo": {"full_name": "fork/x"}},
        "base": {"ref": base, "repo": {"full_name": f"matteocervelli/{repository}"}},
        "labels": [{"name": "example"}],
        "issue_url": f"https://api.github.com/repos/matteocervelli/{repository}/issues/1",
    }
    return {**row, **changes}


class Transport:
    def __init__(self, rows=(), *, has_next=None):
        self.rows = list(rows)
        self.calls = []
        self.has_next = has_next

    def __call__(self, request):
        self.calls.append(request)
        assert request.endpoint.startswith("repos/matteocervelli/")
        assert request.query["sort"] == "created"
        assert request.query["direction"] == "desc"
        assert request.query["per_page"] == 100
        if request.base != "auto/integration" or request.state != "open":
            return Page([], NOW, False)
        start = (request.page - 1) * 100
        rows = deepcopy(self.rows[start : start + 100])
        more = start + 100 < len(self.rows)
        return Page(rows, NOW, more if self.has_next is None else self.has_next)


def run(fetch, **kwargs):
    return collect([REPO], fetch, now=NOW, freshness=300, budget=25, **kwargs)


@pytest.mark.parametrize("count", [100, 201, 471, 1101])
def test_rest_pagination_exceeds_old_search_limits(count):
    fetch = Transport([payload(n) for n in range(1, count + 1)])
    result = run(fetch)
    assert len(result.rows) == count
    assert all(row["status"] == "complete" for row in result.coverage)
    assert max(r.page for r in fetch.calls) == (count + 99) // 100
    assert result.budget_remaining == 25 - len(fetch.calls)
    assert all("issue" not in row for row in result.rows)


def test_open_merge_sha_is_not_merge_and_head_fork_is_not_authority():
    result = run(Transport([payload()]))
    row = result.rows[0]
    assert row["state"] == "open"
    assert row["repository"]["nameWithOwner"] == "matteocervelli/synthetic"
    assert row["headRefName"] == "work" and row["headRefOid"] == "a" * 40
    assert "mergeCommit" not in row and "issue" not in row


def test_open_feeds_have_no_cutoff_and_main_is_collected():
    def fetch(request):
        if request.state == "all":
            return Page([], NOW, False)
        base = request.base
        return Page(
            [
                payload(
                    1 if base == "main" else 2,
                    base=base,
                    created_at="2020-01-01T00:00:00Z",
                )
            ],
            NOW,
            False,
        )

    result = run(fetch)
    assert {row["number"] for row in result.rows} == {1, 2}


def test_closed_and_merged_require_real_merged_at():
    def fetch(request):
        if request.state == "open":
            return Page([], NOW, False)
        return Page(
            [
                payload(1, state="closed"),
                payload(2, state="closed", merged_at="2026-10-21T00:00:00Z"),
            ],
            NOW,
            False,
        )

    rows = {r["number"]: r for r in run(fetch).rows}
    assert rows[1]["state"] == "closed" and rows[2]["state"] == "merged"


@pytest.mark.parametrize(
    "changes",
    [
        {"number": True},
        {"number": "1"},
        {"number": -1},
        {"html_url": "https://github.com/foreign/synthetic/pull/1"},
        {"html_url": "https://github.com/matteocervelli/other/pull/1"},
        {"html_url": "https://git.adlimen.dev/matteocervelli/synthetic/pulls/1"},
        {"html_url": "https://github.com/matteocervelli/synthetic/pull/2"},
        {"html_url": "https://github.com/matteocervelli/synthetic/pull/1?x=1"},
        {"url": "https://api.github.com/repos/foreign/synthetic/pulls/1"},
        {"base": {"ref": "main", "repo": {"full_name": "matteocervelli/synthetic"}}},
        {
            "base": {
                "ref": "auto/integration",
                "repo": {"full_name": "foreign/synthetic"},
            }
        },
        {"created_at": "2026-10-20"},
        {"labels": "example"},
        {"head": {"ref": "work", "sha": "not-a-sha"}},
    ],
)
def test_invalid_rows_fail_page_atomically(changes):
    result = run(Transport([payload(2), payload(**changes)]))
    assert result.rows == []
    assert result.coverage[0]["status"] != "complete"


@pytest.mark.parametrize(
    "host,owner,name",
    [
        ("git.adlimen.dev", "matteocervelli", "synthetic"),
        ("github.com", "foreign", "synthetic"),
        ("github.com", "matteocervelli", "../synthetic"),
    ],
)
def test_scope_is_explicit_not_an_arbitrary_owner_or_endpoint(host, owner, name):
    with pytest.raises(ValueError):
        collect(
            [Repository(host, owner, name)],
            lambda r: pytest.fail("no fetch"),
            now=NOW,
            freshness=300,
            budget=25,
        )


def test_shared_budget_resumes_fairly_and_keeps_previous_rows():
    repos = [Repository("github.com", "matteocervelli", f"repo{n}") for n in range(12)]
    calls = []

    def fetch(request):
        calls.append((request.repository, request.base, request.state))
        return Page([], NOW, False)

    first = collect(repos, fetch, now=NOW, freshness=300, budget=25)
    assert len(calls) == 25 and first.budget_remaining == 0
    assert any(c["reason"] == "budget" for c in first.coverage)
    state_before = deepcopy(first.state)
    second = collect(repos, fetch, now=NOW, freshness=300, budget=25, state=first.state)
    assert len(calls) == 36
    assert all(c["status"] == "complete" for c in second.coverage)
    assert first.state == state_before
    assert len(set(calls)) == 36


def test_budget_resume_continues_large_feed_instead_of_restart():
    fetch = Transport([payload(n) for n in range(1, 1301)])
    first = collect([REPO], fetch, now=NOW, freshness=300, budget=3)
    assert len(first.rows) == 100
    second = collect(
        [REPO], fetch, now=NOW, freshness=300, budget=25, state=first.state
    )
    assert len(second.rows) == 1300
    assert all(c["status"] == "complete" for c in second.coverage)
    assert len(fetch.calls) == 15


def test_cache_replay_makes_no_calls_and_keeps_retained_absent_rows():
    first = run(Transport([payload(1)]))
    retained = [
        {
            "number": 9,
            "url": "https://github.com/matteocervelli/synthetic/pull/9",
            "repository": {"nameWithOwner": "matteocervelli/synthetic"},
            "state": "open",
        }
    ]
    result = run(
        lambda r: pytest.fail("cache should cover traversal"),
        state=first.state,
        retained=retained,
    )
    assert {r["number"] for r in result.rows} == {1, 9}


def test_error_and_stale_do_not_overwrite_last_good_or_clear_rows():
    first = run(Transport([payload(1)]))
    good = deepcopy(first.state.last_good)

    def fail(request):
        raise TimeoutError("private provider text must not leak")

    result = collect(
        [REPO], fail, now=NOW + 400, freshness=300, budget=25, state=first.state
    )
    assert result.rows == first.rows
    assert result.state.last_good == good
    assert all(c["status"] != "complete" for c in result.coverage)
    assert "private provider" not in repr(result.coverage)
    assert all(c["fallback_stale"] for c in result.coverage)


@pytest.mark.parametrize("rows,has_next", [([], True), ([], None), ({}, False)])
def test_empty_unknown_or_wrong_payload_is_not_empty_complete(rows, has_next):
    result = run(lambda request: Page(rows, NOW, has_next))
    assert all(c["status"] != "complete" for c in result.coverage)


def test_repeated_pages_and_ordering_are_not_silent_completion():
    rows = [payload(n) for n in range(1, 101)]
    result = run(lambda request: Page(rows, NOW, True))
    assert any(c["reason"] == "repeated_page" for c in result.coverage)

    def unsorted(request):
        return Page(
            [payload(1), payload(2, created_at="2026-10-21T00:00:00Z")], NOW, False
        )

    assert all(c["status"] != "complete" for c in run(unsorted).coverage)


def test_history_cutoff_requires_whole_old_page():
    calls = []

    def fetch(request):
        calls.append((request.state, request.page))
        if request.state == "open":
            return Page([], NOW, False)
        if request.page == 1:
            return Page(
                [payload(1), payload(2, created_at="2020-01-01T00:00:00Z")], NOW, True
            )
        return Page([payload(3, created_at="2020-01-01T00:00:00Z")], NOW, True)

    result = run(fetch)
    assert ("all", 2) in calls and ("all", 3) not in calls
    assert [r["number"] for r in result.rows] == [1]


def test_conflicting_duplicate_feeds_are_incomplete_and_not_last_writer_wins():
    def fetch(request):
        if request.base == "main":
            return Page([], NOW, False)
        return Page([payload(title=request.state)], NOW, False)

    result = run(fetch)
    assert any(i["code"] == "conflicting_records" for i in result.issues)
    main = Request(REPO.full_name, "main", "open", 1, None).feed_key
    assert set(result.state.last_good) == {main}
    assert result.state.last_good[main].rows == {}
    assert result.rows == [] and result.state.known == {}
    for receipt in result.coverage:
        if receipt["fingerprint"] == main:
            assert (receipt["status"], receipt["reason"]) == ("complete", "exhausted")
        else:
            assert (receipt["status"], receipt["reason"]) == (
                "partial",
                "conflicting_records",
            )
            assert (receipt["scan_status"], receipt["scan_reason"]) == (
                "complete",
                "exhausted",
            )


def test_conflicting_feeds_preserve_prior_known_row_without_selecting_a_winner():
    first = run(Transport([payload(title="known")]))
    before = deepcopy(first.state)

    def fetch(request):
        if request.base == "main":
            return Page([], NOW + 400, False)
        return Page([payload(title=request.state)], NOW + 400, False)

    result = collect(
        [REPO],
        fetch,
        now=NOW + 400,
        freshness=300,
        budget=25,
        state=first.state,
        retained=first.rows,
    )
    assert result.rows == first.rows
    assert result.state.known == first.state.known
    main = Request(REPO.full_name, "main", "open", 1, None).feed_key
    for key, old_good in first.state.last_good.items():
        good = result.state.last_good[key]
        if key == main:
            assert good.rows == old_good.rows
            assert good.completed_at == NOW + 400
        else:
            assert good == old_good
    assert first.state == before
    assert any(i["code"] == "conflicting_records" for i in result.issues)


def test_fair_resume_does_not_starve_later_feeds_when_earlier_cache_expires():
    repos = [REPO, Repository("github.com", "matteocervelli", "second")]
    calls = []
    state = None
    for attempt in range(3):
        now = NOW + attempt * 400

        def fetch(request, observed=now):
            calls.append((request.repository, request.base, request.state))
            return Page([], observed, False)

        result = collect(repos, fetch, now=now, freshness=300, budget=1, state=state)
        state = result.state
    assert len(calls) == 3 and len(set(calls)) == 3


def test_absence_on_later_complete_traversals_never_deletes_known_rows():
    first = run(Transport([payload()]))
    state = first.state
    for attempt in (1, 2):
        now = NOW + attempt * 400
        result = collect(
            [REPO],
            lambda r, observed=now: Page([], observed, False),
            now=now,
            freshness=300,
            budget=25,
            state=state,
        )
        assert result.rows == first.rows
        state = result.state


def test_non_string_body_is_not_silently_coerced_to_empty():
    assert run(Transport([payload(body=0)])).rows == []


def test_rate_limit_is_explicit_and_does_not_contain_provider_details():
    result = run(lambda r: Page([], NOW, None, error="rate_limit"))
    assert all(c["reason"] == "rate_limit" for c in result.coverage)


def test_more_than_one_hundred_pages_is_partial_not_truncated_complete():
    fetch = Transport([payload(n) for n in range(1, 10002)])
    state = None
    for _ in range(5):
        result = collect([REPO], fetch, now=NOW, freshness=300, budget=25, state=state)
        state = result.state
    assert len(result.rows) == 10000
    assert result.coverage[0]["reason"] == "page_limit"
    assert result.coverage[0]["status"] != "complete"
    assert max(r.page for r in fetch.calls) == 100


def test_oversize_page_and_malicious_next_url_are_explicit_failures():
    result = run(Transport([payload(body="x" * (2 * 1024 * 1024))]))
    assert result.coverage[0]["reason"] == "payload_limit"
    result = run(lambda r: Page([], NOW, "https://foreign.test/page"))
    assert all(c["reason"] == "pagination_unknown" for c in result.coverage)


@pytest.mark.parametrize("budget", [-1, 26, True])
def test_shared_budget_cannot_be_implicitly_increased(budget):
    with pytest.raises(ValueError):
        collect(
            [REPO],
            lambda r: pytest.fail("no fetch"),
            now=NOW,
            freshness=300,
            budget=budget,
        )


def test_stale_observations_never_replace_last_good_or_shift_timestamps():
    result = run(lambda request: Page([], NOW - 400, False))
    assert all(c["status"] == "stale" for c in result.coverage)
    assert all(c["oldest_observation_at"] == NOW - 400 for c in result.coverage)
    assert result.state.last_good == {}


def test_ordering_across_pages_and_input_payload_immutability():
    rows = [payload(n) for n in range(1, 101)]
    rows.append(payload(101, created_at="2026-10-21T00:00:00Z"))
    before = deepcopy(rows)
    fetch = Transport(rows)
    result = run(fetch)
    assert len(result.rows) == 100
    assert result.coverage[0]["reason"] == "invalid_ordering"
    assert rows == before and fetch.rows == before


def test_explicit_clock_allows_observation_after_collection_start():
    result = collect(
        [REPO],
        lambda r: Page([], NOW + 1, False),
        now=NOW,
        clock=lambda: NOW + 2,
        freshness=300,
        budget=25,
    )
    assert all(c["status"] == "complete" for c in result.coverage)
    assert all(c["oldest_observation_at"] == NOW + 1 for c in result.coverage)


def test_explicit_clock_never_accepts_a_future_observation():
    result = collect(
        [REPO],
        lambda r: Page([], NOW + 3, False),
        now=NOW,
        clock=lambda: NOW + 2,
        freshness=300,
        budget=25,
    )
    assert all(c["reason"] == "invalid_observation_time" for c in result.coverage)
    assert result.state.last_good == {}


@pytest.mark.parametrize("diagnostic", ["error", "stale", "budget"])
def test_conflict_isolated_from_other_diagnostics_and_independent_last_good(diagnostic):
    state = CollectionState()
    repos = [
        REPO,
        Repository("github.com", "matteocervelli", "broken"),
        Repository("github.com", "matteocervelli", "independent"),
    ]
    plans = [
        ("auto/integration", "open"),
        ("main", "open"),
        ("auto/integration", "all"),
    ]
    for repo in repos:
        for base, kind in plans:
            request = Request(
                repo.full_name,
                base,
                kind,
                1,
                "2026-10-13T00:00:00Z" if kind == "all" else None,
            )
            state.last_good[request.feed_key] = LastGood({}, NOW - 100, NOW - 100)
            if repo.name == "broken":
                continue
            title = kind if repo.name == "synthetic" else "independent"
            rows = (
                [] if base == "main" else [payload(repository=repo.name, title=title)]
            )
            state.pages[request.cache_key] = Page(rows, NOW, False)
    before = deepcopy(state)

    def fetch(request):
        assert request.repository.endswith("/broken")
        assert diagnostic != "budget", "zero budget must not call transport"
        if diagnostic == "error":
            return Page([], NOW, None, error="rate_limit")
        return Page([], NOW - 400, False)

    result = collect(
        repos,
        fetch,
        now=NOW,
        freshness=300,
        budget=0 if diagnostic == "budget" else 25,
        state=state,
    )
    expected = {
        "error": ("error", "rate_limit"),
        "stale": ("stale", "exhausted"),
        "budget": ("partial", "budget"),
    }[diagnostic]
    for receipt in result.coverage:
        if receipt["repository"].endswith("/broken"):
            assert (receipt["status"], receipt["reason"]) == expected
            assert (
                result.state.last_good[receipt["fingerprint"]]
                == before.last_good[receipt["fingerprint"]]
            )
        elif (
            receipt["repository"].endswith("/independent")
            or receipt["query"]["base"] == "main"
        ):
            assert (receipt["status"], receipt["reason"]) == ("complete", "exhausted")
            assert result.state.last_good[receipt["fingerprint"]].completed_at == NOW
        else:
            assert (receipt["status"], receipt["reason"]) == (
                "partial",
                "conflicting_records",
            )
            assert (receipt["scan_status"], receipt["scan_reason"]) == (
                "complete",
                "exhausted",
            )
            assert receipt["conflicts"]
            assert (
                result.state.last_good[receipt["fingerprint"]]
                == before.last_good[receipt["fingerprint"]]
            )
    assert state == before


@pytest.mark.parametrize("stale_prefix", [False, True])
def test_shifted_offset_prefix_recovers_in_next_run_without_losing_known(stale_prefix):
    old = [payload(n, state="closed") for n in range(300, 100, -1)]
    context = {"rows": old, "now": NOW}
    calls = []

    def fetch(request):
        calls.append((request.state, request.page))
        if request.state == "open":
            return Page([], context["now"], False)
        start = (request.page - 1) * 100
        rows = context["rows"][start : start + 100]
        return Page(deepcopy(rows), context["now"], start + 100 < len(context["rows"]))

    first = collect([REPO], fetch, now=NOW, freshness=300, budget=3)
    assert len(first.rows) == 100 and first.coverage[2]["reason"] == "budget"
    original = deepcopy(first.state)
    changed = deepcopy(old)
    boundary = next(row for row in changed if row["number"] == 201)
    boundary.update(title="Updated boundary PR", updated_at="2026-10-23T00:00:00Z")
    new = payload(
        301,
        state="closed",
        created_at="2026-10-21T12:00:00Z",
        closed_at="2026-10-22T00:00:00Z",
        updated_at="2026-10-22T00:00:00Z",
    )
    context["rows"] = [new, *changed]
    context["now"] = NOW + (400 if stale_prefix else 1)
    if stale_prefix:
        state = first.state
    else:
        failed = collect(
            [REPO],
            fetch,
            now=context["now"],
            freshness=300,
            budget=25,
            state=first.state,
        )
        assert (failed.coverage[2]["status"], failed.coverage[2]["reason"]) == (
            "error",
            "conflicting_records",
        )
        assert failed.state.known == first.state.known
        history_key = first.coverage[2]["fingerprint"]
        assert failed.state.last_good.get(history_key) == first.state.last_good.get(
            history_key
        )
        assert all(
            failed.state.last_good[key].rows == good.rows
            for key, good in first.state.last_good.items()
        )
        # Prefix remains fresh: resetting only Progress would reuse the bad cache.
        assert (
            NOW
            + 1
            - failed.state.pages[
                next(key for key, page in failed.state.pages.items() if page.rows)
            ].fetched_at
            < 300
        )
        state = failed.state
        context["now"] += 1
    before_recovery = deepcopy(state)
    start_calls = len(calls)
    recovered = collect(
        [REPO], fetch, now=context["now"], freshness=300, budget=25, state=state
    )
    assert (recovered.coverage[2]["status"], recovered.coverage[2]["reason"]) == (
        "complete",
        "exhausted",
    )
    assert {r["number"] for r in recovered.rows} == set(range(101, 302))
    assert (
        next(r for r in recovered.rows if r["number"] == 201)["title"]
        == "Updated boundary PR"
    )
    assert [call for call in calls[start_calls:] if call[0] == "all"] == [
        ("all", 1),
        ("all", 2),
        ("all", 3),
    ]
    assert state == before_recovery and first.state == original
