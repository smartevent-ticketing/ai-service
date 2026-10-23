# v1.2 findings and their implementation status

**Historical source:** `docs/contexts/v1.2/` is immutable. Runtime corrections are additive.

| Audit | Resolution in this base |
|---|---|
| P1 enabled vs gate | All runtime tools disabled; constructor rejects enabled tools with gate != PASS. Requires RUNTIME-READONLY gate too. |
| P1 missing required projected fields | Per-tool `required` in runtime YAML, JSON Schema validation after allowlist projection; negative tests. |
| P1 pagination omitted/false complete | Require PageResponse metadata; return `has_more`, `result_complete`, `pagination_limited`, `capped_by_adapter`. |
| P2 venueName mapping | Use explicit `venue.name -> venueName` only for search. |
| P2 timeout, fixed origin, byte cap | `SafeBackendTransport` enforces all 3 + no redirect + GET only; mocked HTTP tests. |
| P2 seats filter and truncation | Filter AVAILABLE before limit, return `filtered_total`, `returned_count`, `result_complete`. |
| P2 capability matrix | See `RELEASE_GATES.md`. |
| P3 3 historical relative links | Do not alter historical source; use `docs/contexts/v1.2/docs/ai-agent/` within this repo and corrected links in runtime docs. |

**Unimplemented**: private auth delegation, child visibility hardening in Spring Boot, live business GET integrations, approved RAG and deployed SLM. Tests here cover local contracts, not those integrations.

## Source repair addendum — 0.1.1

The v0.1.0 source audit also identified implementation defects beyond the historical v1.2 context findings. Version 0.1.1 repairs them without modifying `docs/contexts/v1.2/`:

- bounded Decimal-based budget parsing and non-500 clarification;
- state-aware budget scope follow-up;
- typed semantic event search criteria;
- strict pagination consistency and global completeness;
- pure inner Clean Architecture layers;
- packaged fail-closed config fallback for wheel startup;
- stronger tool-registry and transport contracts;
- deterministic dataset provenance hashes;
- CI coverage/wheel/Docker smoke gates.

All business tools remain disabled. These repairs do not constitute backend integration approval.

## Source repair addendum — 0.1.2

See [audit closures](REVIEW_LOG.md) for cardinality, task switching, strict domain
inputs, parser bounds, side-effect GET denial, dataset component splits and
cross-platform byte/hash fixes. Transport requests identity encoding and rejects
compressed payloads before iteration, keeping the byte cap independent of HTTP
decompression. Tool deadlines cover the full awaited HTTP operation. Runtime
configs and integration gate statuses are unchanged.

## Immutability addendum — 2026-10-23 (P0)

An uncommitted working-tree edit had added `"synthetic_unreviewed"` to the
`metadata.source` enum in the immutable historical file
`docs/contexts/v1.2/schemas/training_sample.schema.json` (line 1571). Per
`AGENTS.md` §2 and `ADR-001`, `docs/contexts/v1.2/` is immutable historical
evidence and must never be edited in place.

Resolution: the file was restored byte-identical via `git restore` (no
commit of the edit); `scripts/verify_contexts.py` passes (49 files). No
correction content was merged into the historical file. Any future need for
a `synthetic_unreviewed` source label belongs in a new contract version
under `configs/schemas/` with its own review, never as an edit to v1.2.
