from pathlib import Path
import copy,json,yaml,pytest
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parents[1]
SC=json.loads((ROOT/'schemas/training_sample.schema.json').read_text(encoding='utf8'))
V=Draft202012Validator(SC,format_checker=FormatChecker())
ONT=yaml.safe_load((ROOT/'configs/dialogue_ontology.yaml').read_text(encoding='utf8'))

def good():
 return {'sample_id':'SE-DST-001','dataset_contract':'1.2','dataset_version':'v0.1.0','language':'vi','task':'dialogue_state_update','previous_state':{'city':'Hà Nội','quantity':2,'budget_amount':1200000,'budget_scope':'TOTAL','budget_currency':'VND'},'user_message':'Đổi thành ba vé','expected':{'primary_intent':'TICKET_RECOMMEND','secondary_intents':[],'entities':{'quantity':3},'state_delta':[{'operation':'SET','slot':'quantity','value':3}],'proposed_action':'GET_TICKET_OPTIONS'},'metadata':{'source':'synthetic_reviewed','scenario':'quantity_update','scenario_family':'correction_family_1','dialogue_group':'D001','difficulty':'medium'}}

def test_good_sample():assert not list(V.iter_errors(good()))

def test_schema_ontology_agree():
 assert set(SC['properties']['expected']['properties']['primary_intent']['enum'])==set(i for group in ONT['intents'].values() for i in group)
 assert set(SC['properties']['expected']['properties']['proposed_action']['enum'])==set(ONT['proposed_actions'])
 assert set(SC['properties']['previous_state']['anyOf'][0]['properties'])==set(ONT['slots'])

@pytest.mark.parametrize('modify',[
 lambda x:x['expected'].update({'secondary_intents':['HACKED']}),
 lambda x:x['expected']['entities'].update({'__toolcall__':{'method':'POST'}}),
 lambda x:x['previous_state'].update({'payment_status':'PAID'}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'SET','slot':'payment_status','value':'SUCCESS'}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'SET','slot':'quantity','value':{'hack':1}}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'SWITCH_TASK','slot':'active_intent'}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'REMOVE','slot':'quantity','value':3}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'CLEAR','slot':'quantity'}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'REFER','slot':'order_id','value':'x'}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'SET','slot':'quantity','value':0}),
 lambda x:x['expected']['state_delta'].__setitem__(0,{'operation':'SET','slot':'budget_amount','value':-100}),
 lambda x:x['expected'].update({'proposed_action':'CREATE_RESERVATION'}),
 lambda x:x['expected'].update({'entities':{'budget':{'amount':1000000}}}),
 lambda x:x.pop('dataset_contract'),
 lambda x:x['metadata'].pop('scenario_family'),
])
def test_negative_contract(modify):
 x=good();modify(x);assert list(V.iter_errors(x)),str(x)

def test_valid_switch_task_and_refer():
 x=good();x['expected']['state_delta']=[{'operation':'SWITCH_TASK','slot':'active_intent','value':'ORDER_STATUS'},{'operation':'REFER','slot':'selected_candidate_id','value':'candidate-2'}]
 assert not list(V.iter_errors(x))
