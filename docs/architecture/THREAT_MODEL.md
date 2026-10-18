# Minimal Threat Model — read-only runtime

Assets: user identity, private orders/payment status, ticket QR/credentials, unpublished events, business DB and policies. Threats: malicious prompts asking to mutate data, arbitrary URL/SSRF, GET with side effects (IPN), backend overbroad DTO, cross-account IDOR, prompt injection in RAG documents, partial inventory presented as complete, replayed conversation state interpreted as identity.

Controls: all business tools initially OFF; allowlist registry and strict PUBLISHED validation; private reads are disabled (no JWT delegate); `SafeBackendTransport` fixed origin, GET, no redirects and response caps; allowlist-only projection; typed state and arguments; no raw JSON logging or LLM prompt; backend DB is never opened by AI; offline model fallback does not claim live values. The existing Next.js catch-all proxy accepts mutations; **never reuse that generic proxy as the AI tool executor**. Enforce method/path at the AI BFF boundary as well as service.

Residual risks: no integrated authentication/rate limit, no validated GET side effect tests, no real customer data leak tests, no continuous production monitoring. Therefore it is not a production deployable customer chatbot yet.
