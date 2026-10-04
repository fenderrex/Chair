const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const source = fs.readFileSync('app/static/js/lifecycle-ui.js', 'utf8');
const context = {
  window: { localStorage: { getItem: () => null, setItem: () => {} } },
  document: {
    querySelectorAll: () => [],
    querySelector: () => null,
    body: { classList: { toggle: () => {} }, dataset: {} },
  },
  Set, Object, String, Number, Boolean, Date,
};

vm.createContext(context);
vm.runInContext(source, context);

const resolve = context.window.resolveDriverUiPhase;
const matrix = context.window.DRIVER_UI_MATRIX;
const values = phase => Array.from(matrix[phase]);

assert.equal(resolve({}), 'AVAILABLE');
assert.equal(resolve({trip_id: 1, status: 'REQUESTED'}), 'REVIEW_RIDE');
assert.equal(resolve({trip_id: 1, status: 'OFFERED'}), 'REVIEW_RIDE');
assert.equal(resolve({trip_id: 1, status: 'DRIVER_ASSIGNED'}), 'RIDE_ACCEPTED');
assert.equal(resolve({trip_id: 1, status: 'DRIVER_EN_ROUTE'}), 'ENROUTE_TO_PICKUP');
assert.equal(resolve({trip_id: 1, status: 'DRIVER_ARRIVED'}), 'DRIVER_ARRIVED');
assert.equal(resolve({trip_id: 1, status: 'PICKUP_PENDING'}), 'WAITING_PASSENGER_CONFIRM');
assert.equal(resolve({trip_id: 1, status: 'IN_PROGRESS'}), 'ENROUTE_TO_DROPOFF');
assert.equal(resolve({trip_id: 1, status: 'COMPLETED'}), 'DROPOFF');
assert.equal(resolve({trip_id: 1, status: 'CANCELED'}), 'AVAILABLE');

assert.deepEqual(values('AVAILABLE'), ['driver-status', 'ride-requests']);
assert.deepEqual(values('REVIEW_RIDE'), ['driver-status', 'ride-requests', 'ride-offer']);
assert.deepEqual(values('RIDE_ACCEPTED'), ['driver-status', 'active-ride', 'route-controls', 'message-passenger']);
assert.deepEqual(values('ENROUTE_TO_PICKUP'), ['driver-status', 'active-ride', 'route-controls', 'message-passenger']);
assert.deepEqual(values('DRIVER_ARRIVED'), ['driver-status', 'active-ride', 'passenger-pickup', 'message-passenger']);
assert.deepEqual(values('WAITING_PASSENGER_CONFIRM'), ['driver-status', 'active-ride', 'route-controls', 'passenger-pickup', 'message-passenger']);
assert.deepEqual(values('ENROUTE_TO_DROPOFF'), ['driver-status', 'active-ride', 'route-controls', 'message-passenger']);
assert.deepEqual(values('DROPOFF'), ['driver-status', 'active-ride', 'message-passenger', 'after-ride-survey']);

const html = fs.readFileSync('app/templates/driver.html', 'utf8');
for (const key of new Set(Object.values(matrix).flatMap(set => Array.from(set)))) {
  assert(html.includes(`data-driver-ui="${key}"`), `Missing driver UI card: ${key}`);
}

console.log('Driver UI lifecycle matrix: OK');
