# RideShare MySQL + Passenger/Driver/Admin Demo

> **WARNING — DEMONSTRATION SOFTWARE**
>
> This software is provided primarily for demonstration, development, evaluation, educational, and testing purposes. It is provided **AS IS**, **AS AVAILABLE**, and **WITH ALL FAULTS**, with no express, implied, statutory, or other warranties. It is not represented as production-ready, certified, insured, legally compliant, or suitable for commercial rideshare, transportation, safety-critical, or regulated operation. Anyone who deploys or operates it assumes responsibility for testing, security, privacy, legal and regulatory compliance, licensing, permits, insurance, taxes, safety, and operation.
>
> See [`LICENSE.md`](LICENSE.md), [`COMMUNITY_LICENSE.md`](COMMUNITY_LICENSE.md), [`COMMERCIAL_LICENSE.md`](COMMERCIAL_LICENSE.md), and [`TRADEMARKS.md`](TRADEMARKS.md) before using or redistributing this project.

## Licensing model

This project uses a **source-available Community + Commercial licensing model**. Qualifying low-income individuals and small entities may run and modify the software, including qualifying small deployments, while they remain within published Community thresholds. Larger or post-threshold commercial/hosted/SaaS use requires commercial authorization. The controlling terms are in `LICENSE.md` and the incorporated license documents listed above.

This version uses MySQL and adds separate passenger, driver, and admin views plus a shared messaging system.

## 1. Create the MySQL database

SQLAlchemy creates the tables, but MySQL must already contain the database:

```sql
CREATE DATABASE history_db
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

## 2. Configure credentials

Copy:

```bash
cp .env.example .env
```

Then edit `.env`:

```text
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=history_db
```

Do not store the real database password directly in Python source.

## 3. Install

```bash
python3 -m pip install -r requirements.txt
```

## 4. Run

```bash
python3 app.py
```

Open:

- Home: http://127.0.0.1:5100/
- Passenger: http://127.0.0.1:5100/passenger
- Driver: http://127.0.0.1:5100/driver
- Admin: http://127.0.0.1:5100/admin/

## Tables created automatically

The app creates tables for the current models, including:

- users
- drivers
- vehicles
- trips
- location_updates
- payments
- identity_documents
- messages

## Communication

Passenger and driver messages are stored in MySQL and broadcast live over Socket.IO.

The `messages` table includes:

- trip_id
- sender_role
- sender_name
- recipient_role
- body
- is_system
- created_at

## Views

### Passenger
- choose pickup and destination
- browser GPS pickup
- route and fare estimate
- request demo ride
- watch test driver movement
- live messages with driver

### Driver
- live route map
- passenger pickup/destination
- test-driver status
- live messages with passenger

### Admin
- counts for users/drivers/trips/messages
- recent trip activity
- direct links to Passenger and Driver screens


## Signup

The admin dashboard now links directly to:

- `/passenger`
- `/driver`
- `/signup`

The signup page creates persistent MySQL users with:

- display name
- email
- password hash
- role (`PASSENGER` or `DRIVER`)
- account status
- created/updated timestamps

Passwords are stored as hashes, not plaintext.

### Important existing database note

If the `users` table was already created before this update, `db.create_all()` will not add the new `password_hash` column to an existing table.

For a development database with disposable data, you can recreate the `users` table/database.

For data you want to preserve, run a migration or manually add:

```sql
ALTER TABLE users
ADD COLUMN password_hash VARCHAR(255) NULL;
```


## Database connection fix

This version no longer depends on `DATABASE_URL`.

The Flask app uses the MySQL configuration in:

```text
app/__init__.py
```

and connects to:

```text
mysql+pymysql://root:...@localhost:3306/history_db
```

Environment variables remain optional overrides.

Test the database before starting Flask:

```bash
python3 test_db.py
```

Expected result:

```text
MYSQL CONNECTION OK
Database: history_db
User: root@localhost
```

Then start the application:

```bash
python3 app.py
```


## Socket.IO compatibility fix

This build uses Socket.IO HTTP long-polling instead of attempting a WebSocket
upgrade. The prior WebSocket upgrade was producing:

```text
GET /socket.io/?EIO=4&transport=websocket ... 500
ConnectionError
```

The `/trips/request` route itself was succeeding with HTTP 200. The 500 was
from the realtime transport upgrade.

Polling still provides live passenger/driver updates through Socket.IO and is
more stable with the current Flask development server and Python 3.13 setup.


## Driver dispatch update

Ride requests no longer auto-assign the demo driver.

The dispatch flow is now:

```text
Passenger requests ride
        ↓
Find drivers where:
    is_online = true
    is_available = true
    verification_status = APPROVED
        ↓
Calculate distance from each driver to pickup
        ↓
Sort nearest → farthest
        ↓
Offer request to closest available driver first
        ↓
Driver accepts
        ↓
Trip becomes DRIVER_ASSIGNED
```

The passenger sees `SEARCHING` / `OFFERED` until a driver accepts.

The demo controls are now on the Admin page only.


## Existing MySQL schema upgrade

This build automatically adds the newer dispatch columns to an existing
development database before querying the ORM.

Columns added when missing:

### drivers

- `current_latitude`
- `current_longitude`
- `last_location_at`

### trips

- `offered_driver_id`
- `offered_at`
- `offer_rank`

`db.create_all()` only creates missing tables. It does not add columns to
tables that already exist, so `app/schema.py` performs these small upgrades.

You can also run the migration check manually:

```bash
python3 migrate_schema.py
```

Then start normally:

```bash
python3 app.py
```


## Five-driver dispatch test

This build seeds five approved, online, available test drivers at different
locations.

Admin now shows every driver with:

- ID
- name/email
- online status
- availability
- location
- vehicle
- direct link to that exact driver's screen

Open a driver screen with:

```text
/driver?driver_id=1
/driver?driver_id=2
...
```

When the passenger requests a ride, the closest available driver receives a
Socket.IO `ride_offer` in that driver's private room.

The driver screen now displays a visible ride-request alert and updates the
offer card immediately.


## Modular requests + route preservation
- `maps/services.py` owns route geometry, distance, time, and fallback detection.
- `trips/state.py` owns state constants.
- New trips persist as `REQUESTED` before dispatch.
- Drivers see active requesting passengers, state, fare, distance/time, and can preview the stored route.
- The privately offered closest driver sees the same route immediately with Accept Ride.
- Admin sees all active requests and offered driver IDs.
- Straight-line fallback is labeled as a fallback instead of silently pretending to be a road route.


## Rex GPS + simulated driver locations

- The five test drivers include a dedicated driver named **Rex**.
- Every driver screen initializes its map from that driver's stored location.
- Admin can open any driver directly from the driver table.
- Admin can start/stop simulated GPS movement for all five test drivers.
- Admin can click **Use My GPS for Rex**; the browser asks for geolocation permission and writes that coordinate into Rex's driver record.
- Driver screens receive location changes live through the driver's private Socket.IO room.
- Simulation controls remain Admin-only.


## Ride acceptance and cancellation

Drivers can accept the ride currently offered to them from the Driver screen.

Passengers can cancel an active request/ride from the Passenger screen.

Cancellation:

- sets trip state to `CANCELED`
- stores `canceled_at`
- clears active driver offers/assignment
- makes the affected driver available again
- emits `ride_canceled` to passenger/driver clients
- removes the canceled request from active request lists


## Driver accept + drive-to-passenger simulation

The Driver request list now has two actions:

- **Preview Trip Route** — shows the passenger's pickup-to-destination route.
- **Accept Ride** — available to the driver who currently owns the closest-driver offer.

After acceptance, the Driver screen unlocks:

- **Preview Pickup Route**
- **Start Driving**
- **Stop Simulation**

The pickup route is calculated separately from the passenger trip route:

```text
driver current location
        ↓
passenger pickup
```

The simulation follows the returned road-route geometry and posts each simulated
driver position through `/location/update`.

The Passenger page listens for those driver location events and moves the driver
marker in real time. This mirrors the future production behavior where a real
driver phone would send GPS locations instead of the simulator.


## Accept pipeline fix

The driver acceptance flow has been rebuilt around persisted state rather than
depending only on the realtime Socket.IO event.

This fixes the case where a trip is already `OFFERED` before the driver page is
opened or refreshed.

### Driver request cards

Every active request now shows:

- Preview Route
- offer status
- Accept Ride when `offered_driver_id` matches the current driver

### Offer recovery

`GET /trips/requests/active` is used to recover an existing offer from MySQL.

If an offered request belongs to the current driver, the Driver page
automatically hydrates the Ride Request panel and enables Accept Ride even if
the original Socket.IO offer event was missed.

### After acceptance

Accepting the ride immediately unlocks:

- Preview Pickup Route
- Start Driving
- Stop Simulation

The app also has:

```text
GET /drivers/<driver_id>/active-trip
```

so refreshing the Driver screen after accepting a ride recovers the assigned
trip and simulation controls.


## Database broker simulation

Driver motion is no longer simulated by JavaScript.

Running:

```bash
python3 app.py
```

starts Flask and a separate:

```text
broker.py
```

subprocess.

The simulation pipeline is now:

```text
Driver accepts request
        ↓
Driver presses Start Driving
        ↓
simulation_jobs row becomes RUNNING
        ↓
broker.py subprocess
        ↓
next route point
        ↓
MySQL
├── drivers.current_latitude/current_longitude
├── location_updates
├── trips.progress_percent
├── trips.driver_eta_seconds
└── trips.status
        ↓
GET /trips/<trip_id>/live
      /                 \
 Driver page        Passenger page
```

Both browser views read the same database-backed trip state every 750 ms.

This is intentionally close to the future production architecture. The
simulation broker can later be replaced by GPS updates from a real driver
device while leaving the Passenger live-trip endpoint unchanged.

### Simulation job states

```text
READY
RUNNING
PAUSED
COMPLETED
ERROR
```

### Trip states during simulated pickup

```text
DRIVER_ASSIGNED
DRIVER_EN_ROUTE
DRIVER_ARRIVED
```

The broker records a `location_updates` row for each simulated GPS point, so
the location history is also persisted instead of existing only in a browser.

## Admin account selection and database-safe deletes

The Admin page can now select a specific Driver or Passenger and open that exact view.

```text
Admin
├── Driver selector → /driver?driver_id=<id>
└── Passenger selector → /passenger?user_id=<id>
```

New passenger trip requests store `passenger_id` in addition to the display name, so the selected rider is tied to the database trip record.

Admin can also delete:

- trips
- drivers
- passenger/rider accounts

### Broker synchronization

MySQL is the source of truth for simulations. The broker no longer keeps ORM job objects between cycles.

On each broker cycle it:

1. reconciles simulation jobs against the current trip and driver rows
2. reloads the IDs of `RUNNING` jobs from MySQL
3. re-queries each job with `SELECT ... FOR UPDATE`
4. checks that the trip still exists, is assigned to the same driver, and has not been canceled/deleted
5. advances one location point only after those checks

Trip deletion locks and deletes the simulation job **before** deleting trip-related rows. This prevents a subprocess that was already running from continuing to write location/progress records for a deleted trip.

Driver deletion stops/removes that driver's simulation jobs, detaches the driver from historical trips, and cancels active trips. Passenger deletion preserves historical trip rows by clearing `passenger_id`, while active rides are canceled.


## Driver signup synchronization

A user who signs up with:

```text
role = DRIVER
```

now creates two coordinated database records:

```text
users
  ↓
drivers
```

The new Driver profile starts as:

```text
verification_status = PENDING
is_online = false
is_available = false
```

so signup does not bypass the driver approval/document flow.

The Admin dashboard also repairs older accounts automatically. If an existing
`users` row has role `DRIVER` but no matching `drivers` row, the dashboard/startup
creates the missing pending driver profile using the same email and display name.

This makes newly signed-up drivers appear under **Admin → All drivers**.


## Timed ranked dispatch

Ride dispatch now uses persistent `ride_offers` rows instead of one
`offered_driver_id` as the sole source of truth.

The default development policy is:

```text
0 seconds    rank #1 driver offered
10 seconds   rank #2 driver added
20 seconds   rank #3 driver added
30 seconds   rank #4 driver added
40 seconds   rank #5 driver added
```

Earlier drivers remain eligible while the offer expands. The first valid
driver to accept wins the trip. All other open offers are then closed.

The ranking is currently based on pickup distance:

```text
dispatch_score = distance_miles
```

This is intentionally modular. `dispatch_score` can later combine factors
such as driver rating, idle time, vehicle type, acceptance history, or other
dispatch policy without changing the offer/timer model.

### Decline

Every driver with an active offer has:

```text
Accept Ride
Decline
```

A decline creates a persistent decision in `ride_offers.status = DECLINED`.

If no other currently-open driver remains after the decline, the next ranked
driver is offered the trip immediately instead of waiting for the timer.

### Dispatch timer

`trips` now stores:

```text
dispatch_started_at
next_dispatch_at
dispatch_wave
```

The separate `broker.py` subprocess checks the database each cycle and calls
the dispatch scheduler when `next_dispatch_at` is reached.

The Driver page polls the database-backed request endpoint once per second, so
the countdown and newly expanded offers stay synchronized even if a Socket.IO
event is missed.

### Offer history

The `ride_offers` table stores:

```text
trip_id
driver_id
rank
distance_miles
dispatch_score
status
offered_at
declined_at
accepted_at
closed_at
```

This gives the Admin/dispatch system a history of the best driver, runner-up,
declines, and which ranked driver ultimately accepted.


### Per-driver eligibility timestamp

Every candidate driver gets an `eligible_at` timestamp in `ride_offers`.

For example:

```text
Driver #1
distance: 0.8 mi
pickup ETA: 2 min
eligible_at: immediately

Driver #2
distance: 1.4 mi
pickup ETA: 3 min
eligible_at: about 1 minute later

Driver #3
distance: 2.0 mi
pickup ETA: 4 min
eligible_at: about 2 minutes later
```

Drivers can see the request before they are eligible. Their Driver page shows:

```text
Rank #2 • eligible in 37s
```

and the Accept button remains disabled.

Once their `eligible_at` timestamp passes, the broker changes that offer from:

```text
WAITING
```

to:

```text
OFFERED
```

and Accept/Decline become active.

This means the offer expands because the closer drivers have spent enough of
their pickup-time advantage without responding, rather than simply because an
arbitrary global timer expired.


## Passenger trip tracing pipeline

The Passenger page now follows the same database-backed trip as the Driver page.

Important fixes:

- Passenger now stores `trip.trip_id` correctly after requesting a ride.
- Passenger can recover an existing active trip after refresh/login using:
  `GET /trips/passenger/<passenger_id>/active`
- Assigned driver information comes from the actual accepted driver, not the demo driver.
- Live driver data includes:
  - driver name
  - driver ID
  - vehicle year/color/make/model
  - plate/state
  - current GPS position
  - GPS update time
  - pickup ETA
- The Passenger UI shows a state pipeline:
  `REQUESTED -> DRIVER_ASSIGNED -> DRIVER_EN_ROUTE -> DRIVER_ARRIVED -> IN_PROGRESS`
- When the broker reaches pickup it sets `trips.driver_arrived_at`.
- Both Passenger and Driver pages show the database-backed pickup waiting clock.
- Passenger gets a persistent arrival notice when the driver reaches pickup.

The dispatch UI also no longer reports "Dispatch timer paused" when there is
meaningful dispatch state. It shows the current driver's eligibility countdown,
the next runner-up eligibility countdown, or the number of currently eligible
drivers.


## driver_arrived_at schema correction

`driver_arrived_at` belongs to the `trips` table.

Correct model:

```text
trips.driver_arrived_at
```

Incorrect model removed:

```text
ride_offers.driver_arrived_at
```

Startup schema migration now ensures the trip column exists.

For an existing database you can also run:

```bash
python3 repair_driver_arrival_schema.py
```

before starting the app.


## WebSocket trip stream lifecycle

Driver and Passenger trip state no longer poll `/trips/<id>/live`.

The browser connection now uses Socket.IO with WebSocket-only transport:

```text
transports = ["websocket"]
upgrade = false
```

`simple-websocket` is included explicitly in `requirements.txt` for the
Flask-SocketIO threading server on Python 3.13.

### Connection lifecycle

Passenger:

```text
WebSocket CONNECTED
        ↓
register_passenger
        ↓
server finds active trip
        ↓
join trip:<trip_id>
        ↓
JOIN_SNAPSHOT
        ↓
trip_snapshot stream
        ↓
STATE_UPDATE events
        ↓
TERMINAL (COMPLETED / CANCELED)
        ↓
leave_trip
```

Driver:

```text
WebSocket CONNECTED
        ↓
register_driver
        ├── joins driver:<driver_id>
        ├── receives driver_request_queue
        └── recovers active trip if one exists
                ↓
          join trip:<trip_id>
                ↓
          trip_snapshot stream
                ↓
          STATE_UPDATE events
                ↓
          TERMINAL
                ↓
          leave_trip
```

### Command vs stream traffic

Commands still use POST requests:

```text
request ride
accept ride
decline ride
cancel ride
prepare simulation
start simulation
pause simulation
```

Ongoing trip state does not use repeating browser GET requests.

State is streamed with:

```text
trip_snapshot
trip_lifecycle
connection_lifecycle
driver_request_queue
```

### Broker subprocess

`broker.py` remains a separate process.

Because it does not own the Flask-SocketIO server process, each committed broker
step sends a local-only POST callback to:

```text
POST /trips/internal/stream-publish
```

The Flask process then rebuilds the authoritative MySQL snapshot and broadcasts
it over the existing WebSocket room.

This keeps the browser path asynchronous:

```text
broker.py
   ↓ local process callback
Flask process
   ↓ WebSocket broadcast
trip:<trip_id>
   ├── Driver
   └── Passenger
```

The internal callback accepts loopback requests only.

### Verbose diagnostics

Server logs now include events such as:

```text
[SOCKET CONNECT]
[PASSENGER REGISTER]
[DRIVER REGISTER]
[TRIP JOIN]
[TRIP STREAM PUBLISH]
[BROKER CALLBACK]
[DRIVER QUEUE PUSH]
[TRIP LEAVE]
[SOCKET DISCONNECT]
```

The browser console includes:

```text
[PASSENGER WS] ...
[DRIVER WS] ...
```

Both pages also display a visible socket state pill such as:

```text
Socket connecting
Socket connected
Trip #42 joined
DRIVER_EN_ROUTE • streaming
COMPLETED • closing
Socket disconnected
```

Pickup waiting clocks and dispatch countdowns continue ticking locally from
server timestamps, so they do not require network polling.


## Two-party passenger pickup handshake

The pickup lifecycle is now:

```text
DRIVER_ARRIVED
    ↓
Driver slides "Passenger picked up"
    ↓
PICKUP_PENDING
    ├── pickup_claimed_at stored in MySQL
    ├── cancel_locked_at stored in MySQL
    ├── cancellation endpoint refuses cancellation
    └── passenger receives live WebSocket snapshot
            ↓
Passenger presses "Confirm I Am in the Vehicle"
            ↓
IN_PROGRESS
    ├── pickup_confirmed_at stored in MySQL
    ├── started_at stored
    └── cancellation remains locked
```

The cancellation lock is enforced on the server, not only by disabling the
Passenger button.

New trip columns:

```text
pickup_claimed_at
pickup_confirmed_at
cancel_locked_at
```

The Passenger page also shows the assigned driver's live latitude/longitude,
last GPS update time, and a button to center the map on the driver's current
position.

`PICKUP_PENDING` is treated as an active trip by Passenger and Driver socket
recovery so refreshing either page does not lose the confirmation state.

The required local-only startup is preserved:

```python
if __name__ == "__main__":
    start_broker()
    atexit.register(stop_broker)
    socketio.run(
        app,
        host="127.0.0.1",
        port=5100,
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
```

The broker stream callback also uses:

```text
http://127.0.0.1:5100/trips/internal/stream-publish
```


## Persistent passenger request recovery

A passenger can now have only one active request/trip at a time.

Active states:

```text
REQUESTED
OFFERED
DRIVER_ASSIGNED
DRIVER_EN_ROUTE
DRIVER_ARRIVED
PICKUP_PENDING
IN_PROGRESS
```

The request endpoint checks MySQL before creating a new trip and returns:

```text
409 ACTIVE_TRIP_EXISTS
```

with the existing trip ID if another active request already exists.

For real passenger accounts, the Passenger row is locked during request
creation so two near-simultaneous requests cannot create duplicate active trips.

On page refresh, `register_passenger` finds the active MySQL trip, joins its
Socket.IO room, and immediately pushes an `ACTIVE_TRIP_RECOVERY` snapshot.

The Passenger page rebuilds:

```text
pickup
destination
route
fare
distance
duration
route provider
driver information
trip state
```

from that snapshot.

While an active ride exists, the request button, pickup/destination inputs, GPS
pickup button, and map destination editing are disabled.

After a successful new request, the Passenger page smooth-scrolls directly to
the `TRIP STATUS` card.

Local-only startup remains:

```text
127.0.0.1:5100
```


## Driver offer Pick Up control

The Driver offer UI now uses:

```text
Pick Up
Decline
```

instead of:

```text
Accept Ride
Decline
```

`Pick Up` uses the existing atomic trip-acceptance backend path. It claims the
ride for that driver, closes all other open offers, marks the driver unavailable,
assigns the trip, and starts the pickup simulation pipeline.

The separate passenger-in-vehicle slider still remains later in the lifecycle:

```text
ride offer
   ↓
Pick Up
   ↓
DRIVER_ASSIGNED / DRIVER_EN_ROUTE
   ↓
DRIVER_ARRIVED
   ↓
driver slider: passenger picked up
   ↓
PICKUP_PENDING
   ↓
passenger confirms
   ↓
IN_PROGRESS
```

This keeps `Decline` available on the offer while making the primary action read
like the driver workflow rather than a generic accept button.


## Socket.IO backend auto-detection (Python 3.13)

The app no longer forces gevent. Flask-SocketIO selects an installed backend;
with the supplied requirements in a clean environment, it uses threading and
simple-websocket. Existing optional backends may be selected automatically.
Gevent is not required, and its absence does not make startup diagnostics fail.
Both server and browser clients remain WebSocket-only.

Install and start with the same Python interpreter:

```bash
python3 -m pip install -U -r requirements.txt
python3 app.py
```

For an isolated installation, first run `python3 -m venv .venv` and
`source .venv/bin/activate`, then use the commands above.
The existing MySQL configuration and database are still required.

Startup reports the actual async mode, selected WebSocket driver, Python
version, and dependency versions. Optional gevent may be reported as MISSING.
The server remains local-only at `127.0.0.1:5100`, with debug enabled and the
reloader disabled. The broker callback remains on the same address and port.

References: https://flask-socketio.readthedocs.io/en/latest/api.html and
https://flask-socketio.readthedocs.io/en/stable/intro.html


## Arrival-gated Pick Up button

The main Driver action now changes with the trip lifecycle:

```text
OFFERED
  Accept Ride + Decline
        ↓
DRIVER_ASSIGNED
  Pick Up disabled
        ↓
DRIVER_EN_ROUTE
  Pick Up disabled
        ↓
DRIVER_ARRIVED
  Pick Up enabled
        ↓
driver presses Pick Up
        ↓
PICKUP_PENDING
  Waiting for Passenger
        ↓
passenger confirms
        ↓
IN_PROGRESS
```

`Pick Up` calls the existing `/trips/<trip_id>/pickup-claim` endpoint, so the
database cancellation lock and passenger confirmation handshake remain intact.

Decline is disabled after the driver has already accepted/been assigned the ride.


## Concurrent nearby offers, demo positioning and live timers

This update supersedes the older sequential ETA dispatch descriptions above.
Deleted drivers stay deleted: startup and admin reads no longer seed or repair
missing driver profiles. New driver signups still create their profiles. To
explicitly restore sample drivers, run `python3 seed_demo_drivers.py`.
The Reset Test Drivers button only resets drivers that still exist.

New requests are offered simultaneously to the nearest available, approved,
online drivers inside the configured radius. Defaults are 5 miles, at most 5
drivers, and 20 seconds to accept or reject. There is no exclusive head start.
The first successful acceptance wins; other offers close atomically with the
trip claim. Ignored offers expire in the broker, and the server rejects late
acceptance even before the broker's next tick. If all candidates decline or
expire, the passenger request stays active for cancellation; this version does
not repeatedly offer the same request to drivers who ignored or declined it.

Configure these values in `.env` before startup:

```text
DISPATCH_RADIUS_MILES=5
DISPATCH_MAX_DRIVERS=5
OFFER_RESPONSE_SECONDS=20
```

With `DEMO_MODE=1`, a driver can click the map to save their location. This is
blocked during an assigned trip so it cannot conflict with the broker route.
The server rejects invalid coordinates and rejects this endpoint outside demo
mode. A changed location is used when selecting drivers for subsequent requests.

The admin's Live driver response windows & trip stage times section shows each
offer's response countdown, decision, distance, and each recorded trip stage's
duration. Passenger and driver pages show stage durations too. JavaScript ticks
locally; WebSocket snapshots interrupt and replace the saved timing state.
Refresh/reconnect reloads timestamps from the database. UTC timestamps and
server-clock offsets prevent browser timezone and clock differences from
resetting timers. Existing trips display the timestamps already recorded;
missing historical transitions cannot be reconstructed.

Startup creates the `trip_stage_events` table and adds nullable
`ride_offers.expires_at` through the existing schema updater. Stage transitions
from both the app and broker are saved in the same database transaction as the
status change. Local-only startup and the broker callback remain at
`127.0.0.1:5100`. Run the usual dependency install before startup.

Regression checks:

```bash
python3 tests/test_dispatch.py
node tests/passenger_pipeline.test.cjs
node tests/trip_timing.test.cjs
```

Backend regression tests use isolated SQLite data; MySQL-specific concurrency
and a complete live browser/broker journey still require local integration testing.


## Driver online/offline control

The Driver status card now has Go Offline / Go Online. The choice is saved in
the database and restored after refresh or restart; it is independent of the
WebSocket connection. Offline drivers are excluded from new dispatches and
request queues, and their outstanding offers close immediately. Going offline
during an accepted ride keeps that ride and its live updates running so the
driver can finish it, but prevents new offers. Going online during a ride does
not make the driver available for another one. Going online requires approval.
Explicit admin reset/demo positioning tools retain their existing behavior.


## Linear distance dispatch (current behavior)

This replaces the simultaneous offer behavior described above. In Admin,
Distance-based offer timing provides saved radius, expansion-time, and
response-time controls. Defaults remain 5 miles, with 20 seconds to expand and
20 seconds to respond after an offer opens. All available, approved, online
drivers within the radius participate; the old five-driver cap no longer applies.

For distances measured when a request is created:

```
fraction = (distance - nearest_distance) / (farthest_distance - nearest_distance)
eligible_at = dispatch_started_at + fraction * expansion_seconds
```

Thus nearest = 0 (immediate), farthest = 1 (full expansion time), and intermediate
drivers open proportionally to distance, not list position or pickup ETA.
Example: 1, 2, 5 miles with 20 seconds expands at 0, 5, 20 seconds. Equal-distance
nearest drivers all open immediately; a single driver opens immediately. An
expansion time of zero offers to all candidates immediately.

Distances, fractions, and eligibility timestamps are saved per offer. Changes
to admin settings affect new requests, leaving existing schedules stable. A
rejection does not skip ahead in the distance schedule. Drivers only see a
request once their offer is open. Offline or busy drivers are skipped at unlock.
The first acceptance still wins and closes all remaining offers.

The existing broker activates due offers on its next tick (so actual delivery
can lag the eligibility timestamp slightly). Each activated driver receives
the saved full response window, even after a delayed broker tick. The admin
shows the 0–1 fraction, countdown to opening, and then countdown to respond.
This timing is independent of the trip stage duration counters.

New schema: `dispatch_settings` plus nullable `ride_offers.distance_fraction`
and `ride_offers.response_seconds`. The existing startup schema updater applies
these additions. Existing offer deadlines are preserved.


## Admin platform map and driver randomization

The admin map shows every driver profile, including offline drivers, plus
passenger locations. Passenger markers use the latest reported passenger
position for the latest trip when available; otherwise they use the trip's
pickup point, explicitly labeled as not live GPS. People without coordinates
(including admin accounts) are listed below the map rather than placed at an
invented location. Driver accounts linked to a driver profile are not duplicated.

Click the map to set a randomization center, enter a radius in miles, then click
Randomize driver locations. In demo mode this saves random positions within
that radius for existing idle drivers, preserving online/offline and approval
status. Drivers serving trips are skipped; deleted drivers are never recreated.
The action updates driver pages and admin maps over WebSocket. Existing offer
schedules remain fixed; the new positions affect subsequent dispatch plans.

Map snapshots refresh on connection/reconnection and on trip, location,
availability, account creation, and deletion events. The Show everyone button
fits known positions into view without forcing the map to recenter on every
location update. Marker popups identify the person, state, location source,
and timestamp. Basemap tiles and Leaflet use the existing internet/CDN model.

Validated with isolated SQLite regression tests and a live local browser:
admin markers rendered, WebSocket updates arrived, and the randomize button
moved test drivers. MySQL-specific concurrency remains untested here.


## Repeated fare escalation after final driver

Admin dispatch settings now include:

```text
Final driver's response wait (seconds)
Fare increase multiplier
```

Defaults:

```text
final driver wait = 30 seconds
fare multiplier = 1.25x
```

The database-backed lifecycle is:

```text
normal driver dispatch
        ↓
last ranked driver becomes OFFERED
        ↓
admin-configured final-driver timer starts
        ↓
last driver's offer remains valid for the full timer
        ↓
no driver accepts
        ↓
fare_escalations row created as PENDING
        ↓
Passenger sees:
  original fare
  multiplier
  proposed new fare
        ↓
Passenger approves
        ↓
trip.estimated_fare updated in MySQL
        ↓
drivers are offered the trip again
        ↓
last-driver timer starts again
        ↓
repeat until passenger stops or a driver accepts
```

The original offer is stored separately in:

```text
trips.original_estimated_fare
```

The current approved fare is stored in:

```text
trips.estimated_fare
```

The accepted escalation round is stored in:

```text
trips.fare_round
```

Each passenger decision is retained in:

```text
fare_escalations
```

with:

```text
trip_id
round_number
original_fare
multiplier
offered_fare
status
prompted_at
responded_at
```

Repeated fare calculations are based on the original offer:

```text
round 0 = original
round 1 = original × multiplier
round 2 = original × multiplier²
round 3 = original × multiplier³
...
```

This prevents each calculation from using an already-rounded previous fare.

If the passenger chooses `Stop Searching`, the pending escalation is marked
DECLINED and the ride request is canceled.

The passenger's escalation prompt and countdown are restored after refresh from
the database-backed trip snapshot.

The existing local-only server configuration remains:

```text
127.0.0.1:5100
```


## Multi-driver dispatch repair

The dispatch plan now explicitly logs every eligible driver inside the admin
radius and every later `WAITING -> OFFERED` transition.

In demo mode, startup also reconciles the five persistent test-driver rows:

```text
online = true
available = true
```

unless a driver is genuinely assigned to an active trip. This prevents an old
test session from leaving several demo drivers unavailable in MySQL and causing
a new request to have only one candidate.

When the broker activates a later-ranked driver, the Flask process now pushes
both:

```text
ride_offer
driver_request_queue
```

to that driver's Socket.IO room.

Expected server logs for a five-driver request look like:

```text
[DISPATCH PLAN] trip=... candidates=5
[DISPATCH CANDIDATE] rank=1 driver=...
[DISPATCH CANDIDATE] rank=2 driver=...
...
[DISPATCH SCHEDULED] rank=1 ... status=OFFERED
[DISPATCH SCHEDULED] rank=2 ... status=WAITING
...
[DISPATCH OFFER ACTIVATED] rank=2 driver=...
[DRIVER OFFER PUSH] trip=... driver=... status=OFFERED
```

If `candidates=1`, the remaining drivers are not eligible for that request
because of radius, online, availability, verification, or active-trip state.


## Sequential normalized-distance dispatch

Driver ranking now uses exactly:

```text
driver_fraction = driver_distance / farthest_driver_distance
```

Example for a 10-mile farthest driver:

```text
2 miles  -> 0.20
5 miles  -> 0.50
7 miles  -> 0.70
10 miles -> 1.00
```

The smallest fraction is offered first.

Only one driver is `OFFERED` at a time:

```text
0.20 offered
    ↓ timer expires
0.50 offered
    ↓ timer expires
0.70 offered
    ↓ timer expires
1.00 offered
    ↓ final-driver admin timer expires
admin alert: no driver in the configured area accepted
```

WAITING drivers no longer have independent pre-calculated activation times.
The next driver is promoted only after the current driver's timer fails or the
current driver declines.

Non-final drivers use the admin `response_seconds` timer.

The final `1.00` driver uses the admin `last_driver_wait_seconds` timer.

When the final driver fails, the trip stores:

```text
trips.no_driver_admin_notified_at
```

and the main Flask process emits:

```text
admin_dispatch_alert
```

to the Admin dashboard. The alert is also reconstructed from MySQL after an
Admin-page refresh, so it is not dependent on catching a one-time socket event.

The existing fare-escalation flow still begins after final-driver exhaustion.

Local-only startup remains:

```text
127.0.0.1:5100
```


## Count-up expansion fix

The distance ranking stays unchanged:

```text
driver_fraction = driver_distance / farthest_driver_distance
```

Example:

```text
2 / 10  = 0.20
5 / 10  = 0.50
7 / 10  = 0.70
10 / 10 = 1.00
```

The timer input is now inverted before it enters the linear expansion:

```text
remaining = total_timer - raw_elapsed
elapsed   = total_timer - remaining
expansion = elapsed / total_timer
```

So the search starts small and expands outward:

```text
elapsed 0%   -> expansion 0.00
elapsed 20%  -> expansion 0.20
elapsed 50%  -> expansion 0.50
elapsed 70%  -> expansion 0.70
elapsed 100% -> expansion 1.00
```

A driver's existing distance fraction is compared to the count-up expansion.
Once the count-up reaches that fraction, the driver becomes eligible.

The expansion fraction is intentionally not capped after the configured timer:

```text
elapsed 120% -> expansion 1.20
elapsed 150% -> expansion 1.50
```

That leaves the scale ready for a later feature that searches beyond the
original farthest-driver reference distance.

The admin live view now shows:

```text
search count-up seconds
remaining countdown seconds
current expansion fraction
```

The server also logs each tick as:

```text
[DISPATCH COUNTUP] remaining=... elapsed=... total=... expansion=...
```

and outward activations as:

```text
[DISPATCH EXPAND OUTWARD] ... fraction=... countup=...
```

Local-only startup remains:

```text
127.0.0.1:5100
```


## Accumulating driver offers

Driver eligibility now only expands. An offer never expires because time passed.

The distance calculation remains:

```text
driver_fraction = driver_distance / farthest_driver_distance
```

The search threshold remains the count-up:

```text
elapsed = total_timer - remaining_timer
expansion = elapsed / total_timer
```

The resulting behavior is:

```text
closest driver offered immediately

count-up reaches next driver's fraction
    -> that driver is added
    -> previous driver keeps the offer

count-up reaches another driver's fraction
    -> that driver is added
    -> every earlier eligible driver still has the offer

count-up reaches 1.0
    -> all known eligible drivers have the offer
    -> admin-configured full-area grace timer starts

grace timer ends with no acceptance
    -> admin dashboard gets "no driver accepted"
    -> passenger gets the fare-escalation decision
```

There is no timer-driven `OFFERED -> EXPIRED` transition.

A driver stops having an offer only when:

```text
the driver declines
another driver accepts the trip
the passenger cancels
a passenger-approved fare increase starts a new search round
```

For compatibility with an existing database, old rows left in `EXPIRED` by
earlier versions are repaired back into the current WAITING/OFFERED lifecycle
the next time that trip is processed.

The expansion value remains intentionally able to grow past `1.0`, leaving the
search function ready to extend beyond the original farthest-driver reference
later.


## Passenger-centered expanding radius

The search is now centered on the passenger pickup point.

The admin setting:

```text
Passenger search radius limit (miles)
```

is the actual denominator for driver eligibility.

Example with a 10-mile limit:

```text
driver 2 miles away  -> 2 / 10 = 0.20
driver 5 miles away  -> 5 / 10 = 0.50
driver 7 miles away  -> 7 / 10 = 0.70
driver 10 miles away -> 10 / 10 = 1.00
```

The passenger search radius grows linearly from 0 to the configured limit:

```text
current_radius = radius_limit * elapsed_fraction
```

The elapsed fraction comes from the count-up conversion:

```text
remaining = total_time - raw_elapsed
elapsed   = total_time - remaining
fraction  = elapsed / total_time
```

A driver becomes OFFERED when:

```text
driver_distance <= current_search_radius
```

Offers accumulate and do not expire:

```text
2 mile driver gets offer
2 mile driver keeps offer

radius reaches 5 miles
2 mile + 5 mile drivers have offer

radius reaches 7 miles
2 + 5 + 7 mile drivers have offer
```

Every driver in a search round receives the same passenger-approved fare.

When the radius reaches the admin limit:

```text
expansion pauses
existing eligible drivers keep the offer
full-radius pause timer starts
```

If nobody accepts by the end of the pause, the existing fare-escalation flow
asks the passenger whether to approve a higher fare.

A driver who accepts after the passenger has approved a higher-fare round sees
a warning before acceptance. The objective event is stored on the driver
account as:

```text
drivers.fare_increase_accept_count
drivers.last_fare_increase_accept_at
```

The system records that the driver accepted an increased-fare round; it does
not attempt to infer the driver's motive.

The passenger map includes a growing search-radius circle centered on the
pickup point. Trip status shows:

```text
current search radius
configured radius limit
number of drivers currently holding the same fare offer
```

Local-only startup remains:

```text
127.0.0.1:5100
```


## Radius step per timer

The admin field previously labeled as a passenger search radius limit now means:

```text
Passenger search radius increase per timer (miles)
```

It is an increment, not a maximum.

Example:

```text
radius increase = 5 miles
timer interval = 20 seconds
```

The search behaves as:

```text
0-19.999 seconds   -> 0 mile radius
20-39.999 seconds  -> 5 mile radius
40-59.999 seconds  -> 10 mile radius
60-79.999 seconds  -> 15 mile radius
80-99.999 seconds  -> 20 mile radius
...
```

A driver is offered the same passenger fare when:

```text
driver_distance <= current_search_radius
```

Previously offered drivers keep the offer. There is no offer expiration caused
by the expansion timer.

The radius is not capped by the increase setting. It can continue to:

```text
5 -> 10 -> 15 -> 20 -> 25 -> ...
```

until all currently known drivers in the search plan have been reached.

After all currently known drivers have been reached, the existing admin pause
timer begins. If nobody accepts during that pause, the existing admin alert and
passenger fare-escalation flow can run.


## Dynamic driver discovery

The active passenger search no longer depends only on the driver locations
captured when the ride request was first created.

On every broker dispatch tick, PIPELINE 03A now:

```text
reads all currently online + available + approved drivers
recalculates each driver's live distance from the passenger pickup
updates WAITING offer distances
adds drivers that did not exist in the original trip offer plan
re-opens eligible drivers that were previously CLOSED but became available
checks the refreshed distance against the current passenger search radius
```

That fixes this case:

```text
ride starts
driver is outside the current search area
search radius expands
driver moves closer
next dispatch tick recalculates driver distance
driver is now inside current radius
driver becomes OFFERED immediately
passenger offer count increases
driver Socket.IO queue receives the ride
```

It also fixes drivers that come online after the passenger already requested
the ride.

Offers that are already OFFERED remain active and do not expire.


## Always-running proximity service

Dispatch matching now runs as an independent database service inside
`broker.py`. It does not require a passenger or driver browser action.

Every broker tick:

```text
PIPELINE 09A
    active passenger requests
        x
    current online + available + approved drivers
        ↓
    recalculate live passenger-to-driver distance
        ↓
    compare with passenger's current expanding search radius
        ↓
    persist RideOffer in MySQL
        ↓
    WAITING -> OFFERED when inside radius
        ↓
    callback to Flask web process
        ↓
    passenger + driver Socket.IO notifications
```

This behaves like a simple boid/proximity broad-phase: active passenger search
areas are continuously compared against live driver positions stored in the
database.

Drivers are not limited to the original request-time snapshot. A driver can:

```text
move into range later
come online later
become available later
be created after the passenger request
```

and the next broker proximity tick can add that driver to the search.

When a driver becomes OFFERED, the persisted trip snapshot contains:

```text
dispatch.reviewing_drivers
```

Each entry includes the driver id/name, current pickup distance, offer time,
and the fare being reviewed.

The passenger UI shows those drivers as:

```text
DRIVERS REVIEWING YOUR OFFER
```

and receives a live `drivers_reviewing_offer` event when a new driver enters
the current search radius.

The driver receives:

```text
review_fare
```

plus the normal database-backed driver request queue. The alert says:

```text
Review Fare • $X.XX • Y.YY mi from pickup
```

Reviewing the request does not accept it. Acceptance still requires the normal
explicit `Accept Ride` action.

The database remains authoritative across browser refresh/reconnects.


## Pickup confirmation auto-scroll

When the driver marks the passenger as picked up and the trip enters:

```text
PICKUP_PENDING
```

the passenger page now automatically scrolls to:

```text
CONFIRM PICKUP
```

The auto-scroll happens once per trip so repeated Socket.IO snapshots do not
continually pull the passenger back down the page.

While pickup confirmation is pending, the passenger's ride-request controls
remain disabled:

```text
Use My Location
Pickup latitude
Pickup longitude
Destination latitude
Destination longitude
Estimate Ride
Request Ride
```

The confirmation card remains interactive:

```text
Confirm I Am in the Vehicle
I Need Help
```

This preserves the existing pickup confirmation and help-request behavior while
preventing the passenger from starting or editing another ride during the
pickup-confirmation gate.


## Live queue membership and reordering

The passenger search queue is now fully live.

Every broker proximity tick recalculates current driver distance from the
passenger pickup and updates queue membership.

A driver remains `OFFERED` only while:

```text
driver is online
driver is available
driver is approved
driver current distance <= passenger current search radius
```

If an offered driver drives outside the current search radius:

```text
OFFERED -> WAITING
```

That removes the trip from the driver's active offer queue on the next broker
callback. The passenger's `DRIVERS REVIEWING YOUR OFFER` list also drops that
driver.

If the same driver later moves back inside the radius:

```text
WAITING -> OFFERED
```

and the driver gets a new Review Fare notification.

The active queue rank is rebuilt on every tick from current distance:

```text
rank 1 = closest current driver
rank 2 = next closest
rank 3 = next closest
...
```

Movement can therefore reorder the queue even when all drivers remain inside
the search radius.

Explicitly declined offers remain declined for the current fare round and are
not automatically re-added by movement.

The database is still authoritative and both passenger and driver UIs receive
their state from the broker-backed DB updates.


## Authoritative driver availability

The live proximity service no longer trusts `drivers.is_available` by itself.

A driver is now considered available for passenger search when:

```text
driver is online
driver verification_status == APPROVED
driver has a current location
driver is not assigned to an active trip
```

Active assignment states are:

```text
DRIVER_ASSIGNED
DRIVER_EN_ROUTE
DRIVER_ARRIVED
PICKUP_PENDING
IN_PROGRESS
```

The broker repairs `drivers.is_available` from the real assignment state on
every live candidate pass. This prevents stale availability flags from causing
drivers inside the passenger radius to disappear from dispatch.

Broker diagnostics now include:

```text
[DRIVER AVAILABILITY REPAIRED]
[DRIVER SEARCH CANDIDATES]
[PASSENGER SEARCH INVARIANT OK]
[PASSENGER SEARCH INVARIANT FAILED]
```

For every trip, the invariant is:

```text
every online + approved + unassigned driver
whose current DB location is inside the passenger search radius
must be OFFERED unless that driver explicitly declined this fare round
```

Queue ordering remains based on current passenger-to-driver distance and is
rebuilt continuously by the broker.


## Authoritative live-location queue reconciliation

The live queue now uses the `drivers` table location as the source of truth on
every broker proximity tick.

For each active passenger request the broker does:

```text
SELECT current online + approved driver rows
        ↓
refresh rows from MySQL
        ↓
read current_latitude/current_longitude
        ↓
haversine distance to passenger pickup
        ↓
overwrite RideOffer.distance_miles
        ↓
distance <= current search radius ?
        ├─ yes -> OFFERED
        └─ no  -> WAITING
        ↓
sort OFFERED rows by current distance
        ↓
rewrite rank 1, 2, 3...
        ↓
commit
        ↓
push passenger snapshot + driver queues
```

The old request-time pickup distance is not trusted for live membership.

Useful broker logs:

```text
[LIVE QUEUE ENTER]
[LIVE QUEUE LEAVE]
[LIVE QUEUE DISTANCE]
[LIVE QUEUE REMOVE DRIVER]
[LIVE QUEUE SNAPSHOT]
```

`[LIVE QUEUE SNAPSHOT]` includes:

```text
radius
live driver count
inside-radius driver count
OFFERED count
WAITING count
missing driver ids
```

The driver request queue no longer applies a second stale `is_available` gate.
It mirrors authoritative `RideOffer.status == OFFERED` rows after the broker
reconciliation pass.


## Demo map location pipeline

The demo driver map click is now a full dispatch-pipeline test, not only a UI
marker change.

Each click performs:

```text
driver clicks map
    ↓
POST /drivers/<driver_id>/demo-location
    ↓
validate latitude/longitude
    ↓
write drivers.current_latitude/current_longitude
    ↓
COMMIT MySQL
    ↓
expire ORM cache
    ↓
run process_proximity_service immediately
    ↓
recompute pickup distance from committed DB coordinates
    ↓
inside search radius?
    ├─ yes -> OFFERED
    └─ no  -> WAITING
    ↓
re-rank OFFERED rows by current distance
    ↓
publish passenger snapshot
    ↓
refresh all affected driver queues
    ↓
emit Review Fare when a driver newly enters
```

The driver page immediately moves its own marker to the exact coordinates
returned by the server.

After each click the demo status line also shows the authoritative result:

```text
Trip #12: OFFERED • 2.31 mi / 5.00 mi radius • rank #1
```

or:

```text
Trip #12: WAITING • 7.42 mi / 5.00 mi radius • rank #4
```

This makes queue entry/exit testable directly from the browser while the normal
broker subprocess continues running in parallel.


## Modular dispatch refactor

Dispatch and location handling were split into smaller domain modules so local
AI agents do not need to load the old monolithic `app/trips/services.py`.

`app/trips/services.py` is now only a compatibility facade. Existing routes and
imports keep working while the actual implementations live under
`app/dispatch/`, `app/location/`, and focused trip service modules.

See `ARCHITECTURE.md` for the module map and demo/production location pipeline.


## Driver preview route

The driver-side "Preview Route" button now requests a shared preview payload from:

```text
GET /drivers/<driver_id>/trips/<trip_id>/pickup-route
```

That response includes:

1. the route from the driver's current location to pickup; and
2. the passenger's trip route from pickup to destination.

For privacy, the driver map does **not** render a passenger marker. The pickup
point is only implied by the join between the two route segments.


## Two-phase broker trip movement

Accepted rides now use two explicit broker movement phases:

```text
TO_PICKUP
    driver presses Start Driving
    broker moves driver along pickup route
    passenger remains at pickup
    ↓
DRIVER_ARRIVED
    driver marks passenger picked up
    ↓
PICKUP_PENDING
    driver cannot continue
    passenger must confirm "I Am in the Vehicle"
    ↓
IN_PROGRESS
    destination route is prepared
    driver presses Continue Ride
    ↓
TO_DESTINATION
    broker moves driver and passenger together
    ↓
COMPLETED
    passenger survey appears
    driver survey appears
```

The server enforces the pickup-confirmation gate. Calling the broker start
endpoint during `PICKUP_PENDING` returns an error until the passenger has
confirmed pickup.

During `TO_DESTINATION`, every broker step:

```text
updates drivers.current_latitude/current_longitude
updates trips.passenger_current_latitude/passenger_current_longitude
writes a driver LocationUpdate
writes a passenger LocationUpdate
publishes a fresh trip snapshot
```

This makes both user interfaces move from the same broker-controlled route.

## After-ride surveys

Completed trips expose a separate survey to the passenger and driver.

Surveys are persisted in:

```text
ride_surveys
```

Each survey stores:

```text
trip_id
role
actor_id
rating
comments
created_at
```

The survey endpoint is:

```text
POST /surveys/trips/<trip_id>
```

Surveys are rejected until the trip status is `COMPLETED`.


## Demo motion service split

The broker simulation was split so demo movement is replaceable.

```text
app/broker/services.py
    normal validation + state transitions

app/broker/demo_service.py
    fake/boid-style route motion only
```

Passenger pickup confirmation no longer creates a demo route directly. It only
sets the real trip to `IN_PROGRESS`.

When the demo driver later presses `Continue Ride`, normal broker services
validate that pickup was confirmed and only then ask `demo_service.py` to build
and run the destination simulation.

With:

```text
DEMO_MODE=0
```

the broker does not advance fake movement jobs and the demo motion HTTP
endpoints reject simulation requests. This allows a future production location
provider to update real driver/passenger movement without changing the normal
validation rules.


## DB-event broker

The broker no longer recalculates dispatch, fare logic, and demo movement on
every timer loop.

Broker work is now persisted in:

```text
broker_events
```

The subprocess only checks for due `PENDING` event rows. If there is no event,
it does no dispatch, fare, proximity, or motion work.

Important event types:

```text
DEMO_STEP
PROXIMITY_RECONCILE
DISPATCH_RECHECK
```

### Demo movement

Pressing `Start Driving` writes the first `DEMO_STEP` event.

The broker consumes one event, validates the job through normal broker
services, advances exactly one fake GPS point through `demo_service.py`,
commits the driver/passenger coordinates, then writes exactly one next
`DEMO_STEP` event with `due_at` based on `step_interval_seconds`.

This creates a sequential chain:

```text
DB event
  -> validate
  -> one route point
  -> DB commit
  -> next DB event
```

The destination leg uses the same chain, so it no longer competes with a
global simulation timer.

### Search/dispatch

Driver location writes enqueue `PROXIMITY_RECONCILE`.

New ride requests and accepted fare-increase rounds enqueue
`DISPATCH_RECHECK` rows. Each completed search/fare check schedules the next
future DB event only when another timed check is required.

This preserves timed radius expansion without recalculating every active trip
on every idle broker loop.


## Flat broker scheduler

The recursive broker-event chain was removed.

There is no runtime `broker_events` queue and no broker handler enqueues
another broker handler.

The scheduler now reads due state directly from authoritative rows:

```text
simulation_jobs.next_due_at
trips.next_dispatch_at
trips.fare_wait_until
```

### Demo motion

```text
Start Driving
    ↓
normal service sets:
    SimulationJob.status = RUNNING
    SimulationJob.next_due_at = now
    ↓
broker read-only scan sees due job
    ↓
normal validation
    ↓
demo_service advances exactly one route point
    ↓
same DB transaction updates coordinates/progress
    ↓
SimulationJob.next_due_at = now + step_interval
```

No function calls itself and no motion step creates another work-item row.

Pause sets:

```text
next_due_at = NULL
```

Resume sets:

```text
next_due_at = now
```

Completion sets:

```text
status = COMPLETED
next_due_at = NULL
```

### Search / proximity

A driver location or availability write marks active searches due by setting:

```text
trips.next_dispatch_at = now
```

The broker later reconciles those due trips. Dispatch code then writes the
next real search threshold into `next_dispatch_at`.

Fare grace uses `fare_wait_until` directly.

The broker's idle loop only performs read-only queries for rows whose persisted
due timestamps have arrived. If nothing is due, it performs no business-state
write.

`next_due_at` is also included in the simulation API/live snapshot so the
currently scheduled trigger is visible for debugging.


## Driver drop-off phase UI

After passenger pickup confirmation, the driver card changes phase from:

```text
DRIVER TO PASSENGER
```

to:

```text
DRIVER TO DROPOFF
```

Before the second phase starts:

```text
Passenger confirmed — ready for drop-off
Continue Ride
```

While the demo broker is advancing the destination route:

```text
Driving to drop-off…
Drop-off progress XX% • ETA N min
```

The destination leg remains broker-controlled. `demo_service.py` updates both
driver and passenger coordinates on every `TO_DESTINATION` step, commits those
coordinates, and advances `SimulationJob.next_due_at` for the next flat
scheduler pass.


## Drop-off state repair

The driver UI and broker now use `simulation.phase` as the authoritative
movement phase.

A valid running `TO_DESTINATION` job with a confirmed pickup will repair a
stale trip status back to `IN_PROGRESS` instead of stopping the destination
scheduler.

This prevents mixed snapshots such as:

```text
simulation.phase = TO_DESTINATION
trip.status = DRIVER_EN_ROUTE
```

from freezing the drop-off route.

The driver UI also gives destination phase precedence over stale pickup status,
so the cards show:

```text
DRIVER TO DROPOFF
Driving to drop-off…
Drop-off progress XX% • ETA N min
```

and the pickup card remains confirmed.

A `RUNNING` simulation job with `next_due_at = NULL` is treated as due now by
the flat scheduler. `PAUSED` jobs remain stopped, because only `RUNNING` jobs
are repaired this way.


## Pickup confirmation race fix

Passenger confirmation is now authoritative at the database boundary.

When the passenger confirms pickup, the same transaction:

```text
locks Trip
locks current SimulationJob
sets pickup_confirmed_at
sets trip.status = IN_PROGRESS
retires any TO_PICKUP job
clears SimulationJob.next_due_at
commits once
```

A `TO_PICKUP` demo motion step also has a hard guard: if
`pickup_confirmed_at` already exists, it is forbidden from writing
`DRIVER_EN_ROUTE`.

`Continue Ride` now keys primarily on `pickup_confirmed_at`, not a possibly
stale trip status. If the confirmation timestamp exists but the status was
overwritten by an older pickup write, normal broker services repair the status
to `IN_PROGRESS` and prepare the destination phase.

Movement snapshots no longer fan out queue refreshes to every historical
RideOffer driver. Search/offer queue fan-out only occurs for `REQUESTED` and
`OFFERED` trips.

The broker also uses a macOS/Linux advisory singleton lock and logs a build
identifier on startup:

```text
pickup-confirmation-race-fix-v1
```

If runtime logs still show the older reason `BROKER_LOCATION_PROGRESS` instead
of `DEMO_BROKER_LOCATION_PROGRESS`, an older broker process/project is still
running and should be stopped before testing this build.


## Dual broker ticks

The broker now has two isolated scheduler lanes.

### 1. Simulation tick

```text
SIMULATION_TICK_SECONDS
```

Owns only demo movement:

```text
SimulationJob due
    -> validate simulation job
    -> advance one demo route point
    -> update driver/passenger coordinates
    -> update progress / ETA
    -> commit
    -> publish SIMULATION_TICK snapshot + passenger notice
```

It does not read or update RideOffer matching/search membership.

### 2. Boid collision / match tick

```text
COLLISION_TICK_SECONDS
```

Owns only passenger-search geometry and queue membership.

A trip becomes collision-dirty when:

```text
rider creates request
driver position changes
driver availability changes
driver declines
fare round restarts
driver becomes available after completing another ride
```

The lane also wakes when the passenger search radius reaches its next timed
expansion point or fare-wait timing is due.

```text
collision_dirty / radius due
    -> read current driver DB positions
    -> distance/collision check
    -> add drivers entering radius
    -> remove drivers leaving radius
    -> rerank OFFERED queue
    -> commit
    -> publish COLLISION_TICK snapshot + passenger notices
```

Once a driver accepts:

```text
collision_dirty = false
next_dispatch_at = null
fare_wait_until = null
```

and that trip can no longer enter the collision/search lane.

## Passenger step notices

Every broker/lifecycle step is also persisted in `trip_notices` and emitted as:

```text
passenger_step
```

Examples:

```text
Ride requested. Checking nearby drivers.
A driver position changed. Rechecking your search area.
A driver entered your current search area and can review the fare.
A driver left your current search area or became unavailable.
Search check complete: 2 drivers reviewing • radius 5.0 mi.
Driver approaching pickup — 34.3% • ETA 1 min.
Your driver arrived at the pickup point.
Pickup confirmed. The driver may now continue to the drop-off.
Driving to drop-off — 48.6% • ETA 2 min.
You reached the drop-off. The ride is complete.
```

The passenger page has a persistent **Ride Updates** timeline. Notices have a
monotonic per-trip sequence number so reconnecting clients can recover the
ordered history from the trip snapshot.


## Admin-capped passenger search radius

Dispatch now expands on the broker interval until `max_radius_miles` from the admin Dispatch Settings page. A fare increase resets `dispatch_started_at`, so the search returns to the smallest radius and expands again. The admin platform map renders active passenger search-radius circles.

The passenger fare-increase question is removed immediately after a successful action and replaced by a short confirmation that the new fare was applied and the nearby-driver search restarted.
# Chair
