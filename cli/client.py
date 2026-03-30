import httpx
from typing import Any


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class LakehouseClient:
    def __init__(self, base_url: str):
        self._base_url = base_url

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params or None)

    def post(self, path: str, body: dict | None = None) -> Any:
        return self._request("POST", path, json=body)

    def delete(self, path: str) -> None:
        self._request("DELETE", path, expect_body=False)

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
        expect_body: bool = True,
    ) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        with httpx.Client() as client:
            response = client.request(method, url, params=params, json=json)

        if not response.is_success:
            try:
                err = response.json()["error"]
                code = err.get("code", "ERROR")
                message = err.get("message", response.text)
            except Exception:
                code = "ERROR"
                message = response.text
            raise ApiError(code=code, message=message, status_code=response.status_code)

        if not expect_body:
            return None
        return response.json()
