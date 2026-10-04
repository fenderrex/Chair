# Modular Dispatch Architecture

This project keeps demo and production dispatch behavior identical below the location provider layer.

## Location pipeline

```text
Demo map click ─┐
                ├─> app/location/providers/*
Production GPS ─┘
                      ↓
             app/location/pipeline.py
                      ↓
          app/location/driver_location.py
                      ↓
                 COMMIT MySQL
                      ↓
            app/dispatch/worker.py
                      ↓
         app/dispatch/proximity.py
                      ↓
         app/dispatch/events.py
                      ↓
        passenger + driver Socket.IO
```

The demo provider does not contain a separate matching algorithm.

## Dispatch modules

- `app/dispatch/timing.py`
  - UTC helpers
  - seconds-until calculations

- `app/dispatch/radius.py`
  - expansion timer
  - current passenger search radius

- `app/dispatch/fare.py`
  - fare estimate
  - pickup ETA estimate

- `app/dispatch/queue.py`
  - RideOffer lookups
  - open/waiting queue helpers
  - trip dispatch summary

- `app/dispatch/plan.py`
  - initial driver search plan

- `app/dispatch/proximity.py`
  - authoritative live driver distance recalculation
  - enter/leave radius
  - live queue ranks

- `app/dispatch/worker.py`
  - iterate all active passenger searches

- `app/dispatch/events.py`
  - passenger snapshots
  - driver queue refresh
  - Review Fare notifications
  - passenger reviewing-driver notifications

- `app/dispatch/fare_rounds.py`
  - full-search wait
  - fare escalation
  - higher-fare round processing

- `app/dispatch/serialization.py`
  - driver-facing trip request payload

## Trip modules

- `app/trips/requests_service.py`
  - create request
  - active passenger request lookup

- `app/trips/lifecycle.py`
  - accept / decline
  - pickup
  - help request
  - cancel

- `app/trips/services.py`
  - compatibility facade only
  - keeps old imports working while implementations live in small modules

## Broker responsibilities

The broker continuously:

1. finds active passenger searches;
2. reads current committed driver locations;
3. calculates current pickup distance;
4. expands passenger radius by the configured step after each timer interval;
5. moves eligible drivers into `OFFERED`;
6. moves out-of-radius drivers back to `WAITING`;
7. discovers new/returning drivers;
8. preserves explicit declines for the current fare round;
9. reorders active offers by current pickup distance;
10. commits queue state;
11. pushes passenger and driver updates;
12. processes fare-round escalation;
13. advances simulation jobs.

## Production switch

Production GPS should call:

```python
from app.location.providers.gps import submit_gps_driver_location
```

Demo map clicks call:

```python
from app.location.providers.demo import submit_demo_driver_location
```

Both providers immediately enter the same `ingest_driver_location()` pipeline.


## Two-phase trip motion

Broker simulation is split into two phases:

```text
TO_PICKUP
TO_DESTINATION
```

`TO_DESTINATION` cannot start until `Trip.pickup_confirmed_at` exists and the
trip is `IN_PROGRESS`.

Passenger confirmation prepares the destination job but does not start it.
The driver explicitly starts the second phase with the same broker start
endpoint used for the first phase.

At destination completion the broker:

```text
sets trip.status = COMPLETED
sets trip.completed_at
sets final_fare
marks the driver available
leaves both driver/passenger coordinates at destination
```

The completed snapshot causes both after-ride survey cards to appear.


## Broker validation vs demo motion

Broker responsibilities are now separated by purpose.

### `app/broker/services.py`

Normal broker services contain the business rules and validation:

```text
trip exists
driver exists
driver is assigned to trip
driver has a location
pickup phase may start
passenger confirmation exists before destination phase
trip is not canceled/completed
job can start
job can pause
job may advance
job/trip/driver relationship is still valid
```

This module changes normal state such as:

```text
READY -> RUNNING
RUNNING -> PAUSED
DRIVER_ASSIGNED -> DRIVER_EN_ROUTE
```

It does not move fake coordinates.

### `app/broker/demo_service.py`

Demo-only motion contains:

```text
route densification into simulated GPS points
driver -> pickup simulated movement
driver + passenger -> destination simulated movement
fake LocationUpdate rows
simulation progress
demo arrival at pickup
demo arrival at destination
```

It does not decide whether the driver is allowed to start or continue.

The broker loop performs:

```text
normal validation
    ↓ allowed
demo_service advances one fake movement step
```

When `DEMO_MODE=0`, fake movement is not advanced at all. Dispatch, fare, queue,
and normal broker validation continue to run, while production is expected to
receive real GPS/location updates.


## Persisted broker event queue

`broker.py` is now event-driven around the database.

```text
normal service writes authoritative state
        ↓
writes broker_events row
        ↓
broker claims due PENDING row
        ↓
runs only the requested service
        ↓
commits resulting state
        ↓
optionally writes next broker_events row
```

The idle broker loop performs only a lightweight due-event query. It no longer
runs proximity, fare, queue, and motion calculations merely because time
passed.

### Demo route motion

```text
Start Driving
  -> DEMO_STEP row
  -> normal broker validation
  -> demo_service advances one point
  -> commit coordinates/progress
  -> enqueue next DEMO_STEP with due_at
```

`PICKUP_PENDING` remains a normal validation gate. No destination event chain
can start until the passenger confirms pickup and the trip becomes
`IN_PROGRESS`.

### Production location

Production GPS writes use the same location pipeline and enqueue
`PROXIMITY_RECONCILE`; they do not use `DEMO_STEP`.


## Flat non-recursive scheduling

The previous persisted event chain was replaced with due timestamps on the
actual state rows.

```text
SimulationJob
    status
    phase
    current_index
    next_due_at

Trip
    next_dispatch_at
    fare_wait_until
```

The broker loop does only:

```text
SELECT due trips
SELECT due simulation jobs
```

Then it handles each due row once.

A handler may update the row's next due timestamp, but it cannot enqueue or
invoke another broker handler. This keeps the call graph flat and makes the
next trigger inspectable directly from database state.

The old `broker_events` runtime model/module is no longer used.


## Two-lane broker scheduler

The broker is one process with two independent flat ticks. It does not create
threads for each trip and neither lane recursively invokes the other.

```text
BROKER PROCESS
│
├── COLLISION TICK
│   ├── REQUESTED / OFFERED trips only
│   ├── collision_dirty
│   ├── next_dispatch_at
│   ├── fare_wait_until
│   ├── current driver positions
│   └── RideOffer match / unmatch / rank
│
└── SIMULATION TICK
    ├── RUNNING SimulationJob rows only
    ├── next_due_at
    ├── TO_PICKUP
    ├── TO_DESTINATION
    └── driver/passenger demo coordinates
```

The only cross-lane handoff is persisted state. For example, when a completed
demo ride makes a driver available again, the simulation lane marks active
searches `collision_dirty`; the collision lane performs the actual match work
on its own later tick.

### Collision trigger state

Trips contain:

```text
collision_dirty
collision_reason
collision_requested_at
collision_revision
```

Driver-position HTTP writes never perform matching directly. They commit the
location, mark active searches dirty, and return.

### Passenger visibility

`trip_notices` stores ordered passenger-facing broker events. The web process
emits them as `passenger_step` and snapshots include recent notice history.

## UI lifecycle projection (2026-09-24)

Passenger and driver screens now use `app/static/js/lifecycle-ui.js` as a presentation-only lifecycle manager. The server/database remain authoritative.

Each marked ride DIV declares `data-lifecycle-statuses`, `data-lifecycle-order`, and a stable `data-lifecycle-key`. The lifecycle manager projects each authoritative trip snapshot into one active DIV.

- Normal mode: only the active lifecycle DIV is rendered.
- Demo mode: all lifecycle DIVs remain visible; previous DIVs are frozen/gray, the active DIV is highlighted, and future DIVs are muted.
- The mode switch persists per role in `localStorage`.
- Lifecycle projection does not create trip transitions and does not replace dispatch, broker, database, or Socket.IO state.
- Passenger and driver lifecycles are independent projections of the same trip snapshot, so they may show different active DIVs at the same moment.

The existing detailed cards remain available as supporting/debug UI. New ride functionality should put state-changing actions in the lifecycle DIV for the status where the action is valid, while the backend continues to validate every transition.

## Fare round search reset

Fare escalation does not replace the broker's radius algorithm. Passenger fare
approval resets the broker clock (`dispatch_started_at`) and preserves known
`RideOffer` rows. Non-closed rows return to `WAITING`; their `eligible_at` is
recomputed from current/last-known pickup distance and the admin-configured
radius step + expansion interval. The collision lane then performs its normal
radius expansion and is authoritative for `WAITING -> OFFERED`.

Driver queue serialization includes WAITING rows so the request does not blink
out between fare rounds. WAITING is non-actionable and exposes
`offer_available_at`, `required_radius_miles`, and `seconds_until_eligible` for
presentation only. The browser countdown cannot unlock an offer; Accept and
Decline require an authoritative OFFERED row.

## Admin-capped expanding passenger search

The broker search radius is clock-driven from `Trip.dispatch_started_at`. `radius_miles` is the amount added each completed `expansion_seconds` interval, while `max_radius_miles` is the admin-configured geographic cap. The broker continues scheduling expansion ticks even when no driver sits at the next threshold, so the radius does not stop merely because all currently-known drivers were reached. When the maximum radius is reached, the configured last-driver grace period begins; only after that can fare escalation be offered.

A passenger-approved fare increase resets `dispatch_started_at`, returns the active radius to the smallest round radius, and reuses known eligible drivers as WAITING until the expanding radius reaches them again. Drivers beyond the configured maximum are CLOSED for that round and can re-enter if their live location later moves inside the cap.

Admin platform-map snapshots include each active passenger search's current and maximum radius. The Leaflet admin view draws a live purple radius circle around each passenger pickup/current passenger position.
