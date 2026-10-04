const output = document.querySelector("#admin-demo-output");
let simulationTimer = null;
let simulationStep = 0;

function showOutput(value) {
    if (!output) return;
    output.textContent = typeof value === "string"
        ? value
        : JSON.stringify(value, null, 2);
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
}

document.querySelector("#admin-open-driver")?.addEventListener("click", () => {
    const id = document.querySelector("#admin-driver-select")?.value;
    if (id) window.location.href = `/driver?driver_id=${encodeURIComponent(id)}`;
});

document.querySelector("#admin-open-passenger")?.addEventListener("click", () => {
    const id = document.querySelector("#admin-passenger-select")?.value;
    if (id) window.location.href = `/passenger?user_id=${encodeURIComponent(id)}`;
});

document.querySelectorAll(".admin-delete").forEach((button) => {
    button.addEventListener("click", async () => {
        const kind = button.dataset.kind;
        const id = button.dataset.id;
        const name = button.dataset.name || `${kind} ${id}`;

        if (!window.confirm(`Delete ${name}? This cannot be undone.`)) return;

        const path = kind === "trip"
            ? `/admin/trips/${id}`
            : kind === "driver"
                ? `/admin/drivers/${id}`
                : `/admin/passengers/${id}`;

        button.disabled = true;
        try {
            const data = await requestJson(path, { method: "DELETE" });
            showOutput(data);
            window.location.reload();
        } catch (error) {
            button.disabled = false;
            showOutput({ error: error.message });
        }
    });
});

document.querySelector("#admin-reset-drivers")?.addEventListener("click", async () => {
    try {
        const data = await requestJson("/admin/demo/reset-all-drivers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        showOutput(data);
        window.location.reload();
    } catch (error) {
        showOutput({ error: error.message });
    }
});

document.querySelector("#admin-sim-toggle")?.addEventListener("click", (event) => {
    const button = event.currentTarget;

    if (simulationTimer) {
        clearInterval(simulationTimer);
        simulationTimer = null;
        button.textContent = "Start Simulated GPS";
        showOutput("Admin test-driver position simulation stopped.");
        return;
    }

    button.textContent = "Stop Simulated GPS";
    simulationTimer = setInterval(async () => {
        try {
            const data = await requestJson("/admin/demo/simulate-step", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ step: simulationStep++ }),
            });
            showOutput(data);
        } catch (error) {
            showOutput({ error: error.message });
        }
    }, 1000);
});

document.querySelector("#admin-use-rex-gps")?.addEventListener("click", () => {
    if (!navigator.geolocation) {
        showOutput({ error: "Browser geolocation is unavailable." });
        return;
    }

    showOutput("Waiting for browser GPS permission…");

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            try {
                const data = await requestJson("/admin/demo/rex-location", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                    }),
                });
                showOutput(data);
            } catch (error) {
                showOutput({ error: error.message });
            }
        },
        (error) => showOutput({ error: error.message }),
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 2000 },
    );
});


const adminSocket = io({transports: ["websocket"], upgrade: false});
const liveTrips = new Map();
const liveState = document.querySelector("#admin-live-state");

function renderAdminDispatchAlerts() {
    const host =
        document.querySelector(
            "#admin-dispatch-alerts"
        );

    const count =
        document.querySelector(
            "#admin-dispatch-alert-count"
        );

    if (!host || !count) {
        return;
    }

    const alerts = [];

    for (const {trip} of liveTrips.values()) {
        if (trip.pickup_help_requested_at) {
            alerts.push({
                kind: "PICKUP_HELP",
                trip,
                createdAt:
                    trip.pickup_help_requested_at,
            });
        }

        if (trip.no_driver_admin_notified_at) {
            alerts.push({
                kind: "NO_DRIVER",
                trip,
                createdAt:
                    trip.no_driver_admin_notified_at,
            });
        }
    }

    alerts.sort(
        (a, b) =>
            Date.parse(b.createdAt)
            - Date.parse(a.createdAt)
    );

    count.textContent =
        String(alerts.length);

    host.replaceChildren();

    if (!alerts.length) {
        const empty =
            document.createElement("p");

        empty.className = "muted";
        empty.textContent =
            "No active dispatch or pickup alerts.";

        host.append(empty);
        return;
    }

    alerts.forEach(({kind, trip, createdAt}) => {
        const row =
            document.createElement("div");

        row.className =
            "request-item";

        const when =
            new Date(
                createdAt
            ).toLocaleString();

        if (kind === "PICKUP_HELP") {
            row.innerHTML = `
                <div>
                    <strong>Pickup help • Trip #${trip.trip_id}</strong>
                    <div class="muted">
                        Passenger requested help during pickup confirmation.
                    </div>
                </div>
                <div class="request-meta">
                    <span>${when}</span>
                    <span>${trip.status}</span>
                </div>
            `;
        } else {
            row.innerHTML = `
                <div>
                    <strong>Trip #${trip.trip_id}</strong>
                    <div class="muted">
                        No driver in the configured area accepted this ride.
                    </div>
                </div>
                <div class="request-meta">
                    <span>${when}</span>
                    <span>Fare $${Number(
                        trip.estimated_fare || 0
                    ).toFixed(2)}</span>
                    <span>Round ${Number(
                        trip.fare_round || 0
                    )}</span>
                </div>
            `;
        }

        host.append(row);
    });
}

function renderAdminTiming() {
    const host = document.querySelector("#admin-live-trips");
    host.replaceChildren();
    for (const {trip, receivedAt} of [...liveTrips.values()].sort((a, b) => b.trip.trip_id - a.trip.trip_id)) {
        const section = document.createElement("section");
        const title = document.createElement("h3");
        title.textContent = `Trip #${trip.trip_id} • ${trip.status}`;
        section.append(title);
        const timing = document.createElement("div");
        TripTiming.render(timing, trip, receivedAt); section.append(timing);

        const fare = document.createElement("p");
        fare.textContent =
            `Fare $${Number(trip.estimated_fare || 0).toFixed(2)} ` +
            `• original $${Number(trip.original_estimated_fare || trip.estimated_fare || 0).toFixed(2)} ` +
            `• escalation round ${trip.fare_round || 0}` +
            (trip.fare_review_pending ? " • waiting for passenger approval" : "");
        section.append(fare);

        const expansion = document.createElement("p");
        expansion.textContent =
            `Passenger search radius ${Number(trip.search_radius_miles || 0).toFixed(2)} mi ` +
            `of ${Number(trip.max_search_radius_miles || 0).toFixed(2)} mi max ` +
            `• increases by ${Number(trip.search_radius_step_miles || 0).toFixed(2)} mi per timer ` +
            `• ${trip.search_radius_capped ? "MAX RADIUS REACHED" : `next expansion in ${TripTiming.clock(trip.dispatch_remaining_seconds || 0)}`} ` +
            `• elapsed ${Number(trip.dispatch_elapsed_seconds || 0).toFixed(1)}s`;
        section.append(expansion);

        const queueState = document.createElement("p");
        const offeredCount = Number(trip.offered_driver_count || 0);
        const waitingCount = Number(trip.waiting_driver_count || 0);
        const declinedCount = Number(trip.declined_driver_count || 0);
        queueState.textContent =
            `Passenger is waiting on ${offeredCount} driver${offeredCount === 1 ? "" : "s"} ` +
            `• ${waitingCount} WAITING for radius ` +
            `• ${declinedCount} DECLINED ` +
            `• fare round ${Number(trip.fare_round || 0)}`;
        section.append(queueState);

        const now = Date.parse(trip.timing.server_time) + Date.now() - receivedAt;
        for (const offer of trip.offers) {
            const row = document.createElement("p");
            const wait = offer.status === "WAITING" && offer.eligible_at
                ? ` • eligible in ${TripTiming.clock((Date.parse(offer.eligible_at) - now) / 1000)}`
                : offer.status === "OFFERED"
                ? " • remains eligible" : "";
            row.textContent = `#${offer.driver_id} ${offer.name} • ${offer.distance_miles.toFixed(2)} mi • scale ${offer.distance_fraction == null ? "—" : offer.distance_fraction.toFixed(3)} • ${offer.status}${wait}`;
            section.append(row);
        }
        host.append(section);
    }
    if (!liveTrips.size) host.textContent = "No trips yet.";

    renderAdminDispatchAlerts();
}
adminSocket.on("connect", () => { liveState.textContent = "Live • timers synchronized"; adminSocket.emit("register_admin"); });
adminSocket.on("disconnect", () => { liveState.textContent = "Disconnected • waiting to synchronize"; });
adminSocket.on("admin_snapshot", ({trips}) => {
    liveTrips.clear();
    trips.forEach(trip => liveTrips.set(trip.trip_id, {trip, receivedAt: Date.now()}));
    renderAdminTiming();
});
adminSocket.on("admin_trip_update", trip => {
    if (trip.deleted) liveTrips.delete(trip.trip_id);
    else liveTrips.set(trip.trip_id, {trip, receivedAt: Date.now()});
    renderAdminTiming();
});

adminSocket.on("admin_pickup_help_alert", alert => {
    showOutput({
        alert: "Passenger requested help during pickup confirmation.",
        trip_id: alert.trip_id,
        passenger: alert.passenger_name,
        driver_id: alert.driver_id,
        created_at: alert.created_at,
    });

    const host =
        document.querySelector(
            "#admin-dispatch-alerts"
        );

    if (host) {
        const row =
            document.createElement("div");

        row.className =
            "request-item";

        row.innerHTML = `
            <div>
                <strong>Pickup help • Trip #${alert.trip_id}</strong>
                <div class="muted">
                    Passenger ${alert.passenger_name || ""} requested help during pickup confirmation.
                </div>
            </div>
            <div class="request-meta">
                <span>Driver #${alert.driver_id ?? "—"}</span>
                <span>${alert.created_at ? new Date(alert.created_at).toLocaleString() : "now"}</span>
            </div>
        `;

        host.prepend(row);
    }
});


adminSocket.on("admin_dispatch_alert", alert => {
    const message =
        alert.message ||
        "No driver in the configured area accepted this ride.";

    showOutput({
        alert: message,
        trip_id: alert.trip_id,
        passenger: alert.passenger_name,
        driver_count: alert.driver_count,
        radius_miles: alert.radius_miles,
        created_at: alert.created_at,
    });

    // The database-backed admin_trip_update carries the persistent alert.
    // Re-render from that source instead of creating a second temporary row.
    renderAdminDispatchAlerts();
});
setInterval(renderAdminTiming, 1000);


document.querySelector("#dispatch-settings").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const message = document.querySelector("#dispatch-settings-result");
    const button = form.querySelector("button");
    button.disabled = true;
    try {
        const values = Object.fromEntries(new FormData(form));
        const response = await fetch("/admin/dispatch-settings", {
            method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not save settings");
        message.textContent = `Saved. Search starts at ${Number(result.initial_radius_miles).toFixed(1)} mi, expands by ${Number(result.radius_miles).toFixed(1)} mi every ${Number(result.expansion_seconds).toFixed(1)} sec, and stops at the ${Number(result.max_radius_miles).toFixed(1)} mi maximum. Higher-fare rounds reset to the starting radius and restart the timer.`;
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
});
