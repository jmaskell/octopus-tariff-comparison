import time

import requests


class ApiError(Exception):
    pass


class OctopusClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.octopus.energy/v1/",
        session=None,
        max_retries: int = 3,
    ):
        self._auth = (api_key, "")
        self._base_url = base_url
        self._session = session or requests.Session()
        self._max_retries = max_retries

    def _request(self, url: str, params: dict | None) -> dict:
        last_status = None
        for attempt in range(self._max_retries):
            resp = self._session.get(url, params=params, auth=self._auth, timeout=30)
            last_status = resp.status_code
            if 200 <= resp.status_code < 300:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(f"GET {url} failed: HTTP {resp.status_code}")
        raise ApiError(f"GET {url} failed after retries: HTTP {last_status}")

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request(self._base_url + path, params)

    def get_results(self, path: str, params: dict | None = None) -> list[dict]:
        data = self._request(self._base_url + path, params)
        results = list(data.get("results", []))
        next_url = data.get("next")
        while next_url:
            data = self._request(next_url, None)
            results.extend(data.get("results", []))
            next_url = data.get("next")
        return results
