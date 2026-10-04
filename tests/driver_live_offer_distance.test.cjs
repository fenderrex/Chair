const fs = require('fs');
const path = require('path');
const assert = require('assert');

const root = path.resolve(__dirname, '..');
const driverJs = fs.readFileSync(path.join(root, 'app/static/js/driver.js'), 'utf8');
const serializationPy = fs.readFileSync(path.join(root, 'app/dispatch/serialization.py'), 'utf8');

assert(
  driverJs.includes('loadActiveRequests().catch(() => {});'),
  'driver_location should immediately refresh the authoritative driver queue'
);
assert(
  serializationPy.includes('live_driver_distance_miles = haversine_miles('),
  'driver request serialization should calculate distance from the current Driver row'
);
assert(
  serializationPy.includes('"driver_distance_miles": (') &&
  serializationPy.includes('live_driver_distance_miles,'),
  'serialized driver_distance_miles should use the live distance'
);
assert(
  serializationPy.includes('estimate_pickup_eta_seconds(\n                live_driver_distance_miles'),
  'pickup ETA should follow the live distance too'
);

console.log('Driver Review Fare distance follows live driver position: OK');
