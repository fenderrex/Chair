const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('app/static/js/passenger.js', 'utf8');
const match = source.match(/function stopPickupWaitTicker\(\) \{[\s\S]*?\n\}\n\nfunction applyPassengerTripSnapshot/);
assert(match, 'pickup wait clock functions were not found');

const functions = match[0].replace(/\n\nfunction applyPassengerTripSnapshot$/, '');
let nowMs = 100000;
let intervalCallback = null;
const clock = { textContent: '' };
const card = { classList: { remove: () => {} } };

const context = {
    pickupWaitTicker: null,
    pickupWaitTickerKey: null,
    pickupWaitBaseSeconds: 0,
    pickupWaitBaseAtMs: 0,
    Date: { now: () => nowMs },
    Math,
    Number,
    String,
    document: {
        querySelector: (selector) => {
            if (selector === '#pickup-wait-card') return card;
            if (selector === '#pickup-wait-time') return clock;
            return null;
        },
    },
    clearInterval: () => {},
    setInterval: (callback) => {
        intervalCallback = callback;
        return 1;
    },
    formatClock: (totalSeconds) => {
        const seconds = Math.max(0, Math.floor(Number(totalSeconds || 0)));
        const minutes = Math.floor(seconds / 60);
        const remainder = seconds % 60;
        return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
    },
};

vm.createContext(context);
vm.runInContext(functions, context);

const snapshot = {
    trip_id: 7,
    status: 'DRIVER_ARRIVED',
    driver_arrived_at: '2026-09-24T22:00:00+00:00',
    pickup_wait_seconds: 0,
};

context.updatePickupWaitFromTimestamp(snapshot);
assert.equal(clock.textContent, '00:00');
assert(intervalCallback, 'wait clock interval was not started');

// Simulate frequent snapshots. They must not restart the local clock.
for (let i = 1; i <= 15; i += 1) {
    nowMs = 100000 + i * 100;
    context.updatePickupWaitFromTimestamp(snapshot);
}
intervalCallback();
assert.equal(clock.textContent, '00:01');

nowMs = 103100;
intervalCallback();
assert.equal(clock.textContent, '00:03');

// A newer server value may move the baseline forward without freezing it.
snapshot.pickup_wait_seconds = 5;
context.updatePickupWaitFromTimestamp(snapshot);
assert.equal(clock.textContent, '00:05');
nowMs = 104200;
intervalCallback();
assert.equal(clock.textContent, '00:06');

console.log('Passenger pickup wait clock advances under frequent snapshots: OK');
