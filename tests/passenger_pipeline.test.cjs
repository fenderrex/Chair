const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app/static/js/passenger.js'), 'utf8');
const template = fs.readFileSync(path.join(root, 'app/templates/passenger.html'), 'utf8');
function extract(name) {
    const start = source.indexOf(`function ${name}(`);
    return source.slice(start, source.indexOf('\n}', start) + 2);
}
function freshPage() {
    const steps = [...template.matchAll(/data-stage="([^"]+)"/g)].map((match) => {
        const classes = new Set();
        return {dataset: {stage: match[1]}, classes, classList: {
            toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); }
        }};
    });
    const context = {
        document: {querySelectorAll: () => steps, querySelector: () => null},
        currentTripId: null, streamedTripSnapshot: null,
        cancelRideButton: {}, etaEl: {},
    };
    for (const name of ['wsLog', 'restoreTripFormFromSnapshot', 'setRequestCreationEnabled',
        'renderAssignedDriver', 'renderPickupWait', 'renderPickupConfirmation',
        'renderPassengerSearchRadius', 'hydratePassengerStepNotices', 'renderFareEscalation',
        'renderReviewingDrivers', 'renderPassengerSurvey', 'updatePickupWaitFromTimestamp',
        'setStatus', 'showPassengerAlert', 'stopPickupWaitTicker']) {
        context[name] = () => {};
    }
    vm.createContext(context);
    vm.runInContext(extract('setPipelineStage') + '\n' + extract('applyPassengerTripSnapshot'), context);
    return {steps, context};
}
const expected = {
    REQUESTED: 0, OFFERED: 0, DRIVER_ASSIGNED: 1, DRIVER_EN_ROUTE: 2,
    DRIVER_ARRIVED: 3, PICKUP_PENDING: 3, IN_PROGRESS: 4,
    COMPLETED: -1, CANCELED: -1,
};
for (const [status, activeIndex] of Object.entries(expected)) {
    const {steps, context} = freshPage();
    // A fresh page receives its first authoritative recovery snapshot.
    context.applyPassengerTripSnapshot({reason: 'ACTIVE_TRIP_RECOVERY', snapshot: {
        trip_id: 42, status, cancel_locked: ['PICKUP_PENDING', 'IN_PROGRESS'].includes(status),
    }});
    assert.equal(context.currentTripId, 42);
    steps.forEach((step, index) => {
        assert.equal(step.classes.has('active'), index === activeIndex, `${status}: active ${index}`);
        assert.equal(step.classes.has('complete'), status === 'COMPLETED' || index < activeIndex,
            `${status}: complete ${index}`);
    });
}
const {steps, context} = freshPage();
for (const status of ['IN_PROGRESS', 'DRIVER_EN_ROUTE', 'PICKUP_PENDING', 'COMPLETED', 'REQUESTED']) {
    context.applyPassengerTripSnapshot({snapshot: {trip_id: 42, status}});
    assert.equal(steps.filter(s => s.classes.has('active')).length, status === 'COMPLETED' ? 0 : 1);
}
console.log('PASS: refresh recovery across nine states and repeated snapshot updates');
