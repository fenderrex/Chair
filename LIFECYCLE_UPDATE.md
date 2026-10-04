# RideShare UI Lifecycle Update — 2026-09-24

The passenger and driver interfaces now use separate presentation-phase matrices. These UI phases do not replace or write the authoritative trip state machine; they only decide which interface DIVs are visible for the current server snapshot.

## Passenger phases
- `SET_LOCATION`
- `LOOKING_FOR_DRIVER`
- `FOUND_DRIVER`
- `ENROUTE_TO_PICKUP`
- `DRIVER_ARRIVED`
- `ENROUTE_TO_DROPOFF`
- `DROPOFF`

The current passenger matrix includes `keep-searching` only during `LOOKING_FOR_DRIVER`, and pickup confirmation only during `DRIVER_ARRIVED`.

## Driver phases
- `AVAILABLE`
- `REVIEW_RIDE`
- `RIDE_ACCEPTED`
- `ENROUTE_TO_PICKUP`
- `DRIVER_ARRIVED`
- `WAITING_PASSENGER_CONFIRM`
- `ENROUTE_TO_DROPOFF`
- `DROPOFF`

The driver page now uses `data-driver-ui` keys and `DRIVER_UI_MATRIX` in `app/static/js/lifecycle-ui.js`, matching the passenger architecture. Driver queue offers project into `REVIEW_RIDE`; accepted-trip Socket.IO snapshots project the remaining phases.

At `DRIVER_ARRIVED`, the `PASSENGER PICKUP` card contains the dedicated `Pick Up Passenger` control. After the driver records pickup, `PICKUP_PENDING` projects to `WAITING_PASSENGER_CONFIRM`. The destination controls do not become actionable until the passenger confirmation advances the trip to `IN_PROGRESS`.

## Demo history switch
Normal mode uses the matrices to show only the DIVs enabled for the current phase. Demo history can still show all matrix-controlled DIVs for debugging. Both passenger and driver default to normal mode unless a browser has a previously saved lifecycle-mode preference.

## Architecture rule
MySQL/server state remains authoritative. The UI lifecycle never advances a trip by itself. Existing buttons continue to call the server routes/events, and Socket.IO snapshots update the presentation phase.

## Explicit driver arrival

Pickup arrival is now a driver-confirmed transition. Completing the demo route leaves the trip in `DRIVER_EN_ROUTE`; the driver must press **Arrived at Pickup**. That action records `driver_arrived_at`, changes the trip to `DRIVER_ARRIVED`, publishes the trip snapshot, and starts the passenger **DRIVER AT PICKUP** waiting clock. Only after that transition does **Pick Up Passenger** become available.


## Passenger pickup wait clock

- `driver-at-pickup` is shown only in the passenger `DRIVER_ARRIVED` phase, not `FOUND_DRIVER` or `ENROUTE_TO_PICKUP`.
- The driver `Arrived at Pickup` action records `driver_arrived_at` and starts the passenger wait clock.
- The browser clock uses the server-provided `pickup_wait_seconds` as its baseline and advances locally once per second, so frequent Socket.IO snapshots cannot freeze it at `00:00`.
- Arrival timestamps are serialized with an explicit UTC offset to avoid browser local-time interpretation of MySQL's timezone-naive UTC datetimes.

## Driver WAITING offer state and fare-round reset

A `RideOffer.status == "WAITING"` is a broker/search state, not a driver response.
The driver knows the request exists, but Accept/Decline stay locked until the
current search radius reaches that driver's current pickup distance.

Driver offer flow:

`WAITING -> OFFERED -> ACCEPTED | DECLINED`

When the passenger approves a higher fare, the trip starts a new fare round:

1. The fare is updated.
2. `dispatch_started_at` is reset to the approval time.
3. The current search radius therefore returns to the smallest radius (0 miles
   before the first configured expansion interval).
4. Existing non-closed driver offer rows are preserved and reset to `WAITING`.
   Old `DECLINED` rows are eligible to participate again because the fare has
   changed.
5. Each waiting row receives a new `eligible_at` calculated from the driver's
   last known pickup distance, the admin radius step, and the admin expansion
   interval.
6. The normal broker collision lane continues expanding the radius from the
   reset timestamp. The broker alone changes `WAITING -> OFFERED` when the
   driver is actually inside the authoritative radius.

The driver UI keeps the request visible in `WAITING`, shows the new fare,
current radius, distance/required radius, passenger's current offered-driver
count, and a server-synchronized countdown to `eligible_at`. Accept/Decline and
route preview remain locked until the broker publishes `OFFERED`.

The admin live view shows OFFERED, WAITING, DECLINED and CLOSED counts plus each
individual offer row and WAITING eligibility countdown.

## Search-cap and fare-action UI update

- Dispatch settings now include a maximum passenger search radius.
- Radius expansion continues on every broker interval until that maximum is reached.
- WAITING drivers remain visible only when they are inside the round's maximum search area and are waiting for the current radius to reach them.
- Admin map displays active passenger search-radius circles.
- After a passenger presses Increase Fare & Keep Searching, the old persistent fare question is hidden immediately, the displayed fare/status update immediately, and a short confirmation states that the nearby-driver search restarted.

## 2026-10-03 — Immediate search radius + live ETA distance
- Added an admin-configured starting passenger search radius (`initial_radius_miles`, default 3.0 mi).
- A new search/fare round now begins at the starting radius immediately instead of 0.00 mi.
- Each timer interval adds the existing radius increment until the configured maximum radius is reached.
- Drivers already inside the starting radius are immediately `OFFERED`; farther in-cap drivers remain `WAITING` until the expanding radius reaches them.
- Higher-fare round resets return to the starting radius, not zero.
- Waiting eligibility timestamps and required-radius calculations now include the starting radius.
- Passenger reviewing-driver distance is recomputed from the driver's current DB coordinates, and pickup ETA is calculated from that same live distance.
- Assigned-driver passenger snapshots also expose live driver-to-pickup distance and ETA from current driver coordinates during pickup phases.
