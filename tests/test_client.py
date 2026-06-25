import pytest

from octopus_compare.client import OctopusClient, ApiError


class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, auth=None, timeout=None):
        self.calls.append((url, params, auth))
        return self._responses.pop(0)


def test_get_uses_basic_auth_and_returns_json():
    session = FakeSession([FakeResponse(200, {"number": "A-1"})])
    c = OctopusClient("sk_test", session=session)
    data = c.get("accounts/A-1/")
    assert data == {"number": "A-1"}
    url, params, auth = session.calls[0]
    assert url == "https://api.octopus.energy/v1/accounts/A-1/"
    assert auth == ("sk_test", "")


def test_get_results_follows_pagination():
    page1 = FakeResponse(200, {"next": "https://api.octopus.energy/v1/x/?page=2",
                               "results": [{"a": 1}]})
    page2 = FakeResponse(200, {"next": None, "results": [{"a": 2}]})
    session = FakeSession([page1, page2])
    c = OctopusClient("sk_test", session=session)
    results = c.get_results("x/")
    assert results == [{"a": 1}, {"a": 2}]


def test_get_raises_apierror_on_401():
    session = FakeSession([FakeResponse(401, {"detail": "no"})])
    c = OctopusClient("sk_test", session=session)
    with pytest.raises(ApiError):
        c.get("accounts/A-1/")
