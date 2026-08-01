import pytest
from nifty_oc.fetcher import fetch_option_chain, FetchError


class FakeResp:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, home_status, api_responses):
        self.headers = {}
        self._home_status = home_status
        self._api_responses = list(api_responses)
        self.get_calls = []

    def get(self, url, timeout=None):
        self.get_calls.append(url)
        if "option-chain-indices" in url:
            return self._api_responses.pop(0)
        return FakeResp(self._home_status)  # homepage prime


def test_fetch_succeeds_first_try():
    good = FakeResp(200, {"records": {"underlyingValue": 24800, "expiryDates": [], "data": []}})
    session = FakeSession(home_status=200, api_responses=[good])
    payload = fetch_option_chain(session=session, sleep=lambda s: None)
    assert payload["records"]["underlyingValue"] == 24800


def test_fetch_retries_then_succeeds():
    bad = FakeResp(401, {})
    good = FakeResp(200, {"records": {"underlyingValue": 1, "expiryDates": [], "data": []}})
    session = FakeSession(home_status=200, api_responses=[bad, good])
    payload = fetch_option_chain(session=session, sleep=lambda s: None)
    assert payload["records"]["underlyingValue"] == 1


def test_fetch_raises_after_max_retries():
    bad = FakeResp(429, {})
    session = FakeSession(home_status=200, api_responses=[bad, bad, bad, bad, bad, bad])
    with pytest.raises(FetchError):
        fetch_option_chain(session=session, sleep=lambda s: None)


def test_fetch_treats_empty_payload_as_failure():
    empty = FakeResp(200, {})  # no "records"
    good = FakeResp(200, {"records": {"underlyingValue": 2, "expiryDates": [], "data": []}})
    session = FakeSession(home_status=200, api_responses=[empty, good])
    payload = fetch_option_chain(session=session, sleep=lambda s: None)
    assert payload["records"]["underlyingValue"] == 2
