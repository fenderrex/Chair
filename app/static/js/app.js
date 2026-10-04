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
const startDemoButton = document.querySelector("#start-demo");

let currentTripId = null;
let currentRoute = null;
let simulationTimer = null;

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

function setStatus(title, detail, progress = 0) {
    tripStatusEl.textContent = title;
    statusDetailEl.textContent = detail;
    progressBar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
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
            passenger_name: "Demo Passenger",
        }),
    });

    const data = await response.json();
    currentTripId = data.trip.id;

    drawRoute(data.route);
    fareEl.textContent = `$${data.fare.estimated_total.toFixed(2)}`;
    distanceEl.textContent = `${data.route.distance_miles.toFixed(1)} mi`;
    durationEl.textContent = `${data.route.duration_minutes.toFixed(0)} min`;
    providerEl.textContent = data.route.provider.toUpperCase();

    setStatus(
        "Driver assigned",
        "Alex Demo accepted the request. Start the live demo to simulate the trip.",
        30
    );

    startDemoButton.disabled = false;
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
    destLat.value = event.latlng.lat.toFixed(6);
    destLng.value = event.latlng.lng.toFixed(6);
    destinationMarker.setLatLng(event.latlng);

    try {
        await estimateRide();
    } catch (error) {
        setStatus("Route error", "Could not calculate a route.", 0);
    }
});

document.querySelector("#use-location").addEventListener("click", () => {
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

document.querySelector("#request").addEventListener("click", async () => {
    try {
        await requestRide();
    } catch (error) {
        setStatus("Request failed", "Could not create the demo trip.", 0);
    }
});

startDemoButton.addEventListener("click", startSimulation);

document.querySelector("#demo-id").addEventListener("click", async () => {
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

async function loadDriver() {
    const response = await fetch("/drivers/demo");
    const data = await response.json();

    document.querySelector("#driver-name").textContent = data.driver.name;
    document.querySelector("#vehicle").textContent =
        `${data.vehicle.year} ${data.vehicle.color} ` +
        `${data.vehicle.make} ${data.vehicle.model} • ` +
        `${data.vehicle.plate_state} ${data.vehicle.plate}`;
}

const socket = io({ transports: ["polling"], upgrade: false });

socket.on("location_update", (data) => {
    if (
        currentTripId &&
        data.trip_id === currentTripId &&
        data.actor_type === "driver"
    ) {
        driverMarker.setLatLng([data.latitude, data.longitude]);
    }
});

[pickupLat, pickupLng].forEach((input) => {
    input.addEventListener("change", updateMarkers);
});

[destLat, destLng].forEach((input) => {
    input.addEventListener("change", updateMarkers);
});

loadDriver();
estimateRide().catch(() => {});
