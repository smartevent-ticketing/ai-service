# Verified SmartEvent upstream snapshot

Compared against GitHub organization `smartevent-ticketing` at the following default-branch commits, checked 2026-10-18. These are inspection points, **not** code imported or modified by this ZIP.

| Repository | Main SHA | Status |
|---|---|---|
| `smartevent-backend` | `200720e32a4d5b3a7c80c599896c74517de95b37` | Modular Monolith, existing read/write endpoints |
| `smartevent-web` | `0e5ac549af4427b4a60be47ab6e708b2003ad75e` | Next.js storefront / checkout; separate UI mutation flows |
| `smartevent-infra` | `b82a3d4c1b0b6ba1757a55b260fe843d502ddc1d` | PostgreSQL, Redis, RabbitMQ, MinIO Compose |
| `ai-service` | empty default branch at inspection | This ZIP is a new codebase; not pushed |

Important backend limitations: Event search supports `q`, `city`, `categoryId` and pagination, NOT an explicit date-range query. Event-child GET APIs must not be enabled until anonymous PUBLISHED visibility and parent-ID membership are tested; `get_available_seats` currently exposes mixed status values and requires filtering. Ticket responses contain `qrCodeBase64`, so raw DTOs must never be forwarded to a language model. Consumer auth must remain CUSTOMER_SELF_ONLY. `POST` writes exist in Spring Boot and Next.js, but the AI has no permissions or routes to call them.
