const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('app/templates/driver.html', 'utf8');
const driverJs = fs.readFileSync('app/static/js/driver.js', 'utf8');
const lifecyclePy = fs.readFileSync('app/trips/lifecycle.py', 'utf8');
const routesPy = fs.readFileSync('app/trips/routes.py', 'utf8');
const demoPy = fs.readFileSync('app/broker/demo_service.py', 'utf8');
const passengerJs = fs.readFileSync('app/static/js/passenger.js', 'utf8');
const streamPy = fs.readFileSync('app/trips/stream.py', 'utf8');

assert(html.includes('id="mark-driver-arrived"'));
assert(html.includes('Arrived at Pickup'));
assert(driverJs.includes('async function markDriverArrived()'));
assert(driverJs.includes('`/trips/${currentTripId}/arrive`'));
assert(driverJs.includes('driverArrivedButton?.addEventListener'));
assert(lifecyclePy.includes('def driver_mark_arrived('));
assert(lifecyclePy.includes('trip.driver_arrived_at = now'));
assert(lifecyclePy.includes('return trip, True'));
assert(routesPy.includes('trip, newly_arrived = driver_mark_arrived('));
assert(routesPy.includes('@bp.post("/<int:trip_id>/arrive")'));
assert(routesPy.includes('reason="DRIVER_MARKED_ARRIVED"'));
assert(demoPy.includes('waiting_for_driver_arrival_confirmation=true'));
assert(!demoPy.includes('[DEMO MOTION ARRIVED PICKUP]'));
assert(passengerJs.includes('["DRIVER_ARRIVED", "PICKUP_PENDING"].includes(snapshot.status)'));
assert(passengerJs.includes('snapshot.pickup_wait_seconds || 0'));
assert(passengerJs.includes('currentPickupWaitSeconds()'));
assert(!passengerJs.includes('new Date(snapshot.driver_arrived_at).getTime()'));
assert(streamPy.includes('\"driver_arrived_at\": iso_utc(trip.driver_arrived_at)'));

console.log('Driver arrival control + passenger wait clock: OK');
