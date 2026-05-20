"""Low-level httpx wrapper with uniform error handling."""

import httpx

from amygda_ops_risk_score.exceptions import APIError

# Sentinel: distinguishes "caller passed None (no timeout)" from "caller passed nothing
# (fall back to client-level default)". httpx treats an explicit None as "no timeout",
# so we must NOT forward None when the caller omitted the argument.
_UNSET = object()


class HTTPClient:
    """Thin synchronous httpx client used by the SDK."""

    def __init__(self, base_url: str, timeout: float):
        self._timeout = timeout
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------ #

    def _resolve(self, timeout) -> float:
        """Return client-level default when caller omitted the timeout argument."""
        return self._timeout if timeout is _UNSET else timeout

    def get(self, path: str, timeout=_UNSET, **kwargs) -> dict:
        r = self._client.get(path, timeout=self._resolve(timeout), **kwargs)
        return self._parse(r)

    def get_raw(self, path: str, timeout=_UNSET, **kwargs) -> bytes:
        """GET a binary/streaming response (CSV, zip, parquet). Returns raw bytes."""
        r = self._client.get(path, timeout=self._resolve(timeout), **kwargs)
        if not r.is_success:
            try:
                body = r.json()
            except Exception:
                body = {"message": r.text}
            raise APIError(
                status_code=r.status_code,
                error_code=body.get("error", "unknown_error"),
                message=body.get("message", r.text[:200]),
                body=body,
            )
        return r.content

    def post(self, path: str, timeout=_UNSET, **kwargs) -> dict:
        r = self._client.post(path, timeout=self._resolve(timeout), **kwargs)
        return self._parse(r)

    def delete(self, path: str, timeout=_UNSET, **kwargs) -> dict:
        r = self._client.delete(path, timeout=self._resolve(timeout), **kwargs)
        return self._parse(r)

    # ------------------------------------------------------------------ #

    def _parse(self, response: httpx.Response) -> dict:
        try:
            body = response.json()
        except Exception:
            body = {"message": response.text}

        if response.is_success:
            return body

        raise APIError(
            status_code=response.status_code,
            error_code=body.get("error", "unknown_error"),
            message=body.get("message", response.text[:200]),
            body=body,
        )
