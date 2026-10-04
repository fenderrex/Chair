const fs = require('fs');
const assert = require('assert');
const vm = require('vm');

const lifecycle = fs.readFileSync('app/static/js/lifecycle-ui.js', 'utf8');
const css = fs.readFileSync('app/static/css/app.css', 'utf8');
const passenger = fs.readFileSync('app/static/js/passenger.js', 'utf8');

const sandbox = { window: {}, document: { querySelectorAll: () => [], querySelector: () => null } };
vm.createContext(sandbox);
vm.runInContext(lifecycle, sandbox);

const searchUi = Array.from(sandbox.window.PASSENGER_UI_MATRIX.LOOKING_FOR_DRIVER);
assert(searchUi.includes('estimate'), 'ESTIMATE must stay visible while searching');
assert(searchUi.includes('keep-searching'), 'KEEP SEARCHING slot remains part of search lifecycle');

assert(/(?:^|\n)\.hidden\s*\{[^}]*display\s*:\s*none\s*!important\s*;/m.test(css),
  'generic .hidden utility must actually hide JS-controlled cards');

assert(passenger.includes('!maxSearchRadiusReached'),
  'fare escalation card must remain gated by max search radius');
assert(passenger.includes('!live.fare_review_pending'),
  'fare escalation card must remain gated by pending fare review');
assert(passenger.includes('escalation.status !== "PENDING"'),
  'fare escalation card must require a pending escalation payload');

console.log('Passenger search estimate + fare-card visibility: OK');
