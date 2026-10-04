const fs = require('fs');
const assert = require('assert');

const settings = fs.readFileSync('app/admin/settings.py', 'utf8');
const radius = fs.readFileSync('app/dispatch/radius.py', 'utf8');
const queue = fs.readFileSync('app/dispatch/queue.py', 'utf8');
const adminMap = fs.readFileSync('app/static/js/admin-map.js', 'utf8');
const passenger = fs.readFileSync('app/static/js/passenger.js', 'utf8');
const template = fs.readFileSync('app/templates/admin.html', 'utf8');

const stream = fs.readFileSync('app/trips/stream.py', 'utf8');

assert(settings.includes('max_radius_miles'));
assert(template.includes('Maximum passenger search radius'));
assert(radius.includes('search_radius = min('));
assert(radius.includes('\"radius_capped\": radius_capped'));
assert(queue.includes('not clock[\"radius_capped\"]'));
assert(adminMap.includes('const searchCircles = new Map()'));
assert(adminMap.includes('search_radius_miles'));
assert(adminMap.includes('L.circle([lat, lng]'));
assert(passenger.includes('function hidePassengerAlert()'));
assert(passenger.includes('Nearby-driver search restarted from the smallest radius.'));

assert(stream.includes('"radius_capped": ('));
assert(stream.includes('"max_search_radius_miles": ('));
assert(passenger.includes('const maxSearchRadiusReached ='));
assert(passenger.includes('dispatch.radius_capped === true'));
assert(passenger.includes('!maxSearchRadiusReached'));
assert(passenger.includes('Maximum search radius reached at'));

console.log('Search cap, admin map radius, and fare action UI: OK');
