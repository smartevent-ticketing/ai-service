# ADR-004 — Chatbot v2 contracts and isolated knowledge reader

Status: IMPLEMENTED IN SOURCE; live integration/evaluation remains pending.

## Contract

Event search accepts optional startFrom (inclusive), startBefore (exclusive), maxPrice (decimal string at gateway) and priceComparison LT/LTE. Times require timezone. Vietnamese relative months use an injected clock and UTC+07:00 calendar; omitted year means next occurrence of the month, including the current month. Ticket budgets cover face value only; final order fees are not asserted. Total budget is converted using the requested positive quantity; no inventory sufficiency is promised.

Backend filters price with correlated EXISTS and positive inventory snapshot before pagination. Repeatable-read search fetches deterministic price evidence in one batch. Old event response fields remain; new evidence fields are nullable. Public child reads require a published parent and active visible phase, while verified event owner/admin retains draft access.

State adds optional start_from/start_before, price_comparison, faq_topic. HTTP DTO rejects unknown fields. EventCard is server-built from allowlisted projection; routes are /events/{validated-slug}. Deploy backend then AI then web; roll web back before AI when dropping fields.

PUBLIC-SEARCH controls enabling search; RUNTIME-READONLY controls runtime availability. Price arguments additionally require PUBLISHED-CHILD. Every shipped business tool remains disabled. No PASS state is created from mock tests.

## Model and verification

Reuse LanguageUnderstanding sync parse in a worker thread, OllamaNLU and PeftTransformerNLU; one strict output parser handles SET/REMOVE/CLEAR. Invalid structured output requests clarification and cannot call tools. Float/bool quantities are rejected. Network fallback is marked fallback. No real model weights were run during implementation.

Until an independently evaluated Vietnamese entailment checker is approved, generated policy answers are accepted only when equivalent to the entire evidence extract. Other candidates are discarded for extractive fallback, with source authority rechecked after generation. This conservatively closes unsupported-claim acceptance but does not claim natural generative RAG acceptance. A learned checker and held-out error evaluation remain release work.

## Knowledge boundary

SafeBackendTransport remains the sole business transport with one fixed origin. The separate HttpPolicyReader has a fixed knowledge origin/path, bounded GET response and a server-held token. It never receives SQL/business credentials. The optional knowledge service belongs to infra/services/knowledge, reuses existing artifact/corpus validation and embedding modules, and owns knowledge-only PostgreSQL access. The database has a private data network, separate reader/ingester roles, no host port and no business volume.

Offline ingest validates approved public artifacts, pins embeddings, writes a new immutable release and switches the active pointer in one transaction. Reader trust anchors are deployment-pinned. Runtime has SELECT privileges only. BM25 remains default; vector/hybrid selection requires a pinned matching evaluation record with calibrated abstention threshold. No approximate index is enabled.

## Acceptance state

100 grouped evaluation seeds are checked in with hash and candidate labels. They require independent event/source expectations before acceptance; no model/index/corpus approval is implied. PostgreSQL integration, reader zero-write, ONNX model selection, hybrid comparison, model inference and browser E2E must be run on an environment supporting Docker/loopback. Do not call this production-ready from source/unit checks.
