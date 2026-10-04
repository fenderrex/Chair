const cancelRideButton = document.querySelector("#cancel-ride");
const requestRideButton = document.querySelector("#request");
const estimateRideButton = document.querySelector("#estimate");
const useLocationButton = document.querySelector("#use-location");
const pickupLat = document.querySelector("#pickup-lat");
const pickupLng = document.querySelector("#pickup-lng");
const destLat = document.querySelector("#dest-lat");
const destLng = document.querySelector("#dest-lng");

const fareEl = document.querySelector("#fare");
const distanceEl = document.querySelector("#distance");
const durationEl = document.querySelector("#duration");
const etaEl = document.querySelector("#eta");
const providerEl = document.querySelector("#provider");
const tripStatusEl = document.querySelector("#trip-status");
const statusDetailEl = document.querySelector("#status-detail");
const progressBar = document.querySelector("#progress-bar");
const startDemoButton = null;

let currentTripId = null;
let currentRoute = null;
let simulationTimer = null;
let lastPassengerStepSequence = 0;

const passengerLifecycle = new window.RideLifecycleManager({
    role: "passenger",
    defaultDemoMode: false,
    toggleSelector: "#passenger-lifecycle-demo",
});

const map = L.map("map", { zoomControl: false }).setView(
    [parseFloat(pickupLat.value), parseFloat(pickupLng.value)],
    12
);

L.control.zoom({ position: "bottomleft" }).addTo(map);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

function markerIcon(kind) {
    return L.divIcon({
        className: "",
        html: `<div class="custom-pin ${kind}"></div>`,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
    });
}

const passengerMarker = L.marker(
    [parseFloat(pickupLat.value), parseFloat(pickupLng.value)],
    { icon: markerIcon("passenger") }
).addTo(map);

const destinationMarker = L.marker(
    [parseFloat(destLat.value), parseFloat(destLng.value)],
    { icon: markerIcon("destination") }
).addTo(map);

const driverMarker = L.marker(
    [parseFloat(pickupLat.value) - 0.015, parseFloat(pickupLng.value) - 0.015],
    { icon: markerIcon("driver") }
).addTo(map);

let routeLayer = null;

const searchRadiusCircle = L.circle(
    [
        parseFloat(pickupLat.value),
        parseFloat(pickupLng.value),
    ],
    {
        radius: 0,
        weight: 2,
        fillOpacity: 0.06,
    }
).addTo(map);

function renderPassengerSearchRadius(live) {
    const dispatch =
        live?.dispatch || {};

    const radiusMiles =
        Number(
            dispatch.search_radius_miles
            || 0
        );

    const pickup =
        live?.pickup;

    if (
        pickup &&
        Number.isFinite(
            Number(pickup.latitude)
        ) &&
        Number.isFinite(
            Number(pickup.longitude)
        )
    ) {
        searchRadiusCircle.setLatLng([
            Number(pickup.latitude),
            Number(pickup.longitude),
        ]);
    }

    searchRadiusCircle.setRadius(
        Math.max(
            0,
            radiusMiles * 1609.344
        )
    );
}


function appendPassengerStepNotice(notice, flash = false) {
    if (!notice) return;

    const sequence =
        Number(notice.sequence || 0);

    if (
        sequence &&
        sequence <= lastPassengerStepSequence
    ) {
        return;
    }

    if (sequence) {
        lastPassengerStepSequence =
            Math.max(
                lastPassengerStepSequence,
                sequence
            );
    }

    const list =
        document.querySelector(
            "#passenger-step-list"
        );

    if (list) {
        if (
            list.children.length === 1 &&
            list.firstElementChild?.classList
                .contains("muted")
        ) {
            list.innerHTML = "";
        }

        const row =
            document.createElement("div");

        row.className =
            "broker-step-item";

        const seq =
            document.createElement(
                "strong"
            );

        seq.textContent =
            sequence
                ? `#${sequence}`
                : "•";

        const message =
            document.createElement(
                "span"
            );

        message.textContent =
            String(
                notice.message
                || "Ride update"
            );

        row.appendChild(seq);
        row.appendChild(message);
        list.appendChild(row);

        while (
            list.children.length > 20
        ) {
            list.removeChild(
                list.firstElementChild
            );
        }

        list.scrollTop =
            list.scrollHeight;
    }

    wsLog(
        "PASSENGER STEP",
        notice
    );

    if (flash) {
        showPassengerAlert(
            notice.message || "Ride update"
        );
    }
}


function hydratePassengerStepNotices(live) {
    const notices =
        Array.isArray(
            live?.recent_notices
        )
            ? live.recent_notices
            : [];

    notices.forEach(
        (notice) => {
            appendPassengerStepNotice(
                notice,
                false
            );
        }
    );
}


function setStatus(title, detail, progress = 0) {
    tripStatusEl.textContent = title;
    statusDetailEl.textContent = detail;
    progressBar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
}


function setRequestCreationEnabled(enabled) {
    if (requestRideButton) {
        requestRideButton.disabled = !enabled;
        requestRideButton.textContent = enabled
            ? "Request Ride"
            : "Active Ride in Progress";
    }

    if (estimateRideButton) {
        estimateRideButton.disabled = !enabled;
    }

    if (useLocationButton) {
        useLocationButton.disabled = !enabled;
    }

    [
        pickupLat,
        pickupLng,
        destLat,
        destLng,
    ].forEach((input) => {
        if (input) {
            input.disabled = !enabled;
        }
    });
}

function scrollToTripStatus() {
    const card =
        document.querySelector("#trip-status-card");

    if (!card) {
        return;
    }

    window.setTimeout(
        () => {
            card.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        },
        80
    );
}

function scrollToPickupConfirmation() {
    const card =
        document.querySelector(
            "#pickup-passenger-confirm-card"
        );

    if (!card) {
        return;
    }

    window.setTimeout(
        () => {
            card.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });

            const confirmButton =
                document.querySelector(
                    "#confirm-passenger-pickup"
                );

            if (
                confirmButton &&
                !confirmButton.disabled
            ) {
                confirmButton.focus({
                    preventScroll: true,
                });
            }
        },
        120
    );
}


function restoreTripFormFromSnapshot(live) {
    if (live.pickup) {
        pickupLat.value =
            Number(live.pickup.latitude).toFixed(6);

        pickupLng.value =
            Number(live.pickup.longitude).toFixed(6);

        passengerMarker.setLatLng([
            live.pickup.latitude,
            live.pickup.longitude,
        ]);
    }

    if (live.destination) {
        destLat.value =
            Number(live.destination.latitude).toFixed(6);

        destLng.value =
            Number(live.destination.longitude).toFixed(6);

        destinationMarker.setLatLng([
            live.destination.latitude,
            live.destination.longitude,
        ]);
    }

    if (live.route_geometry) {
        drawRoute({
            geometry: live.route_geometry,
        });
    }

    if (
        live.estimated_fare !== null &&
        live.estimated_fare !== undefined
    ) {
        fareEl.textContent =
            `$${Number(live.estimated_fare).toFixed(2)}`;
    }

    if (
        live.estimated_distance_meters !== null &&
        live.estimated_distance_meters !== undefined
    ) {
        distanceEl.textContent =
            `${(
                Number(live.estimated_distance_meters)
                / 1609.344
            ).toFixed(1)} mi`;
    }

    if (
        live.estimated_duration_seconds !== null &&
        live.estimated_duration_seconds !== undefined
    ) {
        durationEl.textContent =
            `${Math.ceil(
                Number(live.estimated_duration_seconds)
                / 60
            )} min`;
    }

    if (live.route_provider) {
        providerEl.textContent =
            String(live.route_provider).toUpperCase();
    }
}


let passengerAlertTimer = null;

function hidePassengerAlert() {
    const alert = document.querySelector("#passenger-alert");
    if (!alert) return;

    if (passengerAlertTimer) {
        window.clearTimeout(passengerAlertTimer);
        passengerAlertTimer = null;
    }

    alert.textContent = "";
    alert.classList.add("hidden");
}

function showPassengerAlert(message, keepVisible = false) {
    const alert = document.querySelector("#passenger-alert");
    if (!alert) return;

    if (passengerAlertTimer) {
        window.clearTimeout(passengerAlertTimer);
        passengerAlertTimer = null;
    }

    alert.textContent = message;
    alert.classList.remove("hidden");

    if (!keepVisible) {
        passengerAlertTimer = window.setTimeout(() => {
            alert.classList.add("hidden");
            passengerAlertTimer = null;
        }, 4500);
    }
}

function formatClock(totalSeconds) {
    const seconds = Math.max(0, Math.floor(Number(totalSeconds || 0)));
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function setPipelineStage(status) {
    const steps = Array.from(
        document.querySelectorAll("#trip-pipeline .pipeline-step")
    );
    const normalized = status === "OFFERED"
        ? "REQUESTED"
        : status === "PICKUP_PENDING"
        ? "DRIVER_ARRIVED"
        : status;
    const activeIndex = steps.findIndex(
        (step) => step.dataset.stage === normalized
    );

    steps.forEach((step, index) => {
        step.classList.toggle(
            "complete",
            status === "COMPLETED" || (activeIndex >= 0 && index < activeIndex)
        );
        step.classList.toggle("active", index === activeIndex);
    });
}

function renderAssignedDriver(driver, etaSeconds) {
    const name = document.querySelector("#driver-name");
    const vehicle = document.querySelector("#vehicle");
    const id = document.querySelector("#assigned-driver-id");
    const eta = document.querySelector("#assigned-driver-eta");
    const gps = document.querySelector("#assigned-driver-gps");
    const coordinates = document.querySelector("#assigned-driver-coordinates");
    const centerButton = document.querySelector("#center-driver");
    const pill = document.querySelector("#driver-state-pill");

    if (!driver) {
        if (name) name.textContent = "Waiting for a driver…";
        if (vehicle) {
            vehicle.textContent =
                "Driver and vehicle information will appear after a driver accepts.";
        }
        if (id) id.textContent = "—";
        if (eta) eta.textContent = "—";
        if (gps) gps.textContent = "—";
        if (coordinates) coordinates.textContent = "—";
        if (centerButton) centerButton.disabled = true;
        if (pill) pill.textContent = "Unassigned";
        return;
    }

    if (name) name.textContent = driver.name;
    if (id) id.textContent = `#${driver.id}`;

    if (eta) {
        eta.textContent =
            etaSeconds !== null && etaSeconds !== undefined
                ? etaSeconds <= 0
                    ? "Arrived"
                    : `${Math.max(1, Math.ceil(etaSeconds / 60))} min`
                : "—";
    }

    if (gps) {
        gps.textContent = driver.last_location_at
            ? new Date(driver.last_location_at).toLocaleTimeString()
            : "—";
    }

    if (coordinates) {
        coordinates.textContent =
            driver.latitude !== null &&
            driver.latitude !== undefined &&
            driver.longitude !== null &&
            driver.longitude !== undefined
                ? `${Number(driver.latitude).toFixed(6)}, ${Number(driver.longitude).toFixed(6)}`
                : "—";
    }

    if (centerButton) {
        centerButton.disabled = !(
            driver.latitude !== null &&
            driver.latitude !== undefined &&
            driver.longitude !== null &&
            driver.longitude !== undefined
        );

        centerButton.dataset.lat =
            driver.latitude ?? "";

        centerButton.dataset.lng =
            driver.longitude ?? "";
    }

    if (pill) pill.textContent = "Assigned";

    if (vehicle) {
        const v = driver.vehicle;

        vehicle.textContent = v
            ? `${v.year} ${v.color} ${v.make} ${v.model} • ${v.plate_state} ${v.plate}`
            : "Vehicle information not available.";
    }
}


function renderFareEscalation(live) {
    const card =
        document.querySelector("#fare-escalation-card");
    const title =
        document.querySelector("#fare-escalation-title");
    const detail =
        document.querySelector("#fare-escalation-detail");
    const original =
        document.querySelector("#fare-original");
    const multiplier =
        document.querySelector("#fare-multiplier");
    const next =
        document.querySelector("#fare-next");
    const accept =
        document.querySelector("#accept-fare-escalation");
    const decline =
        document.querySelector("#decline-fare-escalation");
    const status =
        document.querySelector("#fare-escalation-status");

    if (
        !card ||
        !title ||
        !detail ||
        !original ||
        !multiplier ||
        !next ||
        !accept ||
        !decline ||
        !status
    ) {
        return;
    }

    const escalation =
        live.fare_escalation;
    const dispatch =
        live.dispatch || {};

    const searchingForDriver =
        live.status === "REQUESTED" ||
        live.status === "OFFERED";

    // "No driver accepted" is a max-radius state. Never show the fare
    // escalation prompt during ordinary radius expansion, even if an older
    // snapshot still contains pending fare-review data.
    const maxSearchRadiusReached =
        dispatch.radius_capped === true;

    // Fare escalation belongs only to the active driver-search lifecycle.
    // Once a driver accepts, stale fare-review data must never reopen this card.
    if (
        !searchingForDriver ||
        !maxSearchRadiusReached ||
        !live.fare_review_pending ||
        !escalation ||
        escalation.status !== "PENDING"
    ) {
        card.classList.add("hidden");
        return;
    }

    card.classList.remove("hidden");

    title.textContent =
        `No driver accepted round ${live.fare_round || 0}`;

    detail.textContent =
        "The last driver has finished the response period. Approve the higher offer to send the request through another driver-search round.";

    original.textContent =
        `$${Number(
            escalation.original_fare
        ).toFixed(2)}`;

    multiplier.textContent =
        `${Number(
            escalation.multiplier
        ).toFixed(2)}×`;

    next.textContent =
        `$${Number(
            escalation.offered_fare
        ).toFixed(2)}`;

    accept.disabled = false;
    decline.disabled = false;

    accept.dataset.tripId =
        String(live.trip_id);

    decline.dataset.tripId =
        String(live.trip_id);

    status.textContent =
        `Round ${escalation.round_number}: your current fare remains $${Number(live.estimated_fare).toFixed(2)} until you approve.`;

    showPassengerAlert(
        `No driver accepted. Increase the offer to $${Number(escalation.offered_fare).toFixed(2)} and keep searching?`,
        true
    );
}

async function answerFareEscalation(
    accepted
) {
    if (!currentTripId) {
        return;
    }

    const accept =
        document.querySelector("#accept-fare-escalation");
    const decline =
        document.querySelector("#decline-fare-escalation");
    const status =
        document.querySelector("#fare-escalation-status");

    if (accept) {
        accept.disabled = true;
    }

    if (decline) {
        decline.disabled = true;
    }

    if (status) {
        status.textContent =
            accepted
                ? "Applying the new fare and restarting driver search…"
                : "Stopping this ride request…";
    }

    const action =
        accepted
            ? "accept"
            : "decline";

    const response = await fetch(
        `/trips/${currentTripId}/fare-escalation/${action}`,
        {
            method: "POST",
            headers: {
                "Content-Type":
                    "application/json",
            },
            body: JSON.stringify({
                passenger_id:
                    window.PASSENGER_USER_ID,
            }),
        }
    );

    const data =
        await response.json();

    if (!response.ok) {
        if (status) {
            status.textContent =
                data.error ||
                "Could not update the fare.";
        }

        if (accept) {
            accept.disabled = false;
        }

        if (decline) {
            decline.disabled = false;
        }

        return;
    }

    const fareEscalationCard =
        document.querySelector("#fare-escalation-card");

    if (fareEscalationCard) {
        fareEscalationCard.classList.add("hidden");
    }

    // The persistent question has been answered. Remove it immediately so the
    // passenger can see that their action took effect, then show a short
    // confirmation while the broker restarts the radius clock.
    hidePassengerAlert();

    if (accepted) {
        const increasedFare = Number(
            data.estimated_fare || 0
        );

        fareEl.textContent =
            `$${increasedFare.toFixed(2)}`;

        setStatus(
            "Searching again",
            `Fare increased to $${increasedFare.toFixed(2)}. The passenger search radius reset and is expanding again.`,
            25
        );

        showPassengerAlert(
            `Fare increased to $${increasedFare.toFixed(2)}. Nearby-driver search restarted from the smallest radius.`
        );
    }

    wsLog(
        accepted
            ? "FARE ESCALATION ACCEPTED"
            : "FARE ESCALATION DECLINED",
        data
    );
}

document
    .querySelector("#accept-fare-escalation")
    ?.addEventListener(
        "click",
        () => answerFareEscalation(true)
    );

document
    .querySelector("#decline-fare-escalation")
    ?.addEventListener(
        "click",
        () => answerFareEscalation(false)
    );


function renderPickupWait(live) {
    const card = document.querySelector("#pickup-wait-card");
    const clock = document.querySelector("#pickup-wait-time");
    const detail = document.querySelector("#pickup-wait-detail");

    if (!card || !clock || !detail) return;

    const waitingAtPickup = [
        "DRIVER_ARRIVED",
        "PICKUP_PENDING",
    ].includes(live.status);

    if (!waitingAtPickup) {
        card.classList.add("hidden");
        clock.textContent = "00:00";
        return;
    }

    card.classList.remove("hidden");
    clock.textContent = formatClock(live.pickup_wait_seconds);

    detail.textContent = live.status === "DRIVER_ARRIVED"
        ? "Your driver is at the pickup point. This waiting clock is coming from the trip record."
        : "Your driver is still at the pickup point while pickup confirmation is pending.";
}

function readCoords() {
    return {
        pickup_lat: parseFloat(pickupLat.value),
        pickup_lng: parseFloat(pickupLng.value),
        destination_lat: parseFloat(destLat.value),
        destination_lng: parseFloat(destLng.value),
    };
}

function updateMarkers() {
    const coords = readCoords();
    passengerMarker.setLatLng([coords.pickup_lat, coords.pickup_lng]);
    destinationMarker.setLatLng([coords.destination_lat, coords.destination_lng]);
}

function drawRoute(route) {
    currentRoute = route;
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }

    routeLayer = L.geoJSON(route.geometry, {
        style: {
            weight: 6,
            opacity: 0.82,
        },
    }).addTo(map);

    map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });
}

async function estimateRide() {
    updateMarkers();
    setStatus("Estimating", "Getting road distance, travel time, and fare…", 10);

    const response = await fetch("/trips/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readCoords()),
    });

    const data = await response.json();
    drawRoute(data.route);

    fareEl.textContent = `$${data.fare.estimated_total.toFixed(2)}`;
    distanceEl.textContent = `${data.route.distance_miles.toFixed(1)} mi`;
    durationEl.textContent = `${data.route.duration_minutes.toFixed(0)} min`;
    providerEl.textContent = data.route.provider.toUpperCase();

    if (data.route.is_fallback) {
        setStatus("Route service fallback", "Road routing is unavailable right now, so this preview is approximate.", 18);
    }

    setStatus(
        "Estimate ready",
        "The route estimate is now feeding the fare calculation.",
        22
    );

    return data;
}

async function requestRide() {
    const response = await fetch("/trips/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            ...readCoords(),
            passenger_id: window.PASSENGER_USER_ID,
            passenger_name: window.PASSENGER_NAME,
        }),
    });

    const data = await response.json();

    if (!response.ok) {
        if (
            data.code === "ACTIVE_TRIP_EXISTS" &&
            data.active_trip_id
        ) {
            currentTripId =
                Number(data.active_trip_id);

            setRequestCreationEnabled(false);

            joinTripStream(
                currentTripId,
                "DUPLICATE_REQUEST_RECOVERY"
            );

            setStatus(
                "Active ride already exists",
                `Trip #${currentTripId} is still active. Reconnected to that request instead of creating another one.`,
                28
            );

            scrollToTripStatus();
            return;
        }

        throw new Error(
            data.error ||
            `Ride request failed with HTTP ${response.status}`
        );
    }

    currentTripId = data.trip.trip_id ?? data.trip.id;

    setRequestCreationEnabled(false);

    if (cancelRideButton) {
        cancelRideButton.disabled = false;
    }

    drawRoute(data.route);
    fareEl.textContent = `$${data.fare.estimated_total.toFixed(2)}`;
    distanceEl.textContent = `${data.route.distance_miles.toFixed(1)} mi`;
    durationEl.textContent = `${data.route.duration_minutes.toFixed(0)} min`;
    providerEl.textContent = data.route.provider.toUpperCase();

    setPipelineStage("REQUESTED");

    setStatus(
        "Searching for your driver",
        "Nearby drivers are being offered the ride according to arrival possibility and response time.",
        24
    );

    renderAssignedDriver(null, null);

    joinTripStream(
        currentTripId,
        "REQUEST_CREATED"
    );

    scrollToTripStatus();
}

function routeCoordinates() {
    if (!currentRoute || !currentRoute.geometry) return [];

    return currentRoute.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
}

async function sendDriverLocation(lat, lng, progress) {
    if (!currentTripId) return;

    await fetch("/location/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            trip_id: currentTripId,
            actor_type: "driver",
            latitude: lat,
            longitude: lng,
            heading: null,
            speed: 11.5,
        }),
    });

    const minutesLeft = Math.max(
        0,
        Math.ceil(
            parseFloat(durationEl.textContent || "0") *
            (1 - progress)
        )
    );

    etaEl.textContent = progress >= 1 ? "Arrived" : `${minutesLeft} min`;
}

function startSimulation() {
    clearInterval(simulationTimer);

    const coords = routeCoordinates();
    if (coords.length < 2) return;

    let index = 0;
    const maxIndex = coords.length - 1;

    setStatus(
        "Trip in progress",
        "Live driver location is being streamed to the passenger map.",
        35
    );

    simulationTimer = setInterval(async () => {
        const point = coords[index];
        const progress = index / maxIndex;

        driverMarker.setLatLng(point);
        await sendDriverLocation(point[0], point[1], progress);

        setStatus(
            progress >= 1 ? "Arrived" : "Trip in progress",
            progress >= 1
                ? "The simulated driver reached the passenger-selected destination."
                : "Driver position, ETA, and progress are updating live.",
            35 + progress * 65
        );

        index += Math.max(1, Math.ceil(coords.length / 90));

        if (index > maxIndex) {
            driverMarker.setLatLng(coords[maxIndex]);
            clearInterval(simulationTimer);
            etaEl.textContent = "Arrived";
            setStatus(
                "Arrived",
                "Demo complete. The driver reached the passenger-selected destination.",
                100
            );
        }
    }, 550);
}

map.on("click", async (event) => {
    if (
        requestRideButton &&
        requestRideButton.disabled &&
        currentTripId
    ) {
        setStatus(
            "Active ride in progress",
            "Finish or cancel the current ride before changing the destination.",
            Number(progressBar.style.width.replace("%", "")) || 28
        );
        return;
    }

    destLat.value = event.latlng.lat.toFixed(6);
    destLng.value = event.latlng.lng.toFixed(6);
    destinationMarker.setLatLng(event.latlng);

    try {
        await estimateRide();
    } catch (error) {
        setStatus("Route error", "Could not calculate a route.", 0);
    }
});

useLocationButton?.addEventListener("click", () => {
    if (!navigator.geolocation) {
        setStatus("GPS unavailable", "This browser does not expose geolocation.", 0);
        return;
    }

    setStatus("Locating", "Waiting for browser GPS permission…", 5);

    navigator.geolocation.getCurrentPosition(
        (position) => {
            pickupLat.value = position.coords.latitude.toFixed(6);
            pickupLng.value = position.coords.longitude.toFixed(6);
            passengerMarker.setLatLng([
                position.coords.latitude,
                position.coords.longitude,
            ]);
            map.setView(
                [position.coords.latitude, position.coords.longitude],
                14
            );
            setStatus(
                "Pickup updated",
                "Your current GPS position is now the passenger pickup point.",
                8
            );
        },
        () => {
            setStatus(
                "Location permission denied",
                "You can still enter a pickup manually.",
                0
            );
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 3000,
        }
    );
});

document.querySelector("#estimate").addEventListener("click", async () => {
    try {
        await estimateRide();
    } catch (error) {
        setStatus("Estimate failed", "Could not calculate this trip.", 0);
    }
});

requestRideButton?.addEventListener("click", async () => {
    try {
        await requestRide();
    } catch (error) {
        setStatus("Request failed", "Could not create the demo trip.", 0);
    }
});



// ID processor button removed from passenger screen.
/*
    const output = document.querySelector("#id-result");
    output.textContent = "Processing demo driver's license…";

    const response = await fetch("/id-processing/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            filename: "demo-license.jpg",
            document_type: "drivers_license",
        }),
    });

    const data = await response.json();
    output.textContent = JSON.stringify(data, null, 2);
});
*/

const socket = io({
    transports: ["websocket"],
    upgrade: false,
    timeout: 10000,
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 500,
    reconnectionDelayMax: 3000,
});


let streamedTripSnapshot = null;
let pickupWaitTicker = null;
let pickupWaitTickerKey = null;
let pickupWaitBaseSeconds = 0;
let pickupWaitBaseAtMs = 0;

function setPassengerStreamState(
    text
) {
    const pill =
        document.querySelector(
            "#passenger-stream-state"
        );

    if (pill) {
        pill.textContent = text;
    }
}

function wsLog(event, detail = {}) {
    console.log(
        `[PASSENGER WS] ${event}`,
        {
            time: new Date().toISOString(),
            trip_id: currentTripId,
            passenger_id: window.PASSENGER_USER_ID,
            ...detail,
        }
    );
}

function joinTripStream(tripId, reason = "CLIENT_JOIN") {
    if (!tripId || !socket.connected) {
        wsLog(
            "JOIN DEFERRED",
            {
                requested_trip_id: tripId,
                reason,
                connected: socket.connected,
            }
        );
        return;
    }

    wsLog(
        "JOIN TRIP",
        {
            requested_trip_id: tripId,
            reason,
        }
    );

    socket.emit(
        "join_trip",
        {
            trip_id: Number(tripId),
            role: "PASSENGER",
            actor_id: window.PASSENGER_USER_ID,
            reason,
        }
    );
}

function stopPickupWaitTicker() {
    if (pickupWaitTicker) {
        clearInterval(pickupWaitTicker);
        pickupWaitTicker = null;
    }

    pickupWaitTickerKey = null;
    pickupWaitBaseSeconds = 0;
    pickupWaitBaseAtMs = 0;
}

function currentPickupWaitSeconds() {
    if (!pickupWaitBaseAtMs) {
        return Math.max(0, Math.floor(pickupWaitBaseSeconds));
    }

    return Math.max(
        0,
        Math.floor(pickupWaitBaseSeconds) +
            Math.floor((Date.now() - pickupWaitBaseAtMs) / 1000)
    );
}

function updatePickupWaitFromTimestamp(snapshot) {
    if (
        !snapshot ||
        !snapshot.driver_arrived_at ||
        !["DRIVER_ARRIVED", "PICKUP_PENDING"].includes(snapshot.status)
    ) {
        stopPickupWaitTicker();
        return;
    }

    const tickerKey =
        `${Number(snapshot.trip_id || 0)}:${String(snapshot.driver_arrived_at)}`;
    const serverSeconds = Math.max(
        0,
        Math.floor(Number(snapshot.pickup_wait_seconds || 0))
    );

    if (pickupWaitTickerKey !== tickerKey) {
        stopPickupWaitTicker();
        pickupWaitTickerKey = tickerKey;
        pickupWaitBaseSeconds = serverSeconds;
        pickupWaitBaseAtMs = Date.now();
    } else {
        const localSeconds = currentPickupWaitSeconds();
        if (serverSeconds > localSeconds) {
            pickupWaitBaseSeconds = serverSeconds;
            pickupWaitBaseAtMs = Date.now();
        }
    }

    const updateClock = () => {
        const card = document.querySelector("#pickup-wait-card");
        const clock = document.querySelector("#pickup-wait-time");

        if (!card || !clock) {
            return;
        }

        card.classList.remove("hidden");
        clock.textContent = formatClock(currentPickupWaitSeconds());
    };

    updateClock();

    if (!pickupWaitTicker) {
        pickupWaitTicker = setInterval(updateClock, 1000);
    }
}

function applyPassengerTripSnapshot(envelope) {
    const live = envelope?.snapshot;

    if (!live) {
        wsLog("SNAPSHOT IGNORED", {
            reason: "missing snapshot",
        });
        return;
    }

    if (
        currentTripId &&
        Number(live.trip_id) !== Number(currentTripId)
    ) {
        wsLog(
            "SNAPSHOT IGNORED",
            {
                reason: "different trip",
                snapshot_trip_id: live.trip_id,
            }
        );
        return;
    }

    currentTripId = Number(live.trip_id);
    streamedTripSnapshot = live;
    if (typeof passengerLifecycle !== "undefined") {
        passengerLifecycle.update(live);
    }

    hydratePassengerStepNotices(
        live
    );

    setPipelineStage(live.status);
    restoreTripFormFromSnapshot(live);

    if (
        live.passenger_location &&
        Number.isFinite(
            Number(
                live.passenger_location.latitude
            )
        ) &&
        Number.isFinite(
            Number(
                live.passenger_location.longitude
            )
        )
    ) {
        passengerMarker.setLatLng([
            Number(
                live.passenger_location.latitude
            ),
            Number(
                live.passenger_location.longitude
            ),
        ]);
    }

    renderPassengerSearchRadius(live);

    const terminal =
        ["COMPLETED", "CANCELED"].includes(
            live.status
        );

    setRequestCreationEnabled(terminal);

    if (cancelRideButton) {
        cancelRideButton.disabled =
            ["COMPLETED", "CANCELED"].includes(live.status);
    }

    wsLog(
        "SNAPSHOT",
        {
            reason: envelope.reason,
            status: live.status,
            progress: live.progress_percent,
            eta_seconds: live.driver_eta_seconds,
            driver_id: live.driver?.id ?? null,
            dispatch: live.dispatch,
        }
    );

    renderAssignedDriver(
        live.driver,
        live.driver_eta_seconds
    );
    renderPickupWait(live);
    renderFareEscalation(live);
    renderReviewingDrivers(live);
    renderPickupConfirmation(live);
    renderPassengerSurvey(live);
    updatePickupWaitFromTimestamp(live);

    if (cancelRideButton) {
        cancelRideButton.disabled =
            Boolean(live.cancel_locked) ||
            ["COMPLETED", "CANCELED"].includes(live.status);

        cancelRideButton.textContent =
            live.cancel_locked
                ? "Cancellation Locked"
                : "Cancel Ride";
    }

    if (
        live.driver &&
        live.driver.latitude !== null &&
        live.driver.longitude !== null
    ) {
        driverMarker.setLatLng([
            live.driver.latitude,
            live.driver.longitude,
        ]);
    }

    const progress = Math.round(
        Number(live.progress_percent || 0)
    );

    const eta = live.driver_eta_seconds;

    if (
        live.status === "REQUESTED" ||
        live.status === "OFFERED"
    ) {
        const dispatch = live.dispatch || {};
        let detail =
            "Looking for the best-arriving available driver.";

        if (
            live.fare_wait_until &&
            !live.fare_review_pending &&
            Number(dispatch.waiting_offer_count || 0) === 0
        ) {
            const seconds = Math.max(
                0,
                Math.ceil(
                    (
                        new Date(
                            live.fare_wait_until
                        ).getTime()
                        - Date.now()
                    ) / 1000
                )
            );

            detail =
                `The last driver has been offered the ride • waiting ${seconds}s before asking about a higher offer.`;
        }

        if (
            dispatch.seconds_until_expand !== null &&
            dispatch.seconds_until_expand !== undefined
        ) {
            detail =
                `${dispatch.open_offer_count || 0} driver(s) eligible now • ` +
                `next runner-up in ${dispatch.seconds_until_expand}s`;
        } else if (
            (dispatch.open_offer_count || 0) > 0
        ) {
            detail =
                `${dispatch.open_offer_count} driver(s) can accept your ride now.`;
        }

        setStatus(
            "Finding your driver",
            detail,
            28
        );
    }

    if (live.status === "DRIVER_ASSIGNED") {
        setStatus(
            "Driver assigned",
            live.driver
                ? `${live.driver.name} accepted and is preparing to drive to your pickup.`
                : "Your driver accepted the ride.",
            38
        );
    }

    if (live.status === "DRIVER_EN_ROUTE") {
        setStatus(
            "Driver approaching",
            `${live.driver?.name || "Your driver"} is moving toward your pickup • ${progress}%` +
            (
                eta !== null && eta !== undefined
                    ? ` • ETA ${Math.max(1, Math.ceil(eta / 60))} min`
                    : ""
            ),
            40 + progress * 0.35
        );
    }

    if (live.status === "DRIVER_ARRIVED") {
        setStatus(
            "Driver arrived",
            `${live.driver?.name || "Your driver"} is waiting at your pickup.`,
            75
        );

        etaEl.textContent = "Arrived";

        const alert =
            document.querySelector("#passenger-alert");

        if (
            alert &&
            !alert.dataset.arrivalShown
        ) {
            alert.dataset.arrivalShown = "1";

            showPassengerAlert(
                `${live.driver?.name || "Your driver"} has arrived at your pickup.`,
                true
            );
        }
    }

    if (live.status === "PICKUP_PENDING") {
        setStatus(
            "Confirm pickup",
            `${live.driver?.name || "Your driver"} marked you as picked up. Confirm once you are inside the vehicle.`,
            78
        );

        showPassengerAlert(
            `${live.driver?.name || "Your driver"} marked you as picked up. Please confirm.`,
            true
        );
    }

    if (live.status === "IN_PROGRESS") {
        setStatus(
            "Trip in progress",
            "Pickup is confirmed. You are on the way to your destination.",
            82
        );
    }

    if (live.status === "COMPLETED") {
        stopPickupWaitTicker();
        setRequestCreationEnabled(true);

        setStatus(
            "Trip complete",
            "This trip is complete. You can request another ride.",
            100
        );
    }

    if (live.status === "CANCELED") {
        stopPickupWaitTicker();
        setRequestCreationEnabled(true);

        setStatus(
            "Ride canceled",
            "This ride is no longer active.",
            0
        );
    }

    if (
        eta !== null &&
        eta !== undefined &&
        live.status !== "DRIVER_ARRIVED"
    ) {
        etaEl.textContent =
            eta <= 0
                ? "Arrived"
                : `${Math.max(1, Math.ceil(eta / 60))} min`;
    }
}

socket.on("connect", () => {
    setPassengerStreamState(
        "Socket connected"
    );

    wsLog(
        "CONNECTED",
        {
            socket_id: socket.id,
                engine_transport: socket.io.engine.transport.name,
            transport:
                socket.io.engine.transport.name,
        }
    );

    if (window.PASSENGER_USER_ID) {
        wsLog("REGISTER PASSENGER");

        socket.emit(
            "register_passenger",
            {
                passenger_id:
                    window.PASSENGER_USER_ID,
            }
        );
    }

    if (currentTripId) {
        joinTripStream(
            currentTripId,
            "SOCKET_RECONNECT"
        );
    }
});

socket.on("connect_error", (error) => {
    setPassengerStreamState(
        "Socket error"
    );

    wsLog(
        "CONNECT ERROR",
        {
            message: error.message,
        }
    );
});

socket.on("disconnect", (reason) => {
    setPassengerStreamState(
        "Socket disconnected"
    );

    wsLog(
        "DISCONNECTED",
        {
            reason,
        }
    );
});

socket.io.on("reconnect_attempt", (attempt) => {
    setPassengerStreamState(
        `Reconnecting #${attempt}`
    );

    wsLog(
        "RECONNECT ATTEMPT",
        {
            attempt,
        }
    );
});

socket.on(
    "connection_lifecycle",
    (data) => {
        wsLog(
            "CONNECTION LIFECYCLE",
            data
        );

        if (
            data.active_trip_id &&
            !currentTripId
        ) {
            currentTripId =
                Number(data.active_trip_id);

            setRequestCreationEnabled(false);

            if (cancelRideButton) {
                cancelRideButton.disabled = false;
            }

            wsLog(
                "ACTIVE TRIP RECOVERED",
                {
                    trip_id: currentTripId,
                }
            );
        }
    }
);

socket.on(
    "trip_lifecycle",
    (data) => {
        wsLog(
            "TRIP LIFECYCLE",
            data
        );

        if (data.phase === "JOINED") {
            setPassengerStreamState(
                `Trip #${data.trip_id} joined`
            );
        }

        if (data.phase === "STATE_UPDATE") {
            setPassengerStreamState(
                `${data.status} • streaming`
            );
        }

        if (data.phase === "TERMINAL") {
            setPassengerStreamState(
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
                    trip_id: currentTripId,
                    reason:
                        `TERMINAL_${data.status}`,
                }
            );
        }
    }
);

socket.on(
    "passenger_step",
    (notice) => {
        appendPassengerStepNotice(
            notice,
            true
        );
    }
);

socket.on(
    "trip_snapshot",
    applyPassengerTripSnapshot
);


function renderReviewingDrivers(live) {
    const card =
        document.querySelector(
            "#reviewing-drivers-card"
        );

    const title =
        document.querySelector(
            "#reviewing-drivers-title"
        );

    const detail =
        document.querySelector(
            "#reviewing-drivers-detail"
        );

    const list =
        document.querySelector(
            "#reviewing-drivers-list"
        );

    if (
        !card ||
        !title ||
        !detail ||
        !list
    ) {
        return;
    }

    const dispatch =
        live?.dispatch || {};

    const drivers =
        Array.isArray(
            dispatch.reviewing_drivers
        )
            ? dispatch.reviewing_drivers
            : [];

    if (!drivers.length) {
        card.classList.add("hidden");
        list.replaceChildren();
        return;
    }

    card.classList.remove("hidden");

    title.textContent =
        `${drivers.length} driver${drivers.length === 1 ? "" : "s"} reviewing $${Number(live.estimated_fare || 0).toFixed(2)}`;

    detail.textContent =
        "These drivers are currently inside your search radius and can accept this same fare.";

    list.replaceChildren();

    drivers.forEach((driver) => {
        const row =
            document.createElement("div");

        row.className =
            "request-item";

        row.innerHTML = `
            <div>
                <strong>${driver.name || `Driver #${driver.driver_id}`}</strong>
                <div class="muted">Reviewing your fare</div>
            </div>
            <div class="request-meta">
                <span>${Number(driver.distance_miles || 0).toFixed(2)} mi from pickup</span>
                <span>${driver.pickup_eta_seconds !== null && driver.pickup_eta_seconds !== undefined ? `ETA ${Math.max(1, Math.ceil(Number(driver.pickup_eta_seconds) / 60))} min` : "ETA —"}</span>
                <span>$${Number(driver.fare || live.estimated_fare || 0).toFixed(2)}</span>
            </div>
        `;

        list.append(row);
    });
}


function refreshPassengerDispatchCountdown() {
    const live = streamedTripSnapshot;

    if (
        !live ||
        !["REQUESTED", "OFFERED"].includes(live.status)
    ) {
        return;
    }

    const dispatch = live.dispatch || {};

    const radius = Number(
        dispatch.search_radius_miles
        || 0
    );

    const step = Number(
        dispatch.radius_step_miles
        || 0
    );

    const offered = Number(
        dispatch.open_offer_count
        || 0
    );

    const reviewingDrivers =
        Array.isArray(
            dispatch.reviewing_drivers
        )
            ? dispatch.reviewing_drivers
            : [];

    const waiting = Number(
        dispatch.waiting_offer_count
        || 0
    );

    let detail =
        `Searching ${radius.toFixed(2)} miles from your pickup • starts at ${Number(dispatch.initial_radius_miles || 0).toFixed(2)} miles and increases by ${step.toFixed(2)} miles each timer • ` +
        `${offered} driver${offered === 1 ? "" : "s"} currently have your $${Number(live.estimated_fare || 0).toFixed(2)} offer.` +
        (
            reviewingDrivers.length
                ? ` ${reviewingDrivers.length} driver${reviewingDrivers.length === 1 ? " is" : "s are"} reviewing it now.`
                : ""
        );

    if (
        dispatch.radius_paused &&
        live.fare_wait_until &&
        !live.fare_review_pending
    ) {
        const target =
            new Date(
                live.fare_wait_until
            ).getTime();

        const seconds =
            Math.max(
                0,
                Math.ceil(
                    (target - Date.now())
                    / 1000
                )
            );

        detail =
            `Maximum search radius reached at ${radius.toFixed(2)} miles • ` +
            `${offered} driver${offered === 1 ? "" : "s"} still have the same $${Number(live.estimated_fare || 0).toFixed(2)} offer • ` +
            `${seconds}s remaining before the next decision.`;
    } else if (
        dispatch.radius_paused
    ) {
        detail =
            `Maximum search radius reached at ${radius.toFixed(2)} miles • ` +
            `${offered} driver${offered === 1 ? "" : "s"} still have the same $${Number(live.estimated_fare || 0).toFixed(2)} offer.`;
    } else if (waiting > 0) {
        detail +=
            ` ${waiting} farther driver${waiting === 1 ? "" : "s"} can become eligible as the radius expands.`;
    }

    setStatus(
        "Expanding driver search",
        detail,
        28
    );
}


setInterval(
    refreshPassengerDispatchCountdown,
    1000
);




[pickupLat, pickupLng].forEach((input) => {
    input.addEventListener("change", updateMarkers);
});

[destLat, destLng].forEach((input) => {
    input.addEventListener("change", updateMarkers);
});

estimateRide().catch(() => {});



document.querySelector("#center-driver")?.addEventListener(
    "click",
    () => {
        const button =
            document.querySelector("#center-driver");

        const lat =
            Number(button?.dataset.lat);

        const lng =
            Number(button?.dataset.lng);

        if (
            Number.isFinite(lat) &&
            Number.isFinite(lng)
        ) {
            map.setView(
                [lat, lng],
                16
            );

            driverMarker.openPopup?.();
        }
    }
);

function renderPickupConfirmation(live) {
    const card =
        document.querySelector("#pickup-passenger-confirm-card");

    const button =
        document.querySelector("#confirm-passenger-pickup");

    const helpButton =
        document.querySelector("#pickup-help");

    const status =
        document.querySelector("#pickup-confirm-status");

    if (
        !card ||
        !button ||
        !helpButton ||
        !status
    ) {
        return;
    }

    const helpRequested =
        Boolean(
            live.pickup_help_requested_at
        );

    if (live.status === "PICKUP_PENDING") {
        // The passenger is now in the confirmation gate. Ride-request
        // controls stay disabled until this trip leaves the active lifecycle.
        setRequestCreationEnabled(false);

        card.classList.remove("hidden");

        button.disabled = false;
        helpButton.disabled =
            helpRequested;

        if (helpRequested) {
            helpButton.textContent =
                "Help Requested";

            status.textContent =
                "Help was requested. Do not confirm pickup unless you are inside the assigned vehicle and want the trip to begin.";
        } else {
            helpButton.textContent =
                "I Need Help";

            status.textContent =
                "Your driver marked you as picked up. Confirm that you are inside the assigned vehicle, or request help.";
        }

        // Scroll exactly once when PICKUP_PENDING first appears. Repeated
        // socket snapshots must not keep stealing the passenger's scroll.
        if (
            card.dataset.autoScrolled
            !== String(live.trip_id)
        ) {
            card.dataset.autoScrolled =
                String(live.trip_id);

            scrollToPickupConfirmation();
        }

        return;
    }

    if (
        ["IN_PROGRESS", "COMPLETED"]
        .includes(live.status)
    ) {
        card.classList.remove("hidden");
        button.disabled = true;
        helpButton.disabled = true;

        status.textContent =
            "Pickup confirmed. This ride can no longer be canceled.";

        return;
    }

    card.classList.add("hidden");
    button.disabled = true;
    helpButton.disabled = true;

    // Let a future trip auto-scroll again.
    if (
        live.status === "CANCELED" ||
        live.status === "COMPLETED"
    ) {
        delete card.dataset.autoScrolled;
    }
}

async function requestPickupHelp() {
    if (!currentTripId) {
        return;
    }

    const helpButton =
        document.querySelector("#pickup-help");

    const status =
        document.querySelector("#pickup-confirm-status");

    if (helpButton) {
        helpButton.disabled = true;
    }

    if (status) {
        status.textContent =
            "Requesting help…";
    }

    const response = await fetch(
        `/trips/${currentTripId}/pickup-help`,
        {
            method: "POST",
            headers: {
                "Content-Type":
                    "application/json",
            },
            body: JSON.stringify({
                passenger_id:
                    window.PASSENGER_USER_ID,
            }),
        }
    );

    const data =
        await response.json();

    if (!response.ok) {
        if (helpButton) {
            helpButton.disabled = false;
        }

        if (status) {
            status.textContent =
                data.error ||
                "Could not request help.";
        }

        wsLog(
            "PICKUP HELP FAILED",
            data
        );

        return;
    }

    if (helpButton) {
        helpButton.textContent =
            "Help Requested";

        helpButton.disabled = true;
    }

    if (status) {
        status.textContent =
            "Help requested. Do not confirm pickup unless you are inside the assigned vehicle and want the trip to begin.";
    }

    wsLog(
        "PICKUP HELP REQUESTED",
        data
    );
}


async function confirmPassengerPickup() {
    if (!currentTripId) {
        return;
    }

    wsLog(
        "PICKUP CONFIRM REQUEST",
        {
            trip_id: currentTripId,
        }
    );

    const response = await fetch(
        `/trips/${currentTripId}/pickup-confirm`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                passenger_id:
                    window.PASSENGER_USER_ID,
            }),
        }
    );

    const data =
        await response.json();

    if (!response.ok) {
        wsLog(
            "PICKUP CONFIRM FAILED",
            data
        );

        const status =
            document.querySelector("#pickup-confirm-status");

        if (status) {
            status.textContent =
                data.error ||
                "Pickup confirmation failed.";
        }

        return;
    }

    wsLog(
        "PICKUP CONFIRMED",
        data
    );
}

document
    .querySelector("#pickup-help")
    ?.addEventListener(
        "click",
        requestPickupHelp
    );

document
    .querySelector("#confirm-passenger-pickup")
    ?.addEventListener(
        "click",
        confirmPassengerPickup
    );


function renderPassengerSurvey(live) {
    const card =
        document.querySelector(
            "#passenger-survey-card"
        );

    const submit =
        document.querySelector(
            "#passenger-survey-submit"
        );

    const status =
        document.querySelector(
            "#passenger-survey-status"
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
            live.surveys?.passenger_submitted
        );

    submit.disabled =
        submitted;

    status.textContent =
        submitted
            ? "Survey submitted. Thank you."
            : "Please rate your completed ride.";

    if (
        card.dataset.autoScrolled
        !== String(live.trip_id)
    ) {
        card.dataset.autoScrolled =
            String(live.trip_id);

        window.setTimeout(
            () => {
                card.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                });
            },
            180
        );
    }
}


async function submitPassengerSurvey() {
    if (!currentTripId) {
        return;
    }

    const rating =
        document.querySelector(
            "#passenger-survey-rating"
        );

    const comments =
        document.querySelector(
            "#passenger-survey-comments"
        );

    const status =
        document.querySelector(
            "#passenger-survey-status"
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
                role: "PASSENGER",
                actor_id:
                    window.PASSENGER_USER_ID,
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
                "#passenger-survey-submit"
            );

        if (button) {
            button.disabled = true;
        }
    }
}


document
    .querySelector(
        "#passenger-survey-submit"
    )
    ?.addEventListener(
        "click",
        submitPassengerSurvey
    );


const chatLog = document.querySelector("#chat-log");
const chatInput = document.querySelector("#chat-input");
const chatSend = document.querySelector("#chat-send");

function appendChat(message) {
    if (!chatLog) return;
    const row = document.createElement("div");
    row.className = `chat-message ${message.sender_role.toLowerCase()}`;
    row.innerHTML = `
        <strong>${message.sender_name}</strong>
        <span>${message.body}</span>
        <small>${new Date(message.created_at).toLocaleTimeString()}</small>
    `;
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
}

async function loadChat() {
    const url = currentTripId ? `/messages/?trip_id=${currentTripId}` : "/messages/";
    const response = await fetch(url);
    const messages = await response.json();
    chatLog.innerHTML = "";
    messages.forEach(appendChat);
}

async function sendChat() {
    const body = chatInput.value.trim();
    if (!body) return;

    await fetch("/messages/", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            trip_id: currentTripId,
            sender_role: "PASSENGER",
            sender_name: window.PASSENGER_NAME,
            recipient_role: "DRIVER",
            body,
        }),
    });

    chatInput.value = "";
}

chatSend?.addEventListener("click", sendChat);
chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") sendChat();
});

socket.on("chat_message", (message) => {
    if (!currentTripId || !message.trip_id || message.trip_id === currentTripId) {
        appendChat(message);
    }
});

loadChat().catch(() => {});


socket.on("drivers_reviewing_offer", (data) => {
    if (
        !currentTripId ||
        Number(data.trip_id) !==
            Number(currentTripId)
    ) {
        return;
    }

    const drivers =
        Array.isArray(data.drivers)
            ? data.drivers
            : [];

    if (!drivers.length) {
        return;
    }

    const names =
        drivers
            .map(
                (driver) =>
                    driver.name ||
                    `Driver #${driver.driver_id}`
            )
            .join(", ");

    showPassengerAlert(
        `${names} ${drivers.length === 1 ? "is" : "are"} reviewing your $${Number(data.fare || 0).toFixed(2)} offer.`
    );

    wsLog(
        "DRIVERS REVIEWING OFFER",
        data
    );
});


socket.on("ride_accepted", (data) => {
    if (!currentTripId || data.trip_id !== currentTripId) return;

    // Acceptance ends fare review immediately, even before the next snapshot.
    const fareEscalationCard =
        document.querySelector("#fare-escalation-card");
    if (fareEscalationCard) {
        fareEscalationCard.classList.add("hidden");
    }

    setPipelineStage("DRIVER_ASSIGNED");

    setStatus(
        "Driver assigned",
        `${data.driver_name} accepted your ride request.`,
        38
    );

    showPassengerAlert(
        `${data.driver_name} accepted your ride and is your assigned driver.`
    );

});


async function cancelRide() {
    if (!currentTripId) return;

    const response = await fetch(`/trips/${currentTripId}/cancel`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            passenger_id: window.PASSENGER_USER_ID,
            passenger_name: window.PASSENGER_NAME,
        }),
    });

    const data = await response.json();

    if (!response.ok) {
        setStatus(
            "Cancel failed",
            data.error || "The ride could not be canceled.",
            0
        );
        return;
    }

    if (cancelRideButton) cancelRideButton.disabled = true;

    setStatus(
        "Ride canceled",
        "Your ride request has been canceled.",
        0
    );
}

cancelRideButton?.addEventListener("click", cancelRide);

socket.on("ride_canceled", (data) => {
    if (!currentTripId || data.trip_id !== currentTripId) return;

    if (cancelRideButton) cancelRideButton.disabled = true;

    setStatus(
        "Ride canceled",
        "This ride is no longer active.",
        0
    );
});





window.TripTiming.attach(socket);
