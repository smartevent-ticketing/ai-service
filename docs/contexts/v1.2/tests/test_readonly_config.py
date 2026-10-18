from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]

def read_yaml(path):
    return yaml.safe_load((ROOT/path).read_text(encoding='utf-8'))

def test_registry_is_get_only():
    reg=read_yaml('configs/tool_registry.yaml')
    assert reg['business_access']=='READ_ONLY'
    assert reg['enforcement']['deny_mutations'] is True
    assert reg['enforcement']['allowed_methods']==['GET']
    for tool in reg['tools']:
        assert tool['method']=='GET'
        assert tool['mutation'] is False
        assert tool['endpoint'].startswith('/api/v1/')
        assert tool['response']['read_only'] is True
    names={tool['name'] for tool in reg['tools']}
    forbidden={'create_reservation','request_refund_review','create_order','cancel_reservation','create_payment_url','transfer_ticket'}
    assert not names.intersection(forbidden)

def test_policy_fails_closed():
    p=read_yaml('configs/assistant_policy.yaml')
    assert p['assistant']['business_access']=='READ_ONLY'
    assert p['execution']['default_permission']=='deny'
    assert p['execution']['deny_all_business_mutations']
    assert p['execution']['allowed_business_methods']==['GET']
    assert p['dialogue']['state_delta_scope']=='AI_CONVERSATION_ONLY'
    assert not p['transactions']['assistant_may_initiate_transactions']

def test_ontology_schema_actions_agree():
    o=read_yaml('configs/dialogue_ontology.yaml')
    schema=json.loads((ROOT/'schemas/training_sample.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    actions=schema['properties']['expected']['properties']['proposed_action']['enum']
    assert set(actions)==set(o['proposed_actions'])
    assert 'CREATE_REFUND_REVIEW' not in actions
    assert 'CREATE_RESERVATION' not in actions
    sample={'sample_id':'SE-RD-001','dataset_contract':'1.2','dataset_version':'v0.1.0','language':'vi','task':'action_selection','previous_state':None,'user_message':'Giữ giúp tôi hai vé','expected':{'primary_intent':'BOOKING_GUIDANCE','state_delta':[],'proposed_action':'NAVIGATE_TO_BOOKING'},'metadata':{'source':'human_written','scenario':'booking_request_denied','dialogue_group':'G001','scenario_family':'booking_access'}}
    v=Draft202012Validator(schema)
    assert not list(v.iter_errors(sample))
    invalid=json.loads(json.dumps(sample))
    invalid['expected']['proposed_action']='CREATE_RESERVATION'
    assert list(v.iter_errors(invalid))
