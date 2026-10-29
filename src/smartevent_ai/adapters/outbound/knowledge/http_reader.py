"""Fixed-origin, bounded GET-only knowledge-service adapter; no database access."""

import json
from urllib.parse import urlsplit
import httpx
from smartevent_ai.domain.knowledge import Citation, PolicyAnswer
from smartevent_ai.domain.errors import BackendUnavailable


class HttpPolicyReader:
    answer_mode = "remote_extractive"

    def __init__(self, origin: str, token: str):
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or len(token) < 32
        ):
            raise ValueError("Knowledge service needs a fixed origin and a server-held token")
        self._origin, self._token = origin.rstrip("/"), token
        self._status = "not_probed"

    def status(self) -> str:
        return self._status

    async def answer(self, query: str) -> PolicyAnswer:
        try:
            async with httpx.AsyncClient(
                base_url=self._origin, follow_redirects=False, trust_env=False, timeout=8.0
            ) as client:
                async with client.stream(
                    "GET",
                    "/v1/policy",
                    params={"query": query},
                    headers={
                        "Authorization": "Bearer " + self._token,
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if (
                        response.status_code != 200
                        or response.headers.get("content-type", "").split(";")[0]
                        != "application/json"
                    ):
                        raise ValueError("Unexpected knowledge response")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("Compressed knowledge payload denied")
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > 65536:
                            raise ValueError("Knowledge response too large")
            data = json.loads(raw)
            if (
                not isinstance(data, dict)
                or set(data) - {"answer", "citations", "mode"}
                or not isinstance(data.get("answer"), str)
                or len(data["answer"]) > 6000
                or not isinstance(data.get("citations"), list)
                or len(data["citations"]) > 5
            ):
                raise ValueError("Invalid policy contract")
            citations = []
            for row in data["citations"]:
                if not isinstance(row, dict) or set(row) != {
                    "source_id",
                    "version",
                    "title",
                    "canonical_uri",
                    "chunk_id",
                    "heading_path",
                    "start",
                    "end",
                }:
                    raise ValueError("Invalid citation contract")
                if (
                    not all(
                        isinstance(row[k], str) and 0 < len(row[k]) <= 2048
                        for k in ("source_id", "version", "title", "canonical_uri", "chunk_id")
                    )
                    or not isinstance(row["heading_path"], list)
                    or not all(isinstance(x, str) for x in row["heading_path"])
                    or type(row["start"]) is not int
                    or type(row["end"]) is not int
                    or not 0 <= row["start"] < row["end"]
                ):
                    raise ValueError("Invalid citation values")
                row["heading_path"] = tuple(row["heading_path"])
                citations.append(Citation(**row))
            self._status = "last_read_ok"
            return PolicyAnswer(data["answer"], tuple(citations), "remote_extractive")
        except (httpx.HTTPError, ValueError, TypeError, KeyError, RecursionError) as exc:
            self._status = "unavailable"
            raise BackendUnavailable("Knowledge service unavailable") from exc
