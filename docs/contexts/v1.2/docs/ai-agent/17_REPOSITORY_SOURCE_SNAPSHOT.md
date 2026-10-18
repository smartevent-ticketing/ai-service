# 17 — Repository Source Snapshot (18/10/2026)

Source references are GitHub repo `main` as inspected in the 17–18/10/2026 context audit. These SHAs are **reference snapshot only**, not a claim of current HEAD in future.

| Repository | SHA | Role |
|---|---|---|
| `smartevent-ticketing/smartevent-backend` | `200720e32a4d5b3a7c80c599896c74517de95b37` | business source of truth |
| `smartevent-ticketing/smartevent-web` | `0e5ac549af4427b4a60be47ab6e708b2003ad75e` | Next.js UI/BFF |
| `smartevent-ticketing/smartevent-infra` | `b82a3d4c1b0b6ba1757a55b260fe843d502ddc1d` | Compose supporting services |
| `smartevent-ticketing/ai-service` | `main`, empty at audit | target service to implement |

Verified implementation findings: `ReservationServiceImpl` uses 10-minute hold and CAS; `EventSeatServiceImpl.getAvailableSeatsByArea` returns all statuses; `TicketResponse` carries `qrCodeBase64`; Order and Payment read services permit ADMIN ownership bypass for legitimate admin flows, which customer chatbot must never inherit; frontend booking route `/reservations/{eventId}` is before `/checkout?reservationId=...` and must not be bypassed.

Do not treat these verified code paths as AI runtime implementation. Agent must fetch latest SHA/dirty tree and reconcile any changes before code editing.
