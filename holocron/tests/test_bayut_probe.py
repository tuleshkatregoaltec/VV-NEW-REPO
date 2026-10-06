from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from holocron.sources.bayut_listings.probe import (
    BayutProbePlan,
    build_trial_schedule,
    classify_probe_outcome,
    load_probe_events,
    parse_identity_payload,
    sanitized_plan,
    summarize_probe_events,
    validate_identity_result,
    validate_proxy_environment,
)


def _plan(**overrides: object) -> BayutProbePlan:
    payload: dict[str, object] = {
        "identity_url": "https://security.example.test/identity",
        "cohorts": [
            {
                "name": "direct",
                "proxy": "direct",
                "identity_check_scope": "trial",
                "pause_seconds": 0,
            },
            {
                "name": "rotating",
                "trials": 2,
                "proxy": "residential",
                "proxy_session_scope": "page",
                "isolation": "fresh_context",
                "identity_check_scope": "page",
                "pause_seconds": 0,
            },
        ],
    }
    payload.update(overrides)
    return BayutProbePlan.model_validate(payload)


def test_plan_rejects_page_rotation_inside_reused_context() -> None:
    with pytest.raises(ValidationError, match="page-scoped proxy sessions"):
        BayutProbePlan.model_validate(
            {
                "cohorts": [
                    {
                        "name": "invalid",
                        "proxy": "residential",
                        "proxy_session_scope": "page",
                        "isolation": "reuse_context",
                    }
                ]
            }
        )


def test_proxy_session_rotation_requires_provider_template_and_stays_out_of_plan() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="BAYUT_PROBE_PROXY_SERVER"):
        validate_proxy_environment(plan, {})
    with pytest.raises(ValueError, match=r"requires \{session\}"):
        validate_proxy_environment(
            plan,
            {
                "BAYUT_PROBE_PROXY_SERVER": "http://proxy.example:8000",
                "BAYUT_PROBE_PROXY_USERNAME": "fixed-user",
            },
        )

    validate_proxy_environment(
        plan,
        {
            "BAYUT_PROBE_PROXY_SERVER": "http://proxy.example:8000",
            "BAYUT_PROBE_PROXY_USERNAME": "customer-session-{session}",
            "BAYUT_PROBE_PROXY_PASSWORD": "secret",
        },
    )
    serialized = json.dumps(sanitized_plan(plan))
    assert "customer-session" not in serialized
    assert "secret" not in serialized
    assert "BAYUT_PROBE_PROXY_PASSWORD" in serialized


def test_trial_schedule_is_seeded_and_interleaves_complete_trial_set() -> None:
    plan = _plan(random_seed=7)
    first = [
        (task.cohort.name, task.trial, task.search_path) for task in build_trial_schedule(plan)
    ]
    second = [
        (task.cohort.name, task.trial, task.search_path) for task in build_trial_schedule(plan)
    ]
    assert first == second
    assert sorted(first) == [
        ("direct", 1, "/for-sale/property/dubai/"),
        ("direct", 1, "/to-rent/property/dubai/"),
        ("rotating", 1, "/for-sale/property/dubai/"),
        ("rotating", 1, "/to-rent/property/dubai/"),
        ("rotating", 2, "/for-sale/property/dubai/"),
        ("rotating", 2, "/to-rent/property/dubai/"),
    ]


def test_plan_rejects_unedited_identity_placeholder() -> None:
    with pytest.raises(ValidationError, match="replace the identity_url placeholder"):
        _plan(identity_url="https://REPLACE-WITH-INTERNAL.example/identity")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "final_url": "https://www.bayut.com/captchaChallenge",
                "html": "",
                "status_code": 200,
                "card_count": 0,
                "navigation_error": "",
            },
            "captcha",
        ),
        (
            {
                "final_url": "https://www.bayut.com/search",
                "html": "",
                "status_code": 429,
                "card_count": 0,
                "navigation_error": "",
            },
            "rate_limited",
        ),
        (
            {
                "final_url": "https://www.bayut.com/search",
                "html": "",
                "status_code": 200,
                "card_count": 12,
                "navigation_error": "",
            },
            "ok",
        ),
    ],
)
def test_outcome_classification_prioritizes_challenge_evidence(
    kwargs: dict[str, Any], expected: str
) -> None:
    assert classify_probe_outcome(**kwargs) == expected


def test_identity_parser_accepts_common_provider_shapes() -> None:
    assert parse_identity_payload(
        {
            "query": "203.0.113.7",
            "countryCode": "AE",
            "asn": {"asn": "AS64500"},
            "organization": "Example Residential",
        }
    ) == {
        "ip": "203.0.113.7",
        "country": "AE",
        "asn": "AS64500",
        "org": "Example Residential",
    }


def test_required_identity_result_fails_on_errors_missing_ip_and_wrong_country() -> None:
    validate_identity_result(
        {"ip": "203.0.113.7", "country": "AE", "error": ""}, expected_country="AE"
    )
    with pytest.raises(RuntimeError, match="identity check failed"):
        validate_identity_result({"error": "proxy authentication failed"})
    with pytest.raises(RuntimeError, match="did not return an IP"):
        validate_identity_result({"country": "AE"})
    with pytest.raises(RuntimeError, match="country mismatch"):
        validate_identity_result(
            {"ip": "203.0.113.7", "country": "US"},
            expected_country="AE",
        )


def test_summary_preserves_censoring_and_deduplicates_identity_samples(tmp_path: Path) -> None:
    events = [
        {
            "cohort": "sticky",
            "search_path": "/for-sale/property/dubai/",
            "trial": 1,
            "page_in_trial": 1,
            "outcome": "ok",
            "latency_ms": 100,
            "card_count": 10,
            "new_listing_count": 8,
            "card_field_counts": {"title": 10, "price_aed": 9},
            "network": {"request_count": 20, "response_bytes": 1_000_000},
            "identity": {"sample_id": "sample-a", "ip": "203.0.113.1", "country": "AE"},
            "expected_country": "AE",
        },
        {
            "cohort": "sticky",
            "search_path": "/for-sale/property/dubai/",
            "trial": 1,
            "page_in_trial": 2,
            "outcome": "captcha",
            "latency_ms": 200,
            "card_count": 0,
            "new_listing_count": 0,
            "card_field_counts": {},
            "network": {"request_count": 5, "response_bytes": 100_000},
            "identity": {"sample_id": "sample-a", "ip": "203.0.113.1", "country": "AE"},
            "expected_country": "AE",
        },
        {
            "cohort": "sticky",
            "search_path": "/to-rent/property/dubai/",
            "trial": 2,
            "page_in_trial": 1,
            "outcome": "ok",
            "latency_ms": 150,
            "card_count": 10,
            "new_listing_count": 10,
            "card_field_counts": {"title": 10, "price_aed": 10},
            "network": {"request_count": 20, "response_bytes": 1_000_000},
            "identity": {"sample_id": "sample-b", "ip": "203.0.113.2", "country": "AE"},
            "expected_country": "AE",
        },
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n")

    summary = summarize_probe_events(load_probe_events(path))["cohorts"]["sticky"]
    assert summary["challenged_trials"] == 1
    assert summary["censored_trials_without_challenge"] == 1
    assert summary["median_observed_challenge_page"] == 2
    assert summary["identity_samples"] == 2
    assert summary["unique_observed_ips"] == 2
    assert summary["proxy_ip_uniqueness_ratio"] == 1.0
    assert summary["duplicate_card_rate"] == 0.1
    assert summary["card_field_availability"]["price_aed"] == 0.95
    assert summary["search_paths"]["/for-sale/property/dubai/"]["challenged_trials"] == 1
    assert summary["search_paths"]["/to-rent/property/dubai/"]["challenged_trials"] == 0
