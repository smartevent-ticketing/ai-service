from pathlib import Path
import yaml,json
from jsonschema import Draft202012Validator
R=Path(__file__).resolve().parents[1]
reg=yaml.safe_load((R/'configs/tool_registry.yaml').read_text(encoding='utf8'))
policy=yaml.safe_load((R/'configs/assistant_policy.yaml').read_text(encoding='utf8'))

def test_contract_typed_and_denied_by_default():
 assert reg['business_access']=='READ_ONLY'
 assert len(reg['tools'])==14
 for t in reg['tools']:
  assert t['method']=='GET' and t['mutation'] is False
  assert t['response']['projection']=='ALLOWLIST' and t['response']['deny_unlisted_fields'] is True
  assert t['response']['fields']
  assert t['arguments_schema']['additionalProperties'] is False
  Draft202012Validator.check_schema(t['arguments_schema']);Draft202012Validator.check_schema(t['response_schema'])
  assert t['timeout_ms']<=3000 and t['follow_redirects'] is False
  assert 'qrCodeBase64' not in t['response']['fields']
  if t['access']=='authenticated':
   assert t['principal_scope']=='CUSTOMER_SELF_ONLY' and t['enabled'] is False
  if t.get('requires_visibility_audit'):assert t['enabled'] is False
 assert policy['data_security']['deny_raw_payload_to_any_model']

def test_public_paths_only():
 for t in reg['tools']:
  if t['enabled']:assert t['name'] in ('search_events','get_event_details')

def test_no_sensitive_fields_anywhere_in_projection():
 forbidden={'qrCodeBase64','ticketCode','paymentUrl','accessToken','tokenHash','userId','currentOwnerUserId','originalBuyerUserId','reason','evidenceReference','customerNote'}
 for t in reg['tools']:assert not forbidden.intersection(t['response']['fields'])
