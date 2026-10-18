# Integration backlog and ownership

These are unimplemented product/release gates, not approved runtime permissions.
Owner roles below identify the responsible discipline; a named assignee and
linked implementation PR must be recorded when work starts. No live tool may be
enabled by this document, environment variables or unit-test success.

| ID | Work | Responsible role | State / acceptance evidence |
|---|---|---|---|
| AI-001 | Public/child reads | Backend + AI integration maintainers | BLOCKED: anonymous PUBLISHED guards, parent/area membership and pinned live contracts |
| AI-002 | Customer-self identity | BFF + security maintainers | BLOCKED: verified delegation, no admin inheritance, A/B/Admin negatives |
| AI-003 | Runtime zero-write | Security + QA maintainers | BLOCKED: network trace and unchanged business DB snapshots |
| AI-004 | Live optimizer | Recommendation maintainer | BLOCKED: quotas, valid seats, complete timestamped snapshots, TTL/revalidation and hard-constraint golden cases |
| AI-005 | Full dialogue ontology | Dialogue maintainer | NOT_IMPLEMENTED: candidate references, exclusions/ADD, date parsing and full task/slot coverage; never guess unseen candidates |
| AI-006 | Approved RAG | Policy owner + retrieval maintainer | BLOCKED: reviewed effective corpus, audience filters, citations and injection/expiry negatives |
| AI-007 | Model/JEV evaluation | ML maintainer | NOT_RUN: reviewed diverse data, near-duplicate held-out checks, model/Git/data/run hashes and fallback benchmark |
| AI-008 | Public exposure controls | Infrastructure + service maintainers | NOT_RUN: authenticated BFF perimeter, body/admission/rate limits, load/SLO tests, retention and operational alerts |
| AI-009 | Deployment evidence | Release maintainer | NOT_RUN until recorded: remote CI, Docker build/smoke and reviewed base-image policy |

Request IDs and safe request latency/status JSON logs are available. There is no
claim of model/tool stage metrics, alert coverage or measured production capacity.
The service must remain a local/demo foundation while these gates are missing.
