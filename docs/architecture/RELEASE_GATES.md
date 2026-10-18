# Release and Capability Matrix (source: v1.2 implementation gates + final audit)

| Capability | Bootstrap state | Evidence required before enable |
|---|---|---|
| Rule-based Vietnamese parsing | AVAILABLE AS DEMO | schema and E2E interaction tests |
| Stateless AI conversation state | AVAILABLE AS DEMO | abuse/rate controls before public exposure |
| Public event search/detail | DISABLED | anonymous visibility tests + projection + runtime READ_ONLY E2E |
| Public event child: areas, types, phases, seats, inventory | DISABLED | service-side PUBLISHED parent guard, ownership/foreign ID tests, seat filtering/pagination |
| Private order/payment/reservation/tickets/refund review | DISABLED | verified BFF identity, CUSTOMER_SELF_ONLY, cross-user negative tests, QR projection |
| Ticket optimizer | PURE FUNCTION | live complete fresh inventory/seat snapshot before user recommendation |
| Approved policy RAG | NOT IMPLEMENTED | signed source manifests, effective dates, retrieval faithfulness tests |
| Fine-tuned Qwen3-1.7B QLoRA | NOT TRAINED | dataset manifest, splits, GPU run, baseline comparison, model card |
| JEV decision evaluator | NOT INTEGRATED | A/B calibration/latency accuracy evidence; fallback must pass |
| Production release | BLOCKED | live zero-business-write trace, DB snapshot, security/perf tests, backend/BFF integrations |

`SPEC_TEST_ONLY` is not `PASS`. Never change gate status through environment overrides or model output.
