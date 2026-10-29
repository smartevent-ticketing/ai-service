# Chatbot v2 evaluation candidates

100 cases: 30 searches, 25 turns in grouped dialogues, 25 policy/guide questions, 20 negative/error/boundary requests. Reference clock: 2026-10-30 in Asia/Ho_Chi_Minh. Groups never cross the deterministic dev/test split. SHA256 is recorded in chatbot_v2_manifest.json.

These are specification seeds, not training data or completed live evaluation. Independently review and lock expected event IDs, price/date boundaries, sources/claims and error codes against an isolated PostgreSQL fixture and approved corpus before acceptance. Do not tune prompts on the test split. The fixture's policy/source approval cannot be inferred from these questions.

Keep counts of pass/fail/blocked and exact model/provider/index/config versions. A disabled tool or mock response is not a passing backend integration case. Global semantic accuracy does not compensate for a failed public/private, price boundary, zero-write or unsupported-claim case.
