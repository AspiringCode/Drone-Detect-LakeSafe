# Privacy and safety design

LakeSafe is designed so that a public awareness feature does not become a live tracking
feed and an unfinished hardware seam does not look like an autonomous rescue capability.

## Civilian boundary

Civilian endpoints read dedicated `public_lakes`, `public_alerts`, and
`public_patrol_presence` projections. Public alerts use approximate area labels rather
than precise coordinates. Patrol presence uses generalized zones and a minimum five-
minute publication delay enforced in both database constraints and response validation.
The backend also exposes an anonymous public WebSocket endpoint. Its broadcast helper
checks the `PublicPatrolPresence` DTO, including the minimum delay, and checks that the
payload lake matches the channel. It does not query the database or independently verify
persistence. The current civilian dashboard uses the public REST routes and does not
connect to that public WebSocket. Public clients do not receive station membership,
precise routes, hardware identifiers, health details, response tactics, subject
information, or thermal evidence.

## Operational identity and station scope

Operational REST and WebSocket access requires an authenticated officer principal with:

- current identity verification;
- MFA assurance level `aal2`, plus recent MFA for selected high-impact actions;
- an active membership in the station that owns the lake; and
- a role granting the exact requested capability.

The FastAPI policy layer reloads authority instead of trusting client-supplied roles.
The current dashboard operations page connects to the authenticated operational
WebSocket. Operational WebSockets reject credentials in URLs, authenticate through a
bearer subprotocol, and periodically revalidate access so a revoked membership cannot
keep a long-lived connection indefinitely. Supabase row-level security and grants repeat
the station boundary in the database. Cross-station absence and denial responses are
shaped to avoid unnecessary resource disclosure.

## Evidence privacy

Thermal clips are stored in a private `thermal-clips` bucket. Anonymous and authenticated
browser roles have no direct object access. After officer, station, and read-operations
checks, the backend service can generate a signed evidence URL valid for no more than 60
seconds. Allowed and denied reads produce append-only audit events with actor, station,
lake, request/correlation identifier, action, decision, and reason. Failure to record the
audit or sign the link fails the request closed.

## Audit, correlation, and abuse controls

Privileged workflows write append-only audit records, and database triggers prevent
history mutation. Request/correlation identifiers support tracing and idempotent safety
actions without exposing secrets. Durable database rate-limit buckets serialize claims
across API workers; limits cover privileged operations rather than relying on one
process's memory. Verification sessions and invitation material use bounded expiry and
single-use or hashed/encrypted storage paths.

## Real-device safety seam

Simulated and real inventory, adapters, and command envelopes are separated. A real
adapter rejects simulated commands and station/lake mismatches. Outbound gateway commands
are HMAC-signed with a backend-only key. Device heartbeats and acknowledgements use
separate signed device credentials, canonical request bytes, time bounds, and claimed
sequence numbers to resist replay.

Commands are written to a durable outbox with idempotency and desired-state versions.
Publishing to a gateway is not treated as device execution: the matching acknowledgement
must arrive before active state advances. Heartbeat age, connectivity, health,
maintenance, and battery affect capacity. Missing/expired acknowledgements or heartbeats
can reduce capacity, degrade autonomy, hold safety state, or request safe return. The
software does not expose manual flight steering. These mechanisms are implemented and
tested in software but have not been physically validated with an open-water fleet.

## Fail-closed planning and connector behavior

Only reviewed connector configurations may create production snapshots. Publisher or
schema failure creates a quarantined snapshot with no invented data. Candidate geometry
must validate before persistence and atomic activation; a concurrency conflict leaves the
newer plan active. Synthetic legacy rows are available only through the explicitly named
demo loader and an explicit `use_fixture=True`; a failed production request cannot enter
that path.

## Secret handling and operational caveats

Supabase service-role credentials, identity-provider secrets, verification-session keys,
real-gateway signing material, and device secrets remain backend-only. None belongs in a
`VITE_` browser variable, log, screenshot, demo video, repository, or judge handout.

LakeSafe is not a lifeguard, emergency-dispatch service, 24/7 monitor, certified aviation
system, or validated medical/safety device. Operators must retain established emergency
procedures and human authority. A future field trial requires legal, aviation, privacy,
public-safety, and water-safety review plus measured performance under disclosed
conditions.
