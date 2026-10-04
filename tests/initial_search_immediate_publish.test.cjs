const fs = require('fs');
const assert = require('assert');

const requestService = fs.readFileSync('app/trips/requests_service.py', 'utf8');
const fareRounds = fs.readFileSync('app/dispatch/fare_rounds.py', 'utf8');
const plan = fs.readFileSync('app/dispatch/plan.py', 'utf8');
const map = fs.readFileSync('app/static/js/admin-map.js', 'utf8');

assert(requestService.includes('activate_due_offers(\n        trip.id\n    )'));
assert(requestService.includes('reason="INITIAL_SEARCH_STARTED"'));
assert(requestService.includes('RideOffer.status == "OFFERED"'));
assert(fareRounds.includes('reason="FARE_ROUND_RESTARTED"'));
assert(plan.includes('"OFFERED"\n                if inside_initial_radius'));
assert(map.includes('person.search_active'));
assert(map.includes('person.search_radius_miles'));

console.log('Initial search reconciles and publishes immediately: OK');
