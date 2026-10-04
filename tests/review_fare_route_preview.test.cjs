const fs = require('fs');
const assert = require('assert');

const js = fs.readFileSync('app/static/js/driver.js', 'utf8');
const html = fs.readFileSync('app/templates/driver.html', 'utf8');

assert.match(html, /<button id="ride-alert"[^>]*type="button"/);
assert.match(js, /Review Fare \/ Preview Route/);
assert.match(js, /#ride-alert"\)\?\.addEventListener/);
assert.match(js, /previewOfferFromCurrentGps/);
assert.match(js, /gpsRoutePreviewPending = true/);
assert.match(js, /socket\.on\([\s\S]*"driver_location"[\s\S]*gpsRoutePreviewPending = true[\s\S]*loadActiveRequests/);
assert.match(js, /socket\.on\([\s\S]*"driver_request_queue"[\s\S]*gpsRoutePreviewPending[\s\S]*previewOfferFromCurrentGps/);

console.log('Review Fare route-preview button + GPS-triggered preview: OK');
