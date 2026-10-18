#!/usr/bin/env python3
"""Static lint for read-only business tool policy. Run from any working dir."""
from pathlib import Path
import yaml,json
ROOT=Path(__file__).resolve().parents[1]
tools=yaml.safe_load((ROOT/'configs/tool_registry.yaml').read_text(encoding='utf-8'))
policy=yaml.safe_load((ROOT/'configs/assistant_policy.yaml').read_text(encoding='utf-8'))
assert tools['enforcement']['deny_mutations'] and policy['execution']['deny_all_business_mutations']
assert all(t['method']=='GET' and not t['mutation'] for t in tools['tools'])
assert not any(t['name'] in {'create_reservation','request_refund_review'} for t in tools['tools'])
print('PASS: business tool registry is GET-only / READ_ONLY; this is static config validation, not runtime proof')
