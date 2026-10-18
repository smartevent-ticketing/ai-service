from pathlib import Path
import yaml,json,pytest
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parents[1]
G=yaml.safe_load((ROOT/'configs/implementation_gates.yaml').read_text(encoding='utf8'))
P=yaml.safe_load((ROOT/'configs/rag_corpus_policy.yaml').read_text(encoding='utf8'))
C=json.loads((ROOT/'schemas/rag_corpus_manifest.schema.json').read_text(encoding='utf8'))
V=Draft202012Validator(C,format_checker=FormatChecker())

def test_rag_gate_closed_without_corpus():
 assert G['gates']['RAG-APPROVED-CORPUS']['status']=='BLOCKED'
 assert P['publication_gate']['must_be_approved']
 assert P['retrieval']['default_deny_unknown_status']
 assert 'staff_internal' not in P['retrieval']['audience_for_authenticated_customer']

def test_manifest_schema_rejects_missing_source():
 Draft202012Validator.check_schema(C)
 assert list(V.iter_errors({'status':'approved'}))

def test_versioned_manifest_fields():
 m={'source_id':'POLICY-001','canonical_uri':'https://example.org/policy','owner_role':'product_policy_owner','reviewer_role':'legal_reviewer','status':'approved','version':'1.0','audience':'customer_public','locale':'vi-VN','content_sha256':'a'*64,'last_reviewed_at':'2026-10-18T10:00:00Z','approved_at':'2026-10-18T10:00:00Z','effective_from':'2026-10-18T00:00:00Z'}
 assert not list(V.iter_errors(m))
 m['audience']='secret_stuff'
 assert list(V.iter_errors(m))
