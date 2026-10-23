"""Fail-closed read-only gateway for reviewed SmartEvent business tools."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from smartevent_ai.adapters.outbound.route_policy import is_side_effect_route
from smartevent_ai.domain.errors import BackendUnavailable, ContractViolation, ToolUnavailable

_ROUTE_TEMPLATE = re.compile(
    r"^/api/v1/(?:[A-Za-z0-9_.-]+|\{[A-Za-z][A-Za-z0-9_]*\})"
    r"(?:/(?:[A-Za-z0-9_.-]+|\{[A-Za-z][A-Za-z0-9_]*\}))*$"
)
_ROUTE_CONCRETE = re.compile(r"^/api/v1/[A-Za-z0-9_./-]+$")

_PUBLISHED_EVENT_TOOLS = ("search_events", "get_event_details")


def _require_published(tool_name: str, status: object) -> None:
    if tool_name in _PUBLISHED_EVENT_TOOLS and status != "PUBLISHED":
        raise ContractViolation("Unpublished event must never reach model")


class ReadTransport(Protocol):
    async def get(
        self,
        path: str,
        *,
        query: dict[str, Any],
        max_bytes: int,
        timeout_ms: int,
    ) -> dict[str, Any]: ...


class ReadOnlyToolGateway:
    def __init__(self, registry_path: Path, gates_path: Path, transport: ReadTransport):
        registry = self._load_yaml(registry_path, "tool registry")
        gates_doc = self._load_yaml(gates_path, "implementation gates")
        gates = gates_doc.get("gates")
        if not isinstance(gates, dict):
            raise ContractViolation("Gate document must contain an object named 'gates'")
        self.gates: dict[str, Any] = gates

        tools = registry.get("tools")
        if not isinstance(tools, list) or not tools:
            raise ContractViolation("Tool registry must contain a non-empty tools list")

        enforcement = registry.get("enforcement")
        if not isinstance(enforcement, dict):
            raise ContractViolation("Missing read-only enforcement section")
        self._max_response_bytes = self._validate_global_enforcement(registry, enforcement)

        self.tools: dict[str, dict[str, Any]] = {}
        for raw_tool in tools:
            if not isinstance(raw_tool, dict):
                raise ContractViolation("Each tool definition must be an object")
            self._validate_tool(raw_tool)
            name = raw_tool["name"]
            if name in self.tools:
                raise ContractViolation("Duplicate tool names")
            self.tools[name] = raw_tool

        self.transport = transport

    @staticmethod
    def _load_yaml(path: Path, label: str) -> dict[str, Any]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ContractViolation(f"Unable to load {label}") from exc
        if not isinstance(data, dict):
            raise ContractViolation(f"{label} must be a YAML object")
        return data

    @staticmethod
    def _validate_global_enforcement(registry: dict[str, Any], enforcement: dict[str, Any]) -> int:
        if registry.get("business_access") != "READ_ONLY":
            raise ContractViolation("Registry business access must be READ_ONLY")
        if enforcement.get("allowed_methods") != ["GET"]:
            raise ContractViolation("Only GET may be globally allowed")
        if enforcement.get("default") != "deny":
            raise ContractViolation("Global tool policy must default-deny")
        if enforcement.get("response_projection_mode") != "allowlist_only":
            raise ContractViolation("Global response projection must be allowlist-only")
        required_true = (
            "deny_mutations",
            "deny_unknown_tools",
            "deny_side_effect_get",
            "deny_redirects",
            "no_arbitrary_hosts_or_urls",
            "deny_encoded_path_variants",
            "deny_raw_responses_in_model_context",
            "deny_request_retries_by_default",
            "private_tools_fail_closed_until_auth_proven",
        )
        if any(enforcement.get(key) is not True for key in required_true):
            raise ContractViolation("Read-only enforcement flags must fail closed")
        max_bytes = enforcement.get("max_response_bytes")
        if type(max_bytes) is not int or not 1_024 <= max_bytes <= 2_097_152:
            raise ContractViolation("Invalid global response byte cap")
        return max_bytes

    def _validate_tool(self, tool: dict[str, Any]) -> None:
        required = (
            "name",
            "access",
            "method",
            "endpoint",
            "mutation",
            "enabled",
            "arguments_schema",
            "response_schema",
            "response",
            "timeout_ms",
            "max_results",
            "follow_redirects",
            "retry_policy",
            "gate_id",
        )
        if any(key not in tool for key in required):
            raise ContractViolation("Incomplete tool definition")
        if not isinstance(tool["name"], str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{1,63}", tool["name"]
        ):
            raise ContractViolation("Invalid tool name")
        if re.match(
            r"^(create|update|delete|cancel|confirm|reserve|hold|submit|approve|"
            r"transfer|refresh|send|request)_",
            tool["name"],
        ):
            raise ContractViolation("Business mutation aliases are forbidden")
        if tool["method"] != "GET" or tool["mutation"] is not False:
            raise ContractViolation("Mutation capability is forbidden")
        if tool["access"] not in ("public", "authenticated"):
            raise ContractViolation("Unknown tool access mode")
        if tool.get("access") != "public" and tool.get("enabled"):
            raise ContractViolation("Private tools cannot be enabled without verified auth adapter")
        if type(tool["enabled"]) is not bool:
            raise ContractViolation("Tool enabled must be boolean")
        if tool["gate_id"] not in self.gates:
            raise ContractViolation("Every tool must have a known gate")
        if tool["enabled"] and not self._gate_pass(tool["gate_id"]):
            raise ContractViolation("Enabled tool has gate != PASS")
        if tool["follow_redirects"] is not False or tool["retry_policy"] != "NONE":
            raise ContractViolation("Tool transport must deny redirects and retries")
        timeout = tool["timeout_ms"]
        if type(timeout) is not int or not 100 <= timeout <= 10_000:
            raise ContractViolation("Tool timeout outside approved bounds")
        max_results = tool["max_results"]
        if type(max_results) is not int or not 1 <= max_results <= 1_000:
            raise ContractViolation("Tool result cap outside approved bounds")
        endpoint = tool["endpoint"]
        if (
            not isinstance(endpoint, str)
            or not _ROUTE_TEMPLATE.fullmatch(endpoint)
            or is_side_effect_route(endpoint)
        ):
            raise ContractViolation("Unsafe tool endpoint template")

        response = tool["response"]
        if not isinstance(response, dict):
            raise ContractViolation("Tool response contract must be an object")
        if response.get("result_shape") not in ("object", "list", "page"):
            raise ContractViolation("Unsupported response result shape")
        fields = response.get("fields")
        if (
            not isinstance(fields, list)
            or not fields
            or any(not isinstance(field, str) or not field for field in fields)
            or len(set(fields)) != len(fields)
        ):
            raise ContractViolation("Response fields must be a unique non-empty string allowlist")
        mappings = response.get("field_mappings", {})
        if not isinstance(mappings, dict) or any(
            alias not in fields or not isinstance(path, str) or not path
            for alias, path in mappings.items()
        ):
            raise ContractViolation("Invalid response field mappings")
        if (
            response.get("projection") != "ALLOWLIST"
            or response.get("deny_unlisted_fields") is not True
        ):
            raise ContractViolation("Response projection must be strict allowlist")
        safety = tool.get("safety")
        if (
            not isinstance(safety, dict)
            or safety.get("raw_response_to_model") is not False
            or safety.get("validated_origin_required") is not True
        ):
            raise ContractViolation(
                "Tool safety policy must deny raw data and require fixed origin"
            )
        if tool.get("requires_runtime_gate") is not True:
            raise ContractViolation("Every business tool must require runtime gate evidence")

        for key in ("arguments_schema", "response_schema"):
            schema = tool[key]
            if not isinstance(schema, dict) or schema.get("type") != "object":
                raise ContractViolation("Tool schemas must describe objects")
            if schema.get("additionalProperties") is not False:
                raise ContractViolation("Tool schemas must deny unknown properties")
        try:
            Draft202012Validator.check_schema(tool["arguments_schema"])
            Draft202012Validator.check_schema(tool["response_schema"])
        except SchemaError as exc:
            raise ContractViolation("Invalid JSON Schema in tool contract") from exc

    def _gate_pass(self, key: str) -> bool:
        value = self.gates.get(key)
        return isinstance(value, dict) and value.get("status") == "PASS"

    def available_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                t["name"]
                for t in self.tools.values()
                if t["enabled"]
                and t["access"] == "public"
                and self._gate_pass(t["gate_id"])
                and self._gate_pass("RUNTIME-READONLY")
            )
        )

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolUnavailable("Unknown tool")
        if (
            not tool["enabled"]
            or tool["method"] != "GET"
            or tool["access"] != "public"
            or not self._gate_pass(tool["gate_id"])
            or not self._gate_pass("RUNTIME-READONLY")
        ):
            raise ToolUnavailable("Tool not approved for runtime")

        errors = list(
            Draft202012Validator(
                tool["arguments_schema"], format_checker=FormatChecker()
            ).iter_errors(arguments)
        )
        if errors:
            raise ContractViolation("Invalid tool arguments")

        route, query = self._resolve_route(tool["endpoint"], arguments)
        envelope = await self.transport.get(
            route,
            query=query,
            max_bytes=self._max_response_bytes,
            timeout_ms=int(tool["timeout_ms"]),
        )
        if envelope.get("success") is not True:
            raise BackendUnavailable("Unsuccessful or malformed backend envelope")
        if "data" not in envelope:
            raise ContractViolation("Missing backend data")
        if tool["response"]["result_shape"] == "page" and isinstance(envelope["data"], dict):
            for key in ("page", "size"):
                if key in arguments and envelope["data"].get(key) != arguments[key]:
                    raise ContractViolation("Backend pagination does not match request")
        return self.project(tool, envelope["data"])

    @staticmethod
    def _resolve_route(template: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        route = template
        query = arguments.copy()
        for param in re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", route):
            if param not in query:
                raise ContractViolation("Missing route parameter")
            try:
                safe_value = str(UUID(str(query.pop(param))))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ContractViolation("Invalid UUID in route") from exc
            route = route.replace("{" + param + "}", safe_value)
        if (
            ".." in route
            or "%" in route
            or "{" in route
            or "}" in route
            or is_side_effect_route(route)
            or not _ROUTE_CONCRETE.fullmatch(route)
        ):
            raise ContractViolation("Unsafe concrete route")
        return route, query

    @staticmethod
    def _project_row(tool: dict[str, Any], row: Any) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise ContractViolation("Response row must be an object")
        projected = {
            field: row[field]
            for field in tool["response"]["fields"]
            if field in row and row[field] is not None
        }
        for alias, path in tool["response"].get("field_mappings", {}).items():
            value: Any = row
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if value is not None:
                projected[alias] = value

        _require_published(tool["name"], row.get("status"))

        errors = list(
            Draft202012Validator(
                tool["response_schema"], format_checker=FormatChecker()
            ).iter_errors(projected)
        )
        if errors:
            raise ContractViolation("Missing or invalid required response fields")
        return projected

    @staticmethod
    def _validate_page(data: dict[str, Any]) -> tuple[list[Any], int, int, int, int, bool]:
        keys = ("content", "page", "size", "totalElements", "totalPages", "last")
        if any(key not in data for key in keys):
            raise ContractViolation("Incomplete PageResponse")
        entries = data["content"]
        page = data["page"]
        size = data["size"]
        total = data["totalElements"]
        pages = data["totalPages"]
        last = data["last"]
        if (
            not isinstance(entries, list)
            or type(page) is not int
            or page < 0
            or type(size) is not int
            or size < 1
            or type(total) is not int
            or total < 0
            or type(pages) is not int
            or pages < 0
            or type(last) is not bool
            or len(entries) > size
        ):
            raise ContractViolation("Invalid pagination metadata types or bounds")

        expected_pages = (total + size - 1) // size
        if pages != expected_pages:
            raise ContractViolation("totalPages contradicts totalElements and size")
        if total == 0:
            if entries or pages != 0 or last is not True:
                raise ContractViolation("Empty page metadata is inconsistent")
            return entries, page, size, total, pages, last

        if page < pages:
            if len(entries) != min(size, total - page * size):
                raise ContractViolation("Page content contradicts totalElements")
            expected_last = page == pages - 1
            if last is not expected_last:
                raise ContractViolation("last contradicts page and totalPages")
        else:
            # Spring may return a requested page beyond the end, but it must be empty and terminal.
            if entries or last is not True:
                raise ContractViolation("Out-of-range page must be empty and terminal")
        return entries, page, size, total, pages, last

    def project(self, tool: dict[str, Any], data: Any) -> dict[str, Any]:
        kind = tool["response"]["result_shape"]
        limit = int(tool["max_results"])
        if kind == "object":
            projected = self._project_row(tool, data)
            return {"data": projected, "result_complete": True}

        page = size = total = pages = 0
        last = True
        if kind == "page":
            if not isinstance(data, dict):
                raise ContractViolation("Page response must be object")
            entries, page, size, total, pages, last = self._validate_page(data)
        elif kind == "list":
            if not isinstance(data, list):
                raise ContractViolation("List response must be list")
            entries = data
        else:
            raise ContractViolation("Unknown tool response shape")

        source_count = len(entries)
        filtered = [
            item
            for item in entries
            if not (
                tool["name"] == "get_available_seats"
                and isinstance(item, dict)
                and item.get("status") != "AVAILABLE"
            )
        ]
        if tool["name"] == "search_events":
            for item in filtered:
                _require_published(
                    tool["name"], item.get("status") if isinstance(item, dict) else None
                )

        rows = [self._project_row(tool, item) for item in filtered[:limit]]
        capped = len(filtered) > limit
        has_more = (page + 1 < pages) if kind == "page" else False
        has_previous = page > 0 and total > 0 if kind == "page" else False
        result: dict[str, Any] = {
            "data": rows,
            "capped_by_adapter": capped,
            "has_more": has_more,
            "has_previous": has_previous,
            "returned_count": len(rows),
            "source_count": source_count,
            "filtered_total": len(filtered),
            "filtered_out_count": source_count - len(filtered),
            "result_complete": not capped and not has_more and not has_previous,
        }
        if kind == "page":
            result["pagination"] = {
                "page": page,
                "size": size,
                "totalElements": total,
                "totalPages": pages,
                "last": last,
            }
            page_maximum = (
                tool.get("arguments_schema", {})
                .get("properties", {})
                .get("page", {})
                .get("maximum")
            )
            result["pagination_limited"] = (
                has_more and type(page_maximum) is int and page >= page_maximum
            )
        else:
            result["pagination_limited"] = False
        return result
