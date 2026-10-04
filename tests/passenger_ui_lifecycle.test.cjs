const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync('app/static/js/lifecycle-ui.js', 'utf8');
const context = {
  window: { localStorage: { getItem: () => null, setItem: () => {} } },
  document: { querySelectorAll: () => [], querySelector: () => null,
    body: { classList: { toggle: () => {} }, dataset: {} } },
  Set, Object, String, Number, Boolean, Date,
};
vm.createContext(context); vm.runInContext(source, context);
const resolve = context.window.resolvePassengerUiPhase;
const matrix = context.window.PASSENGER_UI_MATRIX;
const values = p => Array.from(matrix[p]);
assert.equal(resolve({}), 'SET_LOCATION');
assert.equal(resolve({trip_id:1,status:'REQUESTED'}), 'LOOKING_FOR_DRIVER');
assert.equal(resolve({trip_id:1,status:'OFFERED'}), 'LOOKING_FOR_DRIVER');
assert.equal(resolve({trip_id:1,status:'DRIVER_ASSIGNED'}), 'FOUND_DRIVER');
assert.equal(resolve({trip_id:1,status:'DRIVER_EN_ROUTE'}), 'ENROUTE_TO_PICKUP');
assert.equal(resolve({trip_id:1,status:'DRIVER_ARRIVED'}), 'DRIVER_ARRIVED');
assert.equal(resolve({trip_id:1,status:'PICKUP_PENDING'}), 'DRIVER_ARRIVED');
assert.equal(resolve({trip_id:1,status:'IN_PROGRESS'}), 'ENROUTE_TO_DROPOFF');
assert.equal(resolve({trip_id:1,status:'COMPLETED'}), 'DROPOFF');
assert.deepEqual(values('SET_LOCATION'), ['ride-pipeline','trip-status','trip','estimate']);
assert.deepEqual(values('LOOKING_FOR_DRIVER'), ['ride-pipeline','trip-status','estimate','drivers-reviewing','assigned-driver','ride-updates','keep-searching']);
assert.deepEqual(values('FOUND_DRIVER'), ['ride-pipeline','trip-status','assigned-driver','ride-updates','message-driver']);
assert.deepEqual(values('ENROUTE_TO_PICKUP'), ['ride-pipeline','trip-status','assigned-driver','ride-updates','message-driver']);
assert.deepEqual(values('DRIVER_ARRIVED'), ['trip-status','ride-updates','driver-at-pickup','assigned-driver','confirm-pickup','message-driver']);
assert.deepEqual(values('ENROUTE_TO_DROPOFF'), ['trip-status','assigned-driver','ride-updates','message-driver']);
assert.deepEqual(values('DROPOFF'), ['trip-status','assigned-driver','ride-updates','message-driver','after-ride-survey']);
console.log('Passenger UI lifecycle matrix: OK');
