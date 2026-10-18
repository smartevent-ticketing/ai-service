"""Shared denial of known side-effect routes, independent of registry flags."""

import re

_SIDE_EFFECT_SEGMENT = re.compile(
    r"(?:^|/)(?:ipn|return|callback|success|cancel|create|update|delete|approve|"
    r"confirm|refresh|transfer|reserve|hold|submit|send)(?:/|$)",
    re.IGNORECASE,
)


def is_side_effect_route(path: str) -> bool:
    return _SIDE_EFFECT_SEGMENT.search(path) is not None
