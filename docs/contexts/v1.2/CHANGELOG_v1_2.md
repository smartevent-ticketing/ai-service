# CHANGELOG — v1.2 READ_ONLY Contract Hardening

**18/10/2026 | source:** v1.1 pack + audit `SmartEvent_READ_ONLY_v1_1_kiem_toan_truoc_chot.md`.

## Fixed at documentation/config/test-reference level

- P1-01: DTO field allowlist projection, banned QR/owner/PII/payment URL in model/log; get_my_tickets disabled until runtime privacy gate.
- P1-02: private tools disabled until verified `CUSTOMER_SELF_ONLY` BFF/backend integration; reject ADMIN bypass.
- P1-03: typed arguments per tool, response contract, explicit allowed output fields, timeout/limits, redirects denied.
- P1-04: reference executor with injected transport and negative unit tests (unknown GET, side-effect GET, mutation, encoded path, redirect, raw QR). Not proof of integration security.
- P1-05: schema oneOf typed deltas, enum secondary intents, strict previous state/entities, dataset_contract, negative tests.
- P1-06: five child GETs remain disabled by design; published-only backend tests mandatory before activation.
- P2-01..05: auth forwarding, seat status, RAG owner/manifest, budget flat slots, pinned repo snapshot + evaluation manifest documented.

## Explicitly NOT completed

FastAPI AI Service runtime, backend published-only patches, BFF token delegation, authenticated customer self-only integration, staging security tests, RAG approved corpus, model training/benchmark, load testing. **No claim of merge/production readiness.**

## Quality gates

1. Static + reference harness tests PASS.
2. Backend auth/published/ownership + API contract tests MUST run before enabling respective tools.
3. Live end-to-end zero-write + no-secret-in-model tests MUST run before product release.
