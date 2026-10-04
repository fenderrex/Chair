const demoDriverId = Number(window.DRIVER_ID || 1);
const socket = io({
    transports: ["websocket"],
    upgrade: false,
    timeout: 10000,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 500,
    reconnectionDelayMax: 3000,
});

let driverClockOffset = 0;
let currentDriver = null;
let currentOffer = null;
let currentTripId = null;
let currentTripStatus = null;
let acceptedTripId = null;
let routeLayer = null;
let pickupRoute = null;
let pickupSimulationTimer = null;
let pickupSimulationIndex = 0;

let driverStreamTripId = null;
let lastDriverRequestQueue = [];
let gpsRoutePreviewPending = false;
let gpsRoutePreviewInFlight = false;

const driverLifecycle = new window.RideLifecycleManager({
    role: "driver",
    defaultDemoMode: false,
    toggleSelector: "#driver-lifecycle-demo",
});

driverLifecycle.update({}, { scroll: false });

function setDriverStreamState(
    text
) {
    const pill =
        document.querySelector(
            "#driver-stream-state"
        );

    if (pill) {
        pill.textContent = text;
    }
}

function driverWsLog(
    event,
    detail = {}
) {
    console.log(
        `[DRIVER WS] ${event}`,
        {
            time:
                new Date().toISOString(),
            driver_id:
                demoDriverId,
            trip_id:
                currentTripId,
            ...detail,
        }
    );
}

function joinDriverTripStream(
    tripId,
    reason = "CLIENT_JOIN"
) {
    if (
        !tripId ||
        !socket.connected
    ) {
        driverWsLog(
            "JOIN DEFERRED",
            {
                requested_trip_id:
                    tripId,
                connected:
                    socket.connected,
                reason,
            }
        );

        return;
    }

    driverStreamTripId =
        Number(tripId);

    driverWsLog(
        "JOIN TRIP",
        {
            requested_trip_id:
                driverStreamTripId,
            reason,
        }
    );

    socket.emit(
        "join_trip",
        {
            trip_id:
                driverStreamTripId,
            role: "DRIVER",
            actor_id:
                demoDriverId,
            reason,
        }
    );
}

const map = L.map("map", { zoomControl: false }).setView(
    [33.7206, -116.2156],
    13
);

L.control.zoom({ position: "bottomleft" }).addTo(map);

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
    }
).addTo(map);

function markerIcon(kind) {
    return L.divIcon({
        className: "",
        html: `<div class="custom-pin ${kind}"></div>`,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
    });
}

const driverMarker = L.marker(
    [33.7206, -116.2156],
    { icon: markerIcon("driver") }
).addTo(map).bindPopup("Driver location");

const passengerMarker = L.marker(
    [33.7206, -116.2156],
    { icon: markerIcon("passenger") }
);
// Privacy rule: do not add the passenger marker to the driver map.

const destinationMarker = L.marker(
    [33.7414, -116.3042],
    { icon: markerIcon("destination") }
).addTo(map);

function setDriverLocation(lat, lng, center = false) {
    driverMarker.setLatLng([lat, lng]);

    if (center) {
        map.setView([lat, lng], 14);
    }
}

async function loadDriverIdentity() {
    const response = await fetch(`/drivers/${demoDriverId}`);

    if (!response.ok) {
        return;
    }

    currentDriver = await response.json();
    renderDriverAvailability(currentDriver);

    const name = document.querySelector("#driver-name");
    if (name) {
        name.textContent = currentDriver.name;
    }

    document.title = `${currentDriver.name} • Driver • RideShare`;

    if (
        currentDriver.current_latitude !== null &&
        currentDriver.current_longitude !== null
    ) {
        setDriverLocation(
            currentDriver.current_latitude,
            currentDriver.current_longitude,
            true
        );
    }
}


async function recoverAcceptedTrip() {
    // Active-trip recovery is pushed by register_driver over WebSocket.
    return null;
}

function drawRouteGeometry(geometry, weight = 6) {
    if (!geometry) {
        return;
    }

    if (routeLayer) {
        map.removeLayer(routeLayer);
    }

    routeLayer = L.geoJSON(
        geometry,
        {
            style: {
                weight,
                opacity: 0.88,
            },
        }
    ).addTo(map);

    const bounds = routeLayer.getBounds();

    if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [55, 55] });
    }
}

async function previewPassengerTrip(request) {
    try {
        const response = await fetch(
            `/drivers/${demoDriverId}/trips/${request.trip_id}/pickup-route`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Could not preview pickup route."
            );
        }

        if (
            data.preview &&
            data.preview.preview_geometry
        ) {
            drawRouteGeometry(
                data.preview.preview_geometry,
                6
            );
        } else if (request.route_geometry) {
            drawRouteGeometry(
                request.route_geometry,
                6
            );
        }

        // Keep the destination visible, but do not render a passenger marker.
        const destination =
            data.preview?.destination
            || request.destination;

        if (destination) {
            destinationMarker.setLatLng([
                destination.latitude,
                destination.longitude,
            ]);
        }

        const detail = document.querySelector("#offer-detail");
        if (detail) {
            const pickupMiles =
                Number(
                    data.preview?.pickup_route?.distance_miles
                    || request.driver_distance_miles
                    || 0
                );

            const pickupMinutes =
                Math.ceil(
                    Number(
                        data.preview?.pickup_route?.duration_minutes
                        || 0
                    )
                );

            detail.textContent =
                `Preview loaded: your route to pickup plus the passenger trip route. ` +
                `Pickup point remains hidden. ` +
                `${pickupMiles.toFixed(2)} mi to pickup • ${pickupMinutes} min estimate.`;
        }

        return data;
    } catch (error) {
        if (request.route_geometry) {
            drawRouteGeometry(
                request.route_geometry,
                6
            );
        }

        const detail = document.querySelector("#offer-detail");
        if (detail) {
            detail.textContent =
                error.message;
        }

        return null;
    }
}

function showRideAlert(offer) {
    const alert = document.querySelector("#ride-alert");

    if (!alert) {
        return;
    }

    const distance =
        offer.driver_distance_miles !== null &&
        offer.driver_distance_miles !== undefined
            ? `${Number(offer.driver_distance_miles).toFixed(2)} mi from pickup`
            : "Ride offered to you";

    alert.dataset.tripId = String(offer.trip_id || "");
    alert.textContent =
        `Review Fare / Preview Route • ${distance} • $${Number(offer.estimated_fare || 0).toFixed(2)}`;
    alert.title = "Preview the live route from your current GPS location to pickup";
    alert.classList.remove("hidden");
}

function currentPreviewOffer(tripId = null) {
    const wantedTripId = Number(tripId || 0);

    if (wantedTripId) {
        const queued = lastDriverRequestQueue.find(
            (request) =>
                Number(request.trip_id) === wantedTripId &&
                Boolean(request.can_accept)
        );

        if (queued) {
            return queued;
        }
    }

    if (currentOffer && currentOffer.can_accept) {
        return currentOffer;
    }

    return lastDriverRequestQueue.find(
        (request) => Boolean(request.can_accept)
    ) || null;
}

async function previewOfferFromCurrentGps(offer) {
    if (!offer || !offer.can_accept || acceptedTripId) {
        return null;
    }

    gpsRoutePreviewInFlight = true;

    try {
        currentOffer = offer;
        hydrateOfferPanel(offer);
        return await previewPassengerTrip(offer);
    } finally {
        gpsRoutePreviewInFlight = false;
    }
}

function formatClockSeconds(value) {
    const seconds = Math.max(
        0,
        Math.ceil(Number(value || 0))
    );

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;

    if (hours > 0) {
        return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
    }

    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function waitingSecondsRemaining(request) {
    if (!request || request.my_offer_status !== "WAITING") {
        return 0;
    }

    const targetText =
        request.offer_available_at
        || request.eligible_at;

    if (targetText) {
        const target = Date.parse(targetText);

        if (Number.isFinite(target)) {
            const serverNow = Date.now() + driverClockOffset;
            return Math.max(
                0,
                Math.ceil((target - serverNow) / 1000)
            );
        }
    }

    return Math.max(
        0,
        Math.ceil(Number(request.seconds_until_eligible || 0))
    );
}

function passengerWaitingText(request) {
    const count = Math.max(
        0,
        Number(
            request.offered_driver_count
            ?? request.offer_count
            ?? 0
        )
    );

    return `Passenger is waiting on ${count} driver${count === 1 ? "" : "s"}.`;
}

function formatDispatchTimer(request) {
    const radius = Number(request.search_radius_miles || 0);
    const step = Number(request.search_radius_step_miles || 0);

    if (request.my_offer_status === "WAITING") {
        const seconds = waitingSecondsRemaining(request);
        const requiredRadius = Number(
            request.required_radius_miles
            ?? request.driver_distance_miles
            ?? radius
        );

        return (
            `Offer available in ${formatClockSeconds(seconds)} • ` +
            `current radius ${radius.toFixed(2)} mi • ` +
            `reaches you at ${requiredRadius.toFixed(2)} mi • ` +
            passengerWaitingText(request)
        );
    }

    if (request.my_offer_status === "OFFERED") {
        return (
            `Offer available now • current radius ${radius.toFixed(2)} mi • ` +
            passengerWaitingText(request)
        );
    }

    if (request.my_offer_status === "DECLINED") {
        return "You declined this fare round.";
    }

    return (
        `Passenger search radius: ${radius.toFixed(2)} mi • ` +
        `increases by ${step.toFixed(2)} mi each timer`
    );
}

function hydrateOfferPanel(offer) {
    currentOffer = offer;

    if (!acceptedTripId && typeof driverLifecycle !== "undefined") {
        driverLifecycle.update({
            trip_id: offer.trip_id,
            status: offer.status === "REQUESTED" ? "REQUESTED" : "OFFERED",
        }, { scroll: false });
    }

    const canAccept = Boolean(offer.can_accept);
    const canDecline = Boolean(offer.can_decline);
    const waiting = offer.my_offer_status === "WAITING";
    const declined = offer.my_offer_status === "DECLINED";

    const title = document.querySelector("#offer-title");
    const detail = document.querySelector("#offer-detail");
    const distance = document.querySelector("#offer-distance");
    const fare = document.querySelector("#offer-fare");
    const trip = document.querySelector("#offer-trip");
    const timer = document.querySelector("#offer-timer");
    const accept = document.querySelector("#accept-offer");
    const decline = document.querySelector("#decline-offer");
    const waitingPanel = document.querySelector("#offer-waiting-panel");
    const waitingCountdown = document.querySelector("#offer-waiting-countdown");
    const waitingDetail = document.querySelector("#offer-waiting-detail");

    if (title) {
        if (waiting) {
            title.textContent =
                Number(offer.fare_round || 0) > 0
                    ? `${offer.passenger_name}'s higher-fare round is expanding`
                    : `${offer.passenger_name}'s search is expanding`;
        } else if (canAccept) {
            title.textContent = `${offer.passenger_name} needs a ride`;
        } else if (declined) {
            title.textContent = `You declined ${offer.passenger_name}'s fare round`;
        } else {
            title.textContent = `${offer.passenger_name} requested a ride`;
        }
    }

    if (detail) {
        if (waiting && Number(offer.fare_round || 0) > 0) {
            const previousFare = Number(offer.previous_estimated_fare || 0);
            const currentFare = Number(offer.estimated_fare || 0);
            const fareChange = previousFare > 0
                ? `The passenger increased the fare from $${previousFare.toFixed(2)} to $${currentFare.toFixed(2)}. `
                : `The passenger increased the fare to $${currentFare.toFixed(2)}. `;

            detail.textContent =
                fareChange +
                `The nearby-driver search restarted at the smallest radius, so this offer is temporarily more exclusive. ` +
                `You will be able to accept or decline when the expanding radius reaches you.`;
        } else if (waiting) {
            detail.textContent =
                `This ride is known to dispatch, but the current search radius has not reached you yet. ` +
                `The broker will unlock the offer automatically.`;
        } else if (canAccept && offer.fare_increase_acceptance_note) {
            detail.textContent =
                `${offer.fare_increase_warning} ` +
                `Current passenger-approved fare: $${Number(offer.estimated_fare).toFixed(2)}.`;
        } else if (canAccept) {
            detail.textContent =
                `You are inside the passenger's current search radius. This offer remains available until someone accepts or you decline.`;
        } else if (declined) {
            detail.textContent =
                "You declined this fare round. If the passenger approves a higher fare, the next search round can place you back into WAITING.";
        } else {
            detail.textContent =
                `Dispatch wave ${offer.dispatch_wave || 0} is currently active.`;
        }
    }

    if (distance) {
        distance.textContent =
            offer.driver_distance_miles !== null &&
            offer.driver_distance_miles !== undefined
                ? `${Number(offer.driver_distance_miles).toFixed(2)} mi`
                : "—";
    }

    if (fare) {
        fare.textContent = `$${Number(offer.estimated_fare).toFixed(2)}`;
    }

    if (trip) {
        trip.textContent = `#${offer.trip_id}`;
    }

    if (timer) {
        timer.textContent = formatDispatchTimer(offer);
    }

    if (waitingPanel) {
        waitingPanel.hidden = !waiting;
    }

    if (waitingCountdown) {
        waitingCountdown.textContent = formatClockSeconds(
            waitingSecondsRemaining(offer)
        );
    }

    if (waitingDetail && waiting) {
        const radius = Number(offer.search_radius_miles || 0);
        const requiredRadius = Number(
            offer.required_radius_miles
            ?? offer.driver_distance_miles
            ?? radius
        );
        waitingDetail.textContent =
            `Current radius ${radius.toFixed(2)} mi • ` +
            `your pickup distance ${Number(offer.driver_distance_miles || 0).toFixed(2)} mi • ` +
            `search reaches you at ${requiredRadius.toFixed(2)} mi • ` +
            passengerWaitingText(offer);
    }

    if (accept) {
        accept.disabled = !canAccept;
        accept.textContent = waiting
            ? `Waiting ${formatClockSeconds(waitingSecondsRemaining(offer))}`
            : canAccept
            ? "Accept Ride"
            : "Accept Ride";
    }

    if (decline) {
        decline.disabled = !canDecline;
    }

    if (canAccept) {
        showRideAlert(offer);
    } else {
        document.querySelector("#ride-alert")?.classList.add("hidden");
    }
}


function updateMainDriverAction(live) {
    const action =
        document.querySelector("#accept-offer");

    const decline =
        document.querySelector("#decline-offer");

    const title =
        document.querySelector("#offer-title");

    const detail =
        document.querySelector("#offer-detail");

    if (!action || !decline || !live) {
        return;
    }

    const destinationPhase =
        live.simulation?.phase
            === "TO_DESTINATION";

    const destinationRunning =
        destinationPhase &&
        live.simulation?.status
            === "RUNNING";

    if (destinationPhase) {
        action.textContent =
            live.status === "COMPLETED"
                ? "Trip Complete"
                : destinationRunning
                ? "Driving to Drop-off"
                : "Passenger Confirmed";

        action.disabled = true;
        decline.disabled = true;

        if (title) {
            title.textContent =
                live.status === "COMPLETED"
                    ? "Ride complete"
                    : "Passenger onboard";
        }

        if (detail) {
            detail.textContent =
                live.status === "COMPLETED"
                    ? "The ride reached the drop-off."
                    : destinationRunning
                    ? "The passenger and driver are traveling together to the drop-off."
                    : "Pickup is confirmed. Continue the ride from the driving controls.";
        }

        return;
    }

    if (
        live.status === "DRIVER_ASSIGNED" ||
        live.status === "DRIVER_EN_ROUTE"
    ) {
        action.textContent = "Pick Up";
        action.disabled = true;

        decline.disabled = true;

        if (title) {
            title.textContent =
                "Ride assigned";
        }

        if (detail) {
            detail.textContent =
                live.status === "DRIVER_EN_ROUTE"
                    ? "Drive to the passenger. Pick Up unlocks when you arrive."
                    : "This ride is assigned to you. Pick Up unlocks when you arrive.";
        }

        return;
    }

    if (live.status === "DRIVER_ARRIVED") {
        action.textContent = "Pick Up";
        action.disabled = false;

        decline.disabled = true;

        if (title) {
            title.textContent =
                "Passenger pickup ready";
        }

        if (detail) {
            detail.textContent =
                "You have arrived. Press Pick Up when the passenger is in the vehicle.";
        }

        return;
    }

    if (live.status === "PICKUP_PENDING") {
        action.textContent =
            "Waiting for Passenger";
        action.disabled = true;
        decline.disabled = true;

        if (title) {
            title.textContent =
                "Pickup recorded";
        }

        if (detail) {
            detail.textContent =
                "The passenger has been asked to confirm pickup.";
        }

        return;
    }

    if (
        live.status === "IN_PROGRESS" ||
        live.status === "COMPLETED"
    ) {
        action.textContent =
            live.status === "COMPLETED"
                ? "Trip Complete"
                : "Passenger Confirmed";

        action.disabled = true;
        decline.disabled = true;

        return;
    }
}


function resetOfferPanel(message = "No active ride request") {
    currentOffer = null;

    if (!acceptedTripId && typeof driverLifecycle !== "undefined") {
        driverLifecycle.update({}, { scroll: false });
    }

    const title = document.querySelector("#offer-title");
    const detail = document.querySelector("#offer-detail");
    const distance = document.querySelector("#offer-distance");
    const fare = document.querySelector("#offer-fare");
    const trip = document.querySelector("#offer-trip");
    const timer = document.querySelector("#offer-timer");
    const accept = document.querySelector("#accept-offer");
    const decline = document.querySelector("#decline-offer");

    if (title) title.textContent = message;
    if (detail) {
        detail.textContent =
            "Timed dispatch starts with the best-ranked available driver, then expands to runner-ups.";
    }
    if (distance) distance.textContent = "—";
    if (fare) fare.textContent = "—";
    if (trip) trip.textContent = "—";
    if (timer) timer.textContent = "Waiting for dispatch timer…";
    const waitingPanel = document.querySelector("#offer-waiting-panel");
    if (waitingPanel) waitingPanel.hidden = true;
    if (accept) {
        accept.disabled = true;
        accept.textContent = "Accept Ride";
    }
    if (decline) decline.disabled = true;

    document.querySelector("#ride-alert")?.classList.add("hidden");
}

function renderRequestCard(request) {
    const row = document.createElement("div");
    row.className = "request-item";
    row.dataset.tripId = request.trip_id;

    if (request.my_offer_status === "WAITING") {
        row.classList.add("waiting-request");
    }

    const miles = (
        Number(request.estimated_distance_meters) / 1609.344
    ).toFixed(1);

    const minutes = Math.ceil(
        Number(request.estimated_duration_seconds) / 60
    );

    const canAccept = Boolean(request.can_accept);
    const canDecline = Boolean(request.can_decline);

    let offerText = "";

    if (canAccept) {
        offerText =
            `<span class="pill online">OFFERED • rank #${request.my_offer_rank}</span>`;
    } else if (request.my_offer_status === "WAITING") {
        offerText =
            `<span class="pill">WAITING • offer in ${formatClockSeconds(waitingSecondsRemaining(request))}</span>`;
    } else if (request.my_offer_status === "DECLINED") {
        offerText =
            '<span class="pill">DECLINED THIS ROUND</span>';
    } else if (request.status === "OFFERED") {
        offerText =
            `<span class="pill">${request.offer_count} driver${request.offer_count === 1 ? "" : "s"} currently eligible</span>`;
    } else {
        offerText =
            '<span class="pill">Waiting for dispatch</span>';
    }

    row.innerHTML = `
        <div>
            <strong>${request.passenger_name}</strong>
            <div class="muted">
                Trip #${request.trip_id} • ${request.status}
            </div>
            ${offerText}
        </div>

        <div class="request-meta">
            <span>${miles} mi</span>
            <span>${minutes} min</span>
            <span>$${Number(request.estimated_fare).toFixed(2)}</span>
            ${
                request.driver_distance_miles !== null &&
                request.driver_distance_miles !== undefined
                    ? `<span>${Number(request.driver_distance_miles).toFixed(2)} mi to pickup</span>`
                    : ""
            }
        </div>

        <div class="dispatch-countdown" data-next="${request.next_dispatch_at || ""}">
            ${formatDispatchTimer(request)}
        </div>

        <div class="button-row">
            <button
                class="button secondary preview-request"
                ${canAccept ? "" : "disabled"}
            >
                ${canAccept ? "Preview Route" : "Route Locked"}
            </button>

            <button
                class="button primary accept-request"
                ${canAccept ? "" : "disabled"}
            >
                ${
                    canAccept
                        ? "Accept Ride"
                        : request.my_offer_status === "WAITING"
                        ? `Waiting ${formatClockSeconds(waitingSecondsRemaining(request))}`
                        : "Not Yet Offered"
                }
            </button>

            <button
                class="button danger decline-request"
                ${canDecline ? "" : "disabled"}
            >
                Decline
            </button>
        </div>
    `;

    row.querySelector(".preview-request").addEventListener(
        "click",
        async () => {
            if (!canAccept) {
                hydrateOfferPanel(request);
                return;
            }

            await previewPassengerTrip(request);

            if (request.my_offer_status) {
                hydrateOfferPanel(request);
            }
        }
    );

    row.querySelector(".accept-request").addEventListener(
        "click",
        async () => {
            if (!canAccept) return;
            await acceptRide(request);
        }
    );

    row.querySelector(".decline-request").addEventListener(
        "click",
        async () => {
            if (!canDecline) return;
            await declineRide(request);
        }
    );

    return row;
}

async function declineRide(request) {
    const response = await fetch(
        `/trips/${request.trip_id}/decline`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                driver_id: demoDriverId,
            }),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        const detail = document.querySelector("#offer-detail");
        if (detail) {
            detail.textContent =
                data.error || "Unable to decline this ride.";
        }
        return;
    }

    resetOfferPanel("Ride declined");
    await loadActiveRequests();
}

function renderDriverRequestQueue(requests) {
    const list = document.querySelector("#active-requests");
    const count = document.querySelector("#request-count");

    if (count) {
        count.textContent = requests.length;
    }

    if (list) {
        list.innerHTML = "";
    }

    if (!requests.length) {
        if (list) {
            list.innerHTML =
                '<p class="muted">No active requests.</p>';
        }

        if (!acceptedTripId) {
            resetOfferPanel();
        }

        return;
    }

    let mine = null;

    requests.forEach((request) => {
        if (!mine && request.can_accept) {
            mine = request;
        }

        if (list) {
            list.appendChild(
                renderRequestCard(request)
            );
        }
    });

    if (mine) {
        hydrateOfferPanel(mine);
    } else if (!acceptedTripId) {
        const waiting = requests.find(
            (request) =>
                request.my_offer_status === "WAITING"
        );

        const declined = requests.find(
            (request) =>
                request.my_offer_status === "DECLINED"
        );

        if (waiting) {
            hydrateOfferPanel(waiting);
        } else if (declined) {
            hydrateOfferPanel(declined);
        } else {
            resetOfferPanel();
        }
    }
}

async function loadActiveRequests() {
    if (!socket.connected) {
        driverWsLog(
            "QUEUE REQUEST DEFERRED",
            {
                connected: false,
            }
        );
        return;
    }

    driverWsLog(
        "QUEUE REQUEST"
    );

    socket.emit(
        "request_driver_queue",
        {
            driver_id: demoDriverId,
        }
    );
}

async function loadTrip(tripId) {
    currentTripId = Number(tripId);

    joinDriverTripStream(
        currentTripId,
        "LOAD_TRIP"
    );

    return null;
}

function unlockPickupSimulation(tripId) {
    acceptedTripId = Number(tripId);
    currentTripId = Number(tripId);

    const preview = document.querySelector("#preview-pickup-route");
    const start = document.querySelector("#start-pickup-sim");
    const stop = document.querySelector("#stop-pickup-sim");
    const title = document.querySelector("#pickup-drive-title");
    const detail = document.querySelector("#pickup-drive-detail");

    if (preview) preview.disabled = false;
    if (start) start.disabled = false;
    if (stop) stop.disabled = true;

    if (title) {
        title.textContent = "Drive to passenger";
    }

    if (detail) {
        detail.textContent =
            "Preview the road route to pickup, then start the simulated drive. The passenger will see your location move live.";
    }
}

async function acceptRide(request) {
    const response = await fetch(
        `/trips/${request.trip_id}/accept`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                driver_id: demoDriverId,
            }),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        const detail = document.querySelector("#offer-detail");

        if (detail) {
            detail.textContent =
                data.error || "Unable to accept this ride.";
        }

        await loadActiveRequests();
        return;
    }

    currentOffer = request;

    const accept = document.querySelector("#accept-offer");
    const title = document.querySelector("#offer-title");
    const detail = document.querySelector("#offer-detail");

    if (accept) accept.disabled = true;
    if (title) title.textContent = "Ride accepted";
    if (detail) {
        detail.textContent =
            "The passenger was notified. You can now simulate driving to pickup.";
    }

    document.querySelector("#ride-alert")?.classList.add("hidden");

    unlockPickupSimulation(request.trip_id);

    if (typeof driverLifecycle !== "undefined") {
        driverLifecycle.update({
            trip_id: request.trip_id,
            status: "DRIVER_ASSIGNED",
        }, { scroll: false });
    }

    const mainAction =
        document.querySelector("#accept-offer");

    const mainDecline =
        document.querySelector("#decline-offer");

    if (mainAction) {
        mainAction.textContent = "Pick Up";
        mainAction.disabled = true;
    }

    if (mainDecline) {
        mainDecline.disabled = true;
    }

    await previewPassengerTrip(request);

    if (
        data.simulation &&
        data.simulation.route_geometry
    ) {
        pickupRoute = {
            geometry:
                data.simulation.route_geometry,
        };

        drawRouteGeometry(
            data.simulation.route_geometry,
            7
        );
    }

    joinDriverTripStream(
        request.trip_id,
        "DRIVER_ACCEPTED"
    );

    const driveTitle =
        document.querySelector(
            "#pickup-drive-title"
        );

    const driveDetail =
        document.querySelector(
            "#pickup-drive-detail"
        );

    if (
        data.simulation &&
        data.simulation.status === "READY"
    ) {
        if (driveTitle) {
            driveTitle.textContent =
                "Ready to drive to passenger";
        }

        if (driveDetail) {
            driveDetail.textContent =
                "The route is prepared. Press Start Driving to begin broker-controlled movement.";
        }

        const startButton =
            document.querySelector(
                "#start-pickup-sim"
            );

        if (startButton) {
            startButton.disabled = false;
            startButton.textContent =
                "Start Driving";
        }
    } else if (
        data.simulation &&
        data.simulation.status === "PREPARE_FAILED"
    ) {
        if (driveTitle) {
            driveTitle.textContent =
                "Route preparation failed";
        }

        if (driveDetail) {
            driveDetail.textContent =
                data.simulation.error ||
                "The ride was accepted but the pickup route could not be prepared.";
        }
    }

    await loadActiveRequests();
}

async function previewPickupRoute() {
    if (!acceptedTripId) return;

    const response = await fetch(
        `/broker/trips/${acceptedTripId}/drivers/${demoDriverId}/prepare`,
        {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({}),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        const detail = document.querySelector("#pickup-drive-detail");
        if (detail) detail.textContent =
            data.error || "Could not prepare pickup simulation.";
        return;
    }

    pickupRoute = data.route;
    drawRouteGeometry(data.route.geometry, 7);

    const detail = document.querySelector("#pickup-drive-detail");
    if (detail) {
        detail.textContent =
            `${Number(data.route.distance_miles).toFixed(2)} mi to passenger • ` +
            `${Math.ceil(Number(data.route.duration_minutes))} min route estimate`;
    }
}

async function startPickupSimulation() {
    if (!acceptedTripId) return;

    if (
        currentTripStatus !== "IN_PROGRESS" &&
        !pickupRoute
    ) {
        await previewPickupRoute();
    }

    const response = await fetch(
        `/broker/trips/${acceptedTripId}/drivers/${demoDriverId}/start`,
        {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({}),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        const detail = document.querySelector("#pickup-drive-detail");
        if (detail) detail.textContent =
            data.error || "Could not start simulation broker.";
        return;
    }

    const startButton = document.querySelector("#start-pickup-sim");
    const stopButton = document.querySelector("#stop-pickup-sim");
    const title = document.querySelector("#pickup-drive-title");

    if (startButton) startButton.disabled = true;
    if (stopButton) stopButton.disabled = false;
    if (title) {
        title.textContent =
            currentTripStatus === "IN_PROGRESS"
                ? "Driving to drop-off…"
                : "Driving to passenger…";
    }

    driverWsLog(
        "SIMULATION START/RESUME RESPONSE",
        {
            trip_id: acceptedTripId,
            job: data.job,
        }
    );
}

async function stopPickupSimulation() {
    if (!acceptedTripId) return;

    await fetch(
        `/broker/trips/${acceptedTripId}/drivers/${demoDriverId}/pause`,
        {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({}),
        }
    );

    const startButton = document.querySelector("#start-pickup-sim");
    const stopButton = document.querySelector("#stop-pickup-sim");
    const title = document.querySelector("#pickup-drive-title");

    if (startButton) startButton.disabled = false;
    if (stopButton) stopButton.disabled = true;
    if (title) title.textContent = "Simulation paused";
}

let driverPickupWaitTicker = null;

function stopDriverPickupWaitTicker() {
    if (driverPickupWaitTicker) {
        clearInterval(
            driverPickupWaitTicker
        );
        driverPickupWaitTicker = null;
    }
}

function startDriverPickupWaitTicker(snapshot) {
    stopDriverPickupWaitTicker();

    if (
        !snapshot.driver_arrived_at ||
        snapshot.status !== "DRIVER_ARRIVED"
    ) {
        return;
    }

    const update = () => {
        const detail =
            document.querySelector(
                "#pickup-drive-detail"
            );

        if (!detail) {
            return;
        }

        const arrivedAt =
            new Date(
                snapshot.driver_arrived_at
            ).getTime();

        const waitSeconds = Math.max(
            0,
            Math.floor(
                (Date.now() - arrivedAt)
                / 1000
            )
        );

        const minutes =
            Math.floor(
                waitSeconds / 60
            );

        const seconds =
            waitSeconds % 60;

        detail.textContent =
            `Waiting at pickup • ` +
            `${String(minutes).padStart(2, "0")}:` +
            `${String(seconds).padStart(2, "0")}`;
    };

    update();

    driverPickupWaitTicker =
        setInterval(
            update,
            1000
        );
}

function applyDriverTripSnapshot(envelope) {
    const live = envelope?.snapshot;

    if (!live) {
        driverWsLog(
            "SNAPSHOT IGNORED",
            {
                reason: "missing snapshot",
            }
        );
        return;
    }

    if (
        currentTripId &&
        Number(live.trip_id) !==
            Number(currentTripId)
    ) {
        driverWsLog(
            "SNAPSHOT IGNORED",
            {
                reason:
                    "different trip",
                snapshot_trip_id:
                    live.trip_id,
            }
        );
        return;
    }

    currentTripId =
        Number(live.trip_id);

    currentTripStatus =
        live.status;
    if (typeof driverLifecycle !== "undefined") {
        driverLifecycle.update(live);
    }

    if (
        [
            "DRIVER_ASSIGNED",
            "DRIVER_EN_ROUTE",
            "DRIVER_ARRIVED",
            "PICKUP_PENDING",
            "IN_PROGRESS",
        ].includes(live.status)
    ) {
        unlockPickupSimulation(
            live.trip_id
        );
    }

    driverWsLog(
        "SNAPSHOT",
        {
            reason:
                envelope.reason,
            status:
                live.status,
            progress:
                live.progress_percent,
            eta_seconds:
                live.driver_eta_seconds,
            simulation:
                live.simulation,
        }
    );

    if (
        live.simulation &&
        live.simulation.route_geometry
    ) {
        pickupRoute = {
            geometry:
                live.simulation.route_geometry,
        };

        drawRouteGeometry(
            live.simulation.route_geometry,
            7
        );
    } else if (
        live.route_geometry
    ) {
        drawRouteGeometry(
            live.route_geometry,
            6
        );
    }

    // Passenger pickup location remains hidden on the driver map.

    if (live.destination) {
        destinationMarker.setLatLng([
            live.destination.latitude,
            live.destination.longitude,
        ]);
    }

    if (
        live.driver &&
        live.driver.latitude !== null &&
        live.driver.longitude !== null
    ) {
        setDriverLocation(
            live.driver.latitude,
            live.driver.longitude,
            false
        );
    }

    const progress =
        Math.round(
            Number(
                live.progress_percent
                || 0
            )
        );

    const eta =
        live.driver_eta_seconds;

    const simulationPhase =
        live.simulation?.phase || null;

    const destinationPhase =
        simulationPhase ===
        "TO_DESTINATION";

    const pickupPhase =
        simulationPhase ===
        "TO_PICKUP";

    const detail =
        document.querySelector(
            "#pickup-drive-detail"
        );

    const title =
        document.querySelector(
            "#pickup-drive-title"
        );

    const phaseEyebrow =
        document.querySelector(
            "#pickup-drive-eyebrow"
        );

    const startButton =
        document.querySelector(
            "#start-pickup-sim"
        );

    const stopButton =
        document.querySelector(
            "#stop-pickup-sim"
        );

    const arriveButton =
        document.querySelector(
            "#mark-driver-arrived"
        );

    const pickupMotionComplete =
        pickupPhase &&
        live.simulation?.status === "COMPLETED";

    if (arriveButton) {
        if (live.status === "DRIVER_EN_ROUTE") {
            const demoMotionStillRunning =
                pickupPhase &&
                ["READY", "RUNNING", "PAUSED"].includes(
                    String(live.simulation?.status || "")
                );

            arriveButton.disabled = demoMotionStillRunning;
            arriveButton.textContent = pickupMotionComplete
                ? "Arrived at Pickup"
                : "Arrived at Pickup";
        } else if (
            ["DRIVER_ARRIVED", "PICKUP_PENDING", "IN_PROGRESS", "COMPLETED"].includes(live.status)
        ) {
            arriveButton.disabled = true;
            arriveButton.textContent = "Arrival Confirmed";
        } else {
            arriveButton.disabled = true;
            arriveButton.textContent = "Arrived at Pickup";
        }
    }

    updatePickupSliderFromSnapshot(live);
    updateMainDriverAction(live);
    renderDriverSurvey(live);

    const status =
        document.querySelector(
            "#driver-status"
        );

    const tripId =
        document.querySelector(
            "#driver-trip-id"
        );

    const activeRideTitle =
        document.querySelector(
            "#driver-trip-title"
        );

    const activeRideDetail =
        document.querySelector(
            "#driver-trip-detail"
        );

    const activeRideEta =
        document.querySelector(
            "#driver-eta"
        );

    if (status) {
        status.textContent =
            destinationPhase &&
            live.status !== "COMPLETED"
                ? "IN_PROGRESS"
                : live.status;
    }

    if (tripId) {
        tripId.textContent =
            `#${live.trip_id}`;
    }

    if (activeRideEta) {
        activeRideEta.textContent =
            eta !== null &&
            eta !== undefined
                ? `${Math.max(
                    0,
                    Math.ceil(
                        Number(eta) / 60
                    )
                )} min`
                : "—";
    }

    if (activeRideTitle) {
        if (
            live.status === "COMPLETED"
        ) {
            activeRideTitle.textContent =
                "Ride complete";
        } else if (
            destinationPhase
        ) {
            activeRideTitle.textContent =
                "Driving to drop-off";
        } else if (
            live.status ===
            "PICKUP_PENDING"
        ) {
            activeRideTitle.textContent =
                "Waiting for passenger confirmation";
        } else if (
            live.status ===
            "DRIVER_ARRIVED"
        ) {
            activeRideTitle.textContent =
                "Passenger pickup";
        } else if (
            pickupPhase ||
            live.status ===
            "DRIVER_EN_ROUTE"
        ) {
            activeRideTitle.textContent =
                "Driving to passenger";
        } else {
            activeRideTitle.textContent =
                "Active ride";
        }
    }

    if (activeRideDetail) {
        if (
            destinationPhase
        ) {
            activeRideDetail.textContent =
                `Drop-off progress ${progress}%` +
                (
                    eta !== null &&
                    eta !== undefined
                        ? ` • ETA ${Math.max(
                            0,
                            Math.ceil(
                                Number(eta)
                                / 60
                            )
                        )} min`
                        : ""
                );
        } else if (
            live.status ===
            "PICKUP_PENDING"
        ) {
            activeRideDetail.textContent =
                "The passenger must confirm they are in the vehicle before the ride can continue.";
        } else if (
            pickupPhase ||
            live.status ===
            "DRIVER_EN_ROUTE"
        ) {
            activeRideDetail.textContent =
                `Pickup progress ${progress}%` +
                (
                    eta !== null &&
                    eta !== undefined
                        ? ` • ETA ${Math.max(
                            0,
                            Math.ceil(
                                Number(eta)
                                / 60
                            )
                        )} min`
                        : ""
                );
        } else if (
            live.status ===
            "COMPLETED"
        ) {
            activeRideDetail.textContent =
                "Destination reached.";
        }
    }

    if (detail) {
        const phaseName =
            destinationPhase
                ? "Drop-off progress"
                : "Pickup progress";

        detail.textContent =
            `${phaseName} ${progress}%` +
            (
                eta !== null &&
                eta !== undefined
                    ? ` • ETA ${Math.max(0, Math.ceil(eta / 60))} min`
                    : ""
            );
    }

    if (phaseEyebrow) {
        if (destinationPhase) {
            phaseEyebrow.textContent =
                "DRIVER TO DROPOFF";
        } else if (
            live.status ===
            "PICKUP_PENDING"
        ) {
            phaseEyebrow.textContent =
                "PICKUP CONFIRMATION";
        } else if (
            live.status ===
            "DRIVER_ARRIVED"
        ) {
            phaseEyebrow.textContent =
                "PASSENGER PICKUP";
        } else {
            phaseEyebrow.textContent =
                "DRIVER TO PASSENGER";
        }
    }

    if (
        live.status ===
        "DRIVER_ASSIGNED" &&
        !destinationPhase
    ) {
        stopDriverPickupWaitTicker();

        if (phaseEyebrow) {
            phaseEyebrow.textContent =
                "DRIVER TO PASSENGER";
        }

        if (title) {
            title.textContent =
                "Ready to drive to passenger";
        }

        if (startButton) {
            startButton.disabled =
                false;
            startButton.textContent =
                "Start Driving";
        }

        if (stopButton) {
            stopButton.disabled =
                true;
        }
    }

    if (
        live.status ===
        "DRIVER_EN_ROUTE" &&
        !destinationPhase
    ) {
        stopDriverPickupWaitTicker();

        if (phaseEyebrow) {
            phaseEyebrow.textContent =
                "DRIVER TO PASSENGER";
        }

        if (title) {
            title.textContent = pickupMotionComplete
                ? "At pickup — confirm arrival"
                : "Driving to passenger…";
        }

        if (detail && pickupMotionComplete) {
            detail.textContent =
                "You reached the pickup point. Press Arrived at Pickup to notify the passenger and start their waiting timer.";
        }

        if (startButton) {
            startButton.disabled = true;
            startButton.textContent = pickupMotionComplete
                ? "Pickup Route Complete"
                : "Driving…";
        }

        if (stopButton) {
            stopButton.disabled = pickupMotionComplete;
        }
    }

    if (
        live.status ===
        "PICKUP_PENDING"
    ) {
        stopDriverPickupWaitTicker();

        if (phaseEyebrow) {
            phaseEyebrow.textContent =
                "PICKUP CONFIRMATION";
        }

        if (title) {
            title.textContent =
                "Waiting for passenger confirmation";
        }

        if (detail) {
            detail.textContent =
                "You cannot continue the ride until the passenger confirms they are in the vehicle.";
        }

        if (startButton) {
            startButton.disabled =
                true;
            startButton.textContent =
                "Waiting for Passenger";
        }

        if (stopButton) {
            stopButton.disabled =
                true;
        }
    }

    if (
        live.status ===
        "IN_PROGRESS" ||
        destinationPhase
    ) {
        stopDriverPickupWaitTicker();

        const destinationRunning =
            destinationPhase &&
            live.simulation?.status
                === "RUNNING";

        if (phaseEyebrow) {
            phaseEyebrow.textContent =
                "DRIVER TO DROPOFF";
        }

        if (title) {
            title.textContent =
                destinationRunning
                    ? "Driving to drop-off…"
                    : "Passenger confirmed — ready for drop-off";
        }

        if (detail) {
            detail.textContent =
                destinationRunning
                    ? `Drop-off progress ${progress}%` +
                      (
                          eta !== null &&
                          eta !== undefined
                              ? ` • ETA ${Math.max(0, Math.ceil(eta / 60))} min`
                              : ""
                      )
                    : "The passenger confirmed they are in the vehicle. Press Continue Ride to begin broker-controlled movement to the drop-off.";
        }

        if (startButton) {
            startButton.disabled =
                destinationRunning;
            startButton.textContent =
                destinationRunning
                    ? "Driving…"
                    : "Continue Ride";
        }

        if (stopButton) {
            stopButton.disabled =
                !destinationRunning;
        }
    }

    if (
        live.status ===
        "DRIVER_ARRIVED" &&
        !destinationPhase
    ) {
        if (phaseEyebrow) {
            phaseEyebrow.textContent =
                "PASSENGER PICKUP";
        }

        if (title) {
            title.textContent =
                "Arrived at passenger";
        }

        if (startButton) {
            startButton.disabled =
                true;
        }

        if (stopButton) {
            stopButton.disabled =
                true;
        }

        startDriverPickupWaitTicker(
            live
        );
    }

    if (
        live.status === "COMPLETED" ||
        live.status === "CANCELED"
    ) {
        stopDriverPickupWaitTicker();

        if (phaseEyebrow) {
            phaseEyebrow.textContent =
                live.status === "COMPLETED"
                    ? "RIDE COMPLETE"
                    : "RIDE CANCELED";
        }

        if (
            live.status === "COMPLETED" &&
            title
        ) {
            title.textContent =
                "Arrived at drop-off";
        }

        if (startButton) {
            startButton.disabled =
                true;
        }

        if (stopButton) {
            stopButton.disabled =
                true;
        }
    }
}




function updatePickupSliderFromSnapshot(live) {
    const slider = document.querySelector("#pickup-passenger-slider");
    const value = document.querySelector("#pickup-slider-value");
    const title = document.querySelector("#pickup-confirm-title");
    const detail = document.querySelector("#pickup-confirm-detail");
    const pickupButton = document.querySelector("#claim-passenger-pickup");

    if (!slider || !value || !title || !detail) {
        return;
    }

    const destinationPhase =
        live.simulation?.phase
            === "TO_DESTINATION";

    if (destinationPhase) {
        slider.disabled = true;
        slider.value = "100";
        value.textContent = "100%";
        title.textContent =
            "Passenger confirmed";
        detail.textContent =
            "Pickup is complete. The passenger and driver are traveling together to the drop-off.";
        if (pickupButton) {
            pickupButton.disabled = true;
            pickupButton.textContent = "Pickup Complete";
        }
        return;
    }

    if (live.status === "DRIVER_ARRIVED") {
        slider.disabled = false;
        slider.value = "0";
        value.textContent = "0%";
        title.textContent = "Passenger ready for pickup";
        detail.textContent =
            "When the passenger is physically in the vehicle, press Pick Up Passenger or use the slider.";
        if (pickupButton) {
            pickupButton.disabled = false;
            pickupButton.textContent = "Pick Up Passenger";
        }
        return;
    }

    if (live.status === "PICKUP_PENDING") {
        slider.disabled = true;
        slider.value = "100";
        value.textContent = "100%";
        title.textContent = "Waiting for passenger confirmation";
        detail.textContent =
            "Pickup was recorded in the database. The ride cannot continue until the passenger confirms.";
        if (pickupButton) {
            pickupButton.disabled = true;
            pickupButton.textContent = "Waiting for Passenger";
        }
        return;
    }

    if (["IN_PROGRESS", "COMPLETED"].includes(live.status)) {
        slider.disabled = true;
        slider.value = "100";
        value.textContent = "100%";
        title.textContent =
            live.status === "COMPLETED"
                ? "Trip pickup complete"
                : "Passenger confirmed";
        detail.textContent =
            live.status === "COMPLETED"
                ? "The ride reached the drop-off."
                : "The passenger confirmed pickup and the ride is now underway.";
        if (pickupButton) {
            pickupButton.disabled = true;
            pickupButton.textContent = "Pickup Complete";
        }
        return;
    }

    slider.disabled = true;
    slider.value = "0";
    value.textContent = "0%";
    title.textContent = "Arrive at passenger first";
    detail.textContent =
        "Pickup unlocks after the driver reaches the passenger.";
    if (pickupButton) {
        pickupButton.disabled = true;
        pickupButton.textContent = "Pick Up Passenger";
    }
}

async function markDriverArrived() {
    if (!currentTripId || currentTripStatus !== "DRIVER_EN_ROUTE") {
        return;
    }

    const button = document.querySelector("#mark-driver-arrived");
    if (button) {
        button.disabled = true;
        button.textContent = "Confirming Arrival…";
    }

    driverWsLog(
        "DRIVER ARRIVAL REQUEST",
        {trip_id: currentTripId}
    );

    const response = await fetch(
        `/trips/${currentTripId}/arrive`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                driver_id: demoDriverId,
            }),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        driverWsLog(
            "DRIVER ARRIVAL FAILED",
            data
        );
        if (button) {
            button.disabled = false;
            button.textContent = "Arrived at Pickup";
        }
        return;
    }

    currentTripStatus = data.status;
    driverWsLog(
        "DRIVER ARRIVAL STORED",
        data
    );

    if (button) {
        button.disabled = true;
        button.textContent = "Arrival Confirmed";
    }
}


async function claimPassengerPickup() {
    if (!currentTripId) {
        return;
    }

    driverWsLog(
        "PICKUP CLAIM REQUEST",
        {
            trip_id: currentTripId,
        }
    );

    const response = await fetch(
        `/trips/${currentTripId}/pickup-claim`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                driver_id: demoDriverId,
            }),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        driverWsLog(
            "PICKUP CLAIM FAILED",
            data
        );

        const slider =
            document.querySelector("#pickup-passenger-slider");
        const value =
            document.querySelector("#pickup-slider-value");

        if (slider) {
            slider.value = "0";
            slider.disabled = false;
        }

        if (value) {
            value.textContent = "0%";
        }

        const pickupButton = document.querySelector("#claim-passenger-pickup");
        if (pickupButton && currentTripStatus === "DRIVER_ARRIVED") {
            pickupButton.disabled = false;
            pickupButton.textContent = "Pick Up Passenger";
        }

        return;
    }

    driverWsLog(
        "PICKUP CLAIM STORED",
        data
    );

    const action =
        document.querySelector("#accept-offer");

    if (action) {
        action.textContent =
            "Waiting for Passenger";
        action.disabled = true;
    }

    const pickupButton = document.querySelector("#claim-passenger-pickup");
    if (pickupButton) {
        pickupButton.textContent = "Waiting for Passenger";
        pickupButton.disabled = true;
    }
}

const driverArrivedButton =
    document.querySelector("#mark-driver-arrived");

driverArrivedButton?.addEventListener(
    "click",
    async () => {
        await markDriverArrived();
    }
);


const pickupPassengerButton =
    document.querySelector("#claim-passenger-pickup");

pickupPassengerButton?.addEventListener(
    "click",
    async () => {
        if (currentTripStatus !== "DRIVER_ARRIVED") {
            return;
        }
        pickupPassengerButton.disabled = true;
        pickupPassengerButton.textContent = "Recording Pickup…";
        await claimPassengerPickup();
    }
);

const pickupPassengerSlider =
    document.querySelector("#pickup-passenger-slider");

pickupPassengerSlider?.addEventListener(
    "input",
    () => {
        const value =
            document.querySelector("#pickup-slider-value");

        if (value) {
            value.textContent =
                `${pickupPassengerSlider.value}%`;
        }
    }
);

pickupPassengerSlider?.addEventListener(
    "change",
    async () => {
        const amount =
            Number(pickupPassengerSlider.value);

        if (amount < 95) {
            pickupPassengerSlider.value = "0";

            const value =
                document.querySelector("#pickup-slider-value");

            if (value) {
                value.textContent = "0%";
            }

            return;
        }

        pickupPassengerSlider.value = "100";
        pickupPassengerSlider.disabled = true;

        const value =
            document.querySelector("#pickup-slider-value");

        if (value) {
            value.textContent = "100%";
        }

        await claimPassengerPickup();
    }
);

const chatLog = document.querySelector("#chat-log");
const chatInput = document.querySelector("#chat-input");
const chatSend = document.querySelector("#chat-send");

function appendChat(message) {
    if (!chatLog) return;

    const row = document.createElement("div");
    row.className =
        `chat-message ${message.sender_role.toLowerCase()}`;

    row.innerHTML = `
        <strong>${message.sender_name}</strong>
        <span>${message.body}</span>
        <small>${new Date(message.created_at).toLocaleTimeString()}</small>
    `;

    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
}

async function loadChat() {
    if (!chatLog) return;

    const response = await fetch("/messages/");
    const messages = await response.json();

    chatLog.innerHTML = "";
    messages.forEach(appendChat);
}

async function sendChat() {
    const body = chatInput?.value.trim();

    if (!body) return;

    await fetch(
        "/messages/",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                trip_id: currentTripId,
                sender_role: "DRIVER",
                sender_name: currentDriver?.name || "Driver",
                recipient_role: "PASSENGER",
                body,
            }),
        }
    );

    chatInput.value = "";
}

chatSend?.addEventListener("click", sendChat);

chatInput?.addEventListener(
    "keydown",
    (event) => {
        if (event.key === "Enter") {
            sendChat();
        }
    }
);

document.querySelector("#ride-alert")?.addEventListener(
    "click",
    async (event) => {
        const tripId = Number(event.currentTarget?.dataset?.tripId || 0);
        let offer = currentPreviewOffer(tripId);

        if (!offer) {
            await loadActiveRequests();
            offer = currentPreviewOffer(tripId);
        }

        if (!offer) {
            return;
        }

        await previewOfferFromCurrentGps(offer);
    }
);

document.querySelector("#accept-offer")?.addEventListener(
    "click",
    async () => {
        const action =
            document.querySelector("#accept-offer");

        if (
            currentTripId &&
            action &&
            action.textContent.trim() === "Pick Up"
        ) {
            await claimPassengerPickup();
            return;
        }

        if (!currentOffer) {
            await loadActiveRequests();
        }

        if (
            !currentOffer ||
            !currentOffer.can_accept
        ) {
            return;
        }

        await acceptRide(
            currentOffer
        );
    }
);

document.querySelector("#decline-offer")?.addEventListener(
    "click",
    async () => {
        if (!currentOffer) {
            await loadActiveRequests();
        }

        if (!currentOffer || !currentOffer.can_decline) {
            return;
        }

        await declineRide(currentOffer);
    }
);

document.querySelector("#preview-pickup-route")?.addEventListener(
    "click",
    previewPickupRoute
);

document.querySelector("#start-pickup-sim")?.addEventListener(
    "click",
    startPickupSimulation
);

document.querySelector("#stop-pickup-sim")?.addEventListener(
    "click",
    stopPickupSimulation
);


function renderDriverSurvey(live) {
    const card =
        document.querySelector(
            "#driver-survey-card"
        );

    const submit =
        document.querySelector(
            "#driver-survey-submit"
        );

    const status =
        document.querySelector(
            "#driver-survey-status"
        );

    if (!card || !submit || !status) {
        return;
    }

    if (live.status !== "COMPLETED") {
        card.classList.add("hidden");
        return;
    }

    card.classList.remove("hidden");

    const submitted =
        Boolean(
            live.surveys?.driver_submitted
        );

    submit.disabled = submitted;

    status.textContent =
        submitted
            ? "Survey submitted. Thank you."
            : "Please rate the completed ride.";
}


async function submitDriverSurvey() {
    if (!currentTripId) {
        return;
    }

    const rating =
        document.querySelector(
            "#driver-survey-rating"
        );

    const comments =
        document.querySelector(
            "#driver-survey-comments"
        );

    const status =
        document.querySelector(
            "#driver-survey-status"
        );

    const response = await fetch(
        `/surveys/trips/${currentTripId}`,
        {
            method: "POST",
            headers: {
                "Content-Type":
                    "application/json",
            },
            body: JSON.stringify({
                role: "DRIVER",
                actor_id:
                    demoDriverId,
                rating:
                    Number(
                        rating?.value || 5
                    ),
                comments:
                    comments?.value || "",
            }),
        }
    );

    const data =
        await response.json();

    if (status) {
        status.textContent =
            response.ok
                ? "Survey submitted. Thank you."
                : (
                    data.error ||
                    "Could not submit survey."
                );
    }

    if (response.ok) {
        const button =
            document.querySelector(
                "#driver-survey-submit"
            );

        if (button) {
            button.disabled = true;
        }
    }
}


document
    .querySelector(
        "#driver-survey-submit"
    )
    ?.addEventListener(
        "click",
        submitDriverSurvey
    );


socket.on(
    "connect",
    () => {
        setDriverStreamState(
            "Socket connected"
        );

        driverWsLog(
            "CONNECTED",
            {
                socket_id:
                    socket.id,
                transport:
                    socket.io.engine
                        .transport.name,
            }
        );

        socket.emit(
            "register_driver",
            {
                driver_id:
                    demoDriverId,
            }
        );

        if (currentTripId) {
            joinDriverTripStream(
                currentTripId,
                "SOCKET_RECONNECT"
            );
        }
    }
);

socket.on(
    "connect_error",
    (error) => {
        setDriverStreamState(
            "Socket error"
        );

        driverWsLog(
            "CONNECT ERROR",
            {
                message:
                    error.message,
            }
        );
    }
);

socket.on(
    "disconnect",
    (reason) => {
        setDriverStreamState(
            "Socket disconnected"
        );

        driverWsLog(
            "DISCONNECTED",
            {
                reason,
            }
        );
    }
);

socket.io.on(
    "reconnect_attempt",
    (attempt) => {
        setDriverStreamState(
            `Reconnecting #${attempt}`
        );

        driverWsLog(
            "RECONNECT ATTEMPT",
            {
                attempt,
            }
        );
    }
);

socket.on(
    "connection_lifecycle",
    (data) => {
        driverWsLog(
            "CONNECTION LIFECYCLE",
            data
        );

        if (
            data.active_trip_id
        ) {
            currentTripId =
                Number(
                    data.active_trip_id
                );

            unlockPickupSimulation(
                currentTripId
            );
        }
    }
);

socket.on(
    "trip_lifecycle",
    (data) => {
        driverWsLog(
            "TRIP LIFECYCLE",
            data
        );

        if (data.phase === "JOINED") {
            setDriverStreamState(
                `Trip #${data.trip_id} joined`
            );
        }

        if (data.phase === "STATE_UPDATE") {
            setDriverStreamState(
                `${data.status} • streaming`
            );
        }

        if (data.phase === "TERMINAL") {
            setDriverStreamState(
                `${data.status} • closing`
            );
        }

        if (
            data.phase === "TERMINAL" &&
            currentTripId &&
            Number(data.trip_id) ===
                Number(currentTripId)
        ) {
            socket.emit(
                "leave_trip",
                {
                    trip_id:
                        currentTripId,
                    reason:
                        `TERMINAL_${data.status}`,
                }
            );
        }
    }
);

socket.on(
    "trip_snapshot",
    applyDriverTripSnapshot
);

socket.on(
    "driver_request_queue",
    (payload) => {
        lastDriverRequestQueue =
            payload.requests || [];

        driverWsLog(
            "DRIVER QUEUE",
            {
                count:
                    lastDriverRequestQueue.length,
            }
        );

        renderDriverRequestQueue(
            lastDriverRequestQueue
        );

        if (gpsRoutePreviewPending && !gpsRoutePreviewInFlight && !acceptedTripId) {
            gpsRoutePreviewPending = false;
            const offer = currentPreviewOffer();
            if (offer) {
                previewOfferFromCurrentGps(offer).catch(() => {});
            }
        }
    }
);


function refreshDriverDispatchCountdowns() {
    const requestByTrip =
        new Map(
            lastDriverRequestQueue.map(
                (request) => [
                    Number(request.trip_id),
                    request,
                ]
            )
        );

    document
        .querySelectorAll(
            ".request-item"
        )
        .forEach((row) => {
            const request =
                requestByTrip.get(
                    Number(
                        row.dataset.tripId
                    )
                );

            if (!request) {
                return;
            }

            const countdown =
                row.querySelector(
                    ".dispatch-countdown"
                );

            if (countdown) {
                countdown.textContent =
                    formatDispatchTimer(
                        request
                    );
            }

            const accept =
                row.querySelector(
                    ".accept-request"
                );

            if (
                accept &&
                request.my_offer_status === "WAITING"
            ) {
                const seconds = waitingSecondsRemaining(request);
                accept.textContent =
                    `Waiting ${formatClockSeconds(seconds)}`;

                const pill = row.querySelector(".pill");
                if (pill) {
                    pill.textContent =
                        `WAITING • offer in ${formatClockSeconds(seconds)}`;
                }
            }
        });

    if (currentOffer) {
        const timer =
            document.querySelector(
                "#offer-timer"
            );

        if (timer) {
            timer.textContent =
                formatDispatchTimer(
                    currentOffer
                );
        }

        if (currentOffer.my_offer_status === "WAITING") {
            const seconds = waitingSecondsRemaining(currentOffer);
            const waitingCountdown = document.querySelector(
                "#offer-waiting-countdown"
            );
            const accept = document.querySelector("#accept-offer");

            if (waitingCountdown) {
                waitingCountdown.textContent = formatClockSeconds(seconds);
            }

            if (accept) {
                accept.textContent = `Waiting ${formatClockSeconds(seconds)}`;
                accept.disabled = true;
            }
        }
    }
}

setInterval(
    refreshDriverDispatchCountdowns,
    1000
);


socket.on(
    "driver_location",
    (data) => {
        if (Number(data.driver_id) !== Number(demoDriverId)) {
            return;
        }

        setDriverLocation(
            data.latitude,
            data.longitude,
            false
        );

        // Route preview is GPS-driven while the driver is reviewing an offer.
        // The committed location is fetched back through the authoritative queue
        // first, then the preview endpoint rebuilds the road route from that
        // current DB location. This keeps the preview geometry and ETA aligned
        // with the same GPS position used by dispatch.
        if (!acceptedTripId) {
            gpsRoutePreviewPending = true;
        }

        loadActiveRequests().catch(() => {});
    }
);

socket.on(
    "review_fare",
    async (notice) => {
        driverWsLog(
            "REVIEW FARE NOTICE",
            notice
        );

        const alert =
            document.querySelector(
                "#ride-alert"
            );

        if (alert) {
            alert.dataset.tripId = String(notice.trip_id || "");
            alert.textContent =
                `Review Fare / Preview Route • $${Number(notice.fare || 0).toFixed(2)} ` +
                `• ${Number(notice.distance_miles || 0).toFixed(2)} mi from pickup`;
            alert.title = "Preview the live route from your current GPS location to pickup";

            alert.classList.remove(
                "hidden"
            );
        }

        await loadActiveRequests();
    }
);


socket.on(
    "ride_offer",
    async (offer) => {
        driverWsLog(
            "RIDE OFFER",
            {
                offered_trip_id:
                    offer.trip_id,
                rank:
                    offer.my_offer_rank,
                can_accept:
                    offer.can_accept,
            }
        );

        if (offer.can_accept) {
            hydrateOfferPanel(
                offer
            );
            previewPassengerTrip(
                offer
            );
        }

        await loadActiveRequests();
    }
);

socket.on(
    "trip_requested",
    () => {
        loadActiveRequests().catch(() => {});
    }
);

socket.on(
    "dispatch_update",
    () => {
        loadActiveRequests().catch(() => {});
    }
);

socket.on(
    "ride_accepted",
    async (data) => {
        driverWsLog(
            "RIDE ACCEPTED EVENT",
            data
        );

        await loadActiveRequests();

        if (
            Number(data.driver_id) ===
            Number(demoDriverId)
        ) {
            unlockPickupSimulation(
                data.trip_id
            );

            joinDriverTripStream(
                data.trip_id,
                "RIDE_ACCEPTED_EVENT"
            );
        }
    }
);

socket.on(
    "ride_canceled",
    async (data) => {
        if (
            currentOffer &&
            Number(data.trip_id) ===
            Number(currentOffer.trip_id)
        ) {
            resetOfferPanel("Ride request canceled");
        }

        if (
            acceptedTripId &&
            Number(data.trip_id) ===
            Number(acceptedTripId)
        ) {
            stopPickupSimulation();
            acceptedTripId = null;
            currentTripId = null;
            pickupRoute = null;

            const driveTitle =
                document.querySelector("#pickup-drive-title");
            const driveDetail =
                document.querySelector("#pickup-drive-detail");

            if (driveTitle) {
                driveTitle.textContent = "Ride canceled";
            }

            if (driveDetail) {
                driveDetail.textContent =
                    "The passenger canceled this ride.";
            }
        }

        await loadActiveRequests();
    }
);

socket.on("chat_message", appendChat);

Promise.all([
    loadDriverIdentity(),
    loadChat(),
]).catch((error) => {
    console.error(error);
});


if (window.DEMO_MODE) {
    const note =
        document.createElement("p");

    note.className = "muted";
    note.textContent =
        "Demo mode: click the map to write this driver's location to the database and immediately rebuild nearby ride queues.";

    document
        .querySelector("#map")
        .before(note);

    let demoLocationSaving = false;

    map.on(
        "click",
        async ({latlng}) => {
            if (demoLocationSaving) {
                return;
            }

            demoLocationSaving = true;

            note.textContent =
                `Saving ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)} to database…`;

            try {
                const response =
                    await fetch(
                        `/drivers/${demoDriverId}/demo-location`,
                        {
                            method:
                                "POST",

                            headers: {
                                "Content-Type":
                                    "application/json",
                            },

                            body:
                                JSON.stringify({
                                    latitude:
                                        latlng.lat,

                                    longitude:
                                        latlng.lng,
                                }),
                        }
                    );

                const result =
                    await response.json();

                if (!response.ok) {
                    throw new Error(
                        result.error
                        || "Location update failed"
                    );
                }

                // Reflect the exact location the server says was committed.
                setDriverLocation(
                    Number(
                        result.latitude
                    ),
                    Number(
                        result.longitude
                    ),
                    false
                );

                if (currentDriver) {
                    currentDriver.current_latitude =
                        Number(
                            result.latitude
                        );

                    currentDriver.current_longitude =
                        Number(
                            result.longitude
                        );
                }

                const memberships =
                    Array.isArray(
                        result.queue_memberships
                    )
                        ? result.queue_memberships
                        : [];

                const membershipText =
                    memberships.length
                        ? memberships
                            .map(
                                (item) =>
                                    `Trip #${item.trip_id}: ${item.status} • ` +
                                    `${item.distance_miles === null ? "—" : Number(item.distance_miles).toFixed(2)} mi / ` +
                                    `${Number(item.search_radius_miles || 0).toFixed(2)} mi radius` +
                                    (
                                        item.rank !== null
                                            ? ` • rank #${item.rank}`
                                            : ""
                                    )
                            )
                            .join(" | ")
                        : "No active passenger searches";

                note.textContent =
                    `DB location saved: ${Number(result.latitude).toFixed(5)}, ${Number(result.longitude).toFixed(5)} • ` +
                    `${membershipText}`;

                driverWsLog(
                    "DEMO LOCATION COMMITTED",
                    result
                );

                // The server already pushes queues, but explicitly requesting
                // ours makes the demo UI deterministic even after reconnects.
                await loadActiveRequests();

            } catch (error) {
                note.textContent =
                    error.message;

            } finally {
                demoLocationSaving =
                    false;
            }
        }
    );
}
socket.on("driver_request_queue", (data) => {
    const clock = data.requests?.find(item => item.server_time)?.server_time;
    if (clock) driverClockOffset = Date.parse(clock) - Date.now();
});
setInterval(() => {
    if (currentOffer && !acceptedTripId) {
        const timer = document.querySelector("#offer-timer");
        if (timer) {
            timer.textContent = formatDispatchTimer(currentOffer);
        }
    }
}, 250);

window.TripTiming.attach(socket);


function renderDriverAvailability(driver) {
    currentDriver = driver;
    const badge = document.querySelector("#driver-online-state");
    const button = document.querySelector("#driver-online-toggle");
    const detail = document.querySelector("#driver-online-detail");
    badge.textContent = driver.is_online ? "Online" : "Offline";
    badge.classList.toggle("online", driver.is_online);
    button.textContent = driver.is_online ? "Go Offline" : "Go Online";
    button.disabled = false;
    button.setAttribute("aria-pressed", String(driver.is_online));
    detail.textContent = driver.is_online
        ? (driver.is_available ? "You can receive nearby ride requests." : "You are online and serving a trip.")
        : "You are offline and will not receive new offers. Any accepted trip continues.";
}
document.querySelector("#driver-online-toggle").addEventListener("click", async () => {
    if (!currentDriver) return;
    const button = document.querySelector("#driver-online-toggle");
    button.disabled = true;
    try {
        const response = await fetch(`/drivers/${demoDriverId}/availability`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({is_online: !currentDriver.is_online}),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Unable to change availability");
        renderDriverAvailability(result);
        await loadActiveRequests();
    } catch (error) {
        document.querySelector("#driver-online-detail").textContent = error.message;
    } finally { button.disabled = false; }
});
socket.on("driver_availability", driver => {
    if (Number(driver.id) === demoDriverId) renderDriverAvailability(driver);
});
