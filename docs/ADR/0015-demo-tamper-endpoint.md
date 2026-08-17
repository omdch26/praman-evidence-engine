# ADR 0015: A live tamper-attempt endpoint, gated four independent ways

**Status:** Accepted
**Date:** 2026-08-16

## Context

The public demo's "Try to secretly edit event #5" button was, before this
ADR, pure client-side JavaScript — it changed some CSS and text on screen
and never contacted the backend. A technical reviewer correctly objects:
*"You just turned some CSS red. None of this proves your backend does
anything."*

That objection cannot be answered by our server asserting more things about
itself. It is answered by letting a visitor's browser trigger a real UPDATE
against the real `events` table and see PostgreSQL's own rejection text —
evidence that does not depend on trusting our application code, only on
trusting Postgres, which the visitor did not have to take our word for
either (the SQLSTATE and error text are Postgres's, unmodified).

This means shipping an HTTP endpoint whose entire purpose is to attempt a
write against the ledger. That is worth a design record on its own.

## Decision

`POST /demo/tamper-attempt`, gated four independent ways, all required:

1. **404 when `settings.demo_mode_enabled` is `False`** (the default). Not
   403 — an endpoint that is off should not confirm its own existence.
2. **`tenant_id` must match `^demo-[a-z0-9]{8}$`**, checked against the
   `X-Tenant-ID` header, 403 otherwise. A real customer tenant is never a
   valid target, regardless of what demo mode is set to.
3. **The `UPDATE`'s `WHERE` clause is scoped to `(tenant_id, event_id)`
   together**, not `event_id` alone. A caller cannot reach another
   tenant's row by guessing or brute-forcing event ids — the query itself
   cannot select it, independent of whether the append-only trigger
   exists.
4. **The `UPDATE` runs inside an explicit `SAVEPOINT`**
   (`db.begin_nested()`), rolled back in a `finally` block — unconditionally,
   whether the statement raised, matched zero rows, or (should the trigger
   ever be absent or misconfigured) actually succeeded.

## Options considered

| Option | Pros | Cons | Chosen? |
|---|---|---|---|
| Keep it client-side only (status quo) | No backend risk at all | Answers nothing — a reviewer can see it never leaves the browser | No |
| Server asserts "tamper would fail" without attempting it | Still no backend risk | Still just us talking about our own system | No |
| **Real UPDATE, four-gated, always rolled back (chosen)** | The rejection is Postgres's, not ours — independently checkable | A live endpoint that deliberately targets the ledger's write path exists in production | Yes |
| Real UPDATE with only tenant-regex validation, no query-level scoping | Simpler query | `event_id` alone in the WHERE clause means a caller can target another tenant's row; safety then depends entirely on the trigger never being dropped, changed, or having an edge case | No — this is the gap closed during review before this endpoint shipped |

The fourth row is not hypothetical caution — it was the actual initial
design brief for this endpoint, corrected before implementation. The trigger
should never be removed, but "should never" is a promise about the future,
and this endpoint's whole premise is not asking anyone to take promises
about the future on faith.

## Rejected alternative: fake the error message client-side

Rendering a plausible-looking Postgres error string in the frontend,
without ever calling the backend, was considered and rejected outright. It
would look identical to a real reviewer until they opened the network tab,
at which point the entire feature's credibility — and by extension the
credibility of every other claim in the demo — collapses at once. A
fabricated proof of honesty is a worse failure mode than no proof at all.

## Consequences

**Easy:**
- The response's `database_error` and `sql_state` are the driver's own
  `exc.orig` attributes, not application-constructed strings — nothing to
  keep in sync if the trigger's message text ever changes.
- Disabling this feature for a real deployment is one environment
  variable, defaulting to off.

**Hard:**
- This is the one piece of the whole verification story that writes
  against the ledger, even transiently. Every other layer (bundle
  verification, standalone verifier) is read-only. Any future change to
  this file needs the same scrutiny this ADR represents, not less.
- `demo_mode_enabled=True` must never be set on a deployment holding real
  tenant data, and nothing in the code enforces that beyond documentation
  and the tenant-regex gate. The regex gate is the actual backstop; the
  environment flag is a convenience, not the safety boundary.

## Revisit when

- Any change to the `events` table schema or the append-only trigger
  (migration 001) — re-verify this endpoint's assumptions against the new
  trigger behaviour before merging.
- If demo traffic volume ever makes per-request `SAVEPOINT` overhead
  material (unlikely at demo scale; revisit only if evidence, not
  speculation, says otherwise).
