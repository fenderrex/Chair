const fs = require('fs');
const assert = require('assert');

const js = fs.readFileSync('app/static/js/driver.js', 'utf8');
const html = fs.readFileSync('app/templates/driver.html', 'utf8');
const stream = fs.readFileSync('app/drivers/stream.py', 'utf8');
const fareRounds = fs.readFileSync('app/dispatch/fare_rounds.py', 'utf8');
const serialization = fs.readFileSync('app/dispatch/serialization.py', 'utf8');
const routes = fs.readFileSync('app/trips/routes.py', 'utf8');
const adminLive = fs.readFileSync('app/admin/live.py', 'utf8');
const adminJs = fs.readFileSync('app/static/js/admin.js', 'utf8');

assert(html.includes('id="offer-waiting-panel"'));
assert(html.includes('id="offer-waiting-countdown"'));
assert(js.includes('function waitingSecondsRemaining(request)'));
assert(js.includes('function formatClockSeconds(value)'));
assert(js.includes('Passenger is waiting on ${count} driver'));
assert(js.includes('WAITING • offer in'));
assert(js.includes('Waiting ${formatClockSeconds(seconds)}'));
assert(js.includes('waitingPanel.hidden = !waiting'));
assert(js.includes('The nearby-driver search restarted at the smallest radius'));
assert(stream.includes('RideOffer.status.in_(['));
assert(stream.includes('"WAITING"'));
assert(stream.includes('"OFFERED"'));
assert(fareRounds.includes('trip.dispatch_started_at = now'));
assert(fareRounds.includes('offer.status = "WAITING"'));
assert(!fareRounds.includes('RideOffer.query.filter_by(\n        trip_id=trip.id\n    ).delete'));
assert(serialization.includes('"offer_available_at"'));
assert(serialization.includes('"required_radius_miles"'));
assert(serialization.includes('"offered_driver_count"'));
assert(routes.includes('publish_proximity_event(\n        trip.id,\n        reason="PASSENGER_ACCEPTED_FARE_ESCALATION"'));
assert(adminLive.includes('"waiting_driver_count"'));
assert(adminJs.includes('Passenger is waiting on ${offeredCount} driver'));

console.log('Driver WAITING fare-round countdown UI: OK');
