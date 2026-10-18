"""Design-time reference contract executor with injected transport; NOT production runtime.

The real FastAPI adapter must have equivalent fail-closed behavior and integration tests.
No network calls are made from this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
import re
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[1]

class ToolDenied(Exception):
    """Safe code only, never attaches raw payload / secrets."""

@dataclass(frozen=True)
class Identity:
    authenticated: bool=False
    roles: tuple[str, ...]=()
    verified_customer: bool=False

class ReadOnlyBusinessToolExecutor:
    def __init__(self, registry=None):
        self.registry=registry or yaml.safe_load((ROOT/'configs/tool_registry.yaml').read_text(encoding='utf8'))
        self.tools={t['name']:t for t in self.registry['tools']}

    def execute(self, tool_name: str, arguments: dict[str, Any], transport: Callable[...,dict], *, identity: Identity=Identity()):
        if not isinstance(tool_name,str) or tool_name not in self.tools:
            raise ToolDenied('UNKNOWN_TOOL')
        tool=self.tools[tool_name]
        if not tool.get('enabled',False):
            raise ToolDenied('TOOL_DISABLED_GATE')
        if tool['method']!='GET' or tool.get('mutation') or not tool['endpoint'].startswith('/api/v1/'):
            raise ToolDenied('BUSINESS_WRITE_OR_UNSAFE_ENDPOINT')
        if re.search(r'(?i)(?:/vnpay/(?:ipn|return)|/(?:refresh|transfer|cancel|create|approve)(?:/|$))',tool['endpoint']):
            raise ToolDenied('SIDE_EFFECT_GET')
        errs=list(Draft202012Validator(tool['arguments_schema'],format_checker=FormatChecker()).iter_errors(arguments))
        if errs: raise ToolDenied('INVALID_ARGUMENTS')
        if tool['principal_scope']=='CUSTOMER_SELF_ONLY':
            if (not identity.authenticated or not identity.verified_customer or
                set(identity.roles)&{'ADMIN','ROLE_ADMIN','SERVICE','ROLE_SERVICE'}):
                raise ToolDenied('CUSTOMER_SELF_ONLY')
        else:
            if tool['credential_policy']!='NO_AUTHORIZATION_HEADER':raise ToolDenied('PUBLIC_AUTH_POLICY')
        args=dict(arguments)
        endpoint=tool['endpoint']
        for key in re.findall(r'\{([^}]+)\}',endpoint):
            value=args.pop(key)
            # All path IDs currently UUID; do not loosen this check without schema revision.
            if not isinstance(value,str) or not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',value):
                raise ToolDenied('INVALID_PATH_ID')
            endpoint=endpoint.replace('{'+key+'}',quote(value,safe=''))
        if '://' in endpoint or '..' in endpoint or '%' in endpoint or '\\' in endpoint:
            raise ToolDenied('UNSAFE_PATH')
        if '?' in endpoint or '#' in endpoint: raise ToolDenied('UNSAFE_PATH')
        # Transport must enforce configured origin, no redirects and no implicit retries.
        response=transport(method='GET',path=endpoint,query=args,credential_mode=tool['credential_policy'],allow_redirects=False)
        if not isinstance(response,dict) or not isinstance(response.get('status'),int):
            raise ToolDenied('INVALID_TRANSPORT_RESPONSE')
        status=response['status']
        if status<200 or status>=300:raise ToolDenied('BACKEND_ERROR_OR_REDIRECT')
        return self.project_response(tool,response.get('json'))

    @staticmethod
    def project_response(tool:dict,raw:Any):
        """Projection happens BEFORE model/JEV/log; only whitelisted scalar fields survive.

        This is a demonstrator; real adapter must validate DTO shape against pinned OpenAPI.
        """
        if not isinstance(raw,dict) or 'data' not in raw:raise ToolDenied('INVALID_API_ENVELOPE')
        payload=raw['data']
        shape=tool['response']['result_shape']
        if shape=='page':
            if not isinstance(payload,dict) or not isinstance(payload.get('content'),list):
                raise ToolDenied('INVALID_PAGINATED_DTO')
            items=payload['content']
        elif shape=='list':
            if not isinstance(payload,list):raise ToolDenied('INVALID_LIST_DTO')
            items=payload
        elif shape=='object':
            if not isinstance(payload,dict):raise ToolDenied('INVALID_OBJECT_DTO')
            items=[payload]
        else:raise ToolDenied('UNKNOWN_SHAPE')
        max_results=tool['max_results']
        if not isinstance(max_results,int) or max_results<1:raise ToolDenied('UNSAFE_LIMIT')
        selected=[]
        condition=tool['response'].get('only_if')
        matches=tool['response'].get('only_items_matching')
        for item in items:
            if not isinstance(item,dict):raise ToolDenied('INVALID_ITEM')
            if condition and any(item.get(k)!=v for k,v in condition.items()):raise ToolDenied('EVENT_NOT_PUBLIC')
            if matches and any(item.get(k)!=v for k,v in matches.items()):continue
            fields=tool['response']['fields']
            projected={k:item[k] for k in fields if k in item and item[k] is not None}
            # never forward nested fields, arbitrary object payloads or backend extension keys.
            if any(isinstance(v,(dict,list)) for v in projected.values()):raise ToolDenied('UNEXPECTED_NESTED_DTO')
            if list(Draft202012Validator(tool['response_schema']).iter_errors(projected)):
                raise ToolDenied('INVALID_PROJECTED_DTO')
            selected.append(projected)
            if len(selected)==max_results:break
        return {'tool':tool['name'],'data':selected[0] if shape=='object' and selected else (selected if shape!='object' else {}),'untrusted_content':True,'truncated':len(items)>max_results}
