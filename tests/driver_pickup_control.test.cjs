const fs = require('fs');
const assert = require('assert');

const html = fs.readFileSync('app/templates/driver.html', 'utf8');
const js = fs.readFileSync('app/static/js/driver.js', 'utf8');

assert(html.includes('id="claim-passenger-pickup"'));
assert(html.includes('data-lifecycle-statuses="DRIVER_ARRIVED,PICKUP_PENDING"'));
assert(js.includes('pickupPassengerButton?.addEventListener'));
assert(js.includes('currentTripStatus !== "DRIVER_ARRIVED"'));
assert(js.includes('await claimPassengerPickup()'));
assert(js.includes('pickupButton.disabled = false'));
assert(js.includes('pickupButton.textContent = "Waiting for Passenger"'));

console.log('Driver pickup control: OK');
