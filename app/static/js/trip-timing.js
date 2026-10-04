window.TripTiming = (() => {
    const labels = {REQUESTED: "Requested", OFFERED: "Drivers deciding", DRIVER_ASSIGNED: "Driver accepted",
        DRIVER_EN_ROUTE: "Approaching", DRIVER_ARRIVED: "Waiting at pickup", PICKUP_PENDING: "Confirming pickup",
        IN_PROGRESS: "Trip underway", COMPLETED: "Completed", CANCELED: "Canceled"};
    function clock(seconds) {
        const value = Math.max(0, Math.floor(seconds));
        return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
    }
    function elapsed(stage, next, now) {
        if (["COMPLETED", "CANCELED"].includes(stage.status)) return "";
        return clock(((next ? Date.parse(next.entered_at) : now) - Date.parse(stage.entered_at)) / 1000);
    }
    function render(container, trip, receivedAt) {
        const timing = trip.timing;
        if (!timing) { container.textContent = "No recorded timing yet"; return; }
        const now = Date.parse(timing.server_time) + Date.now() - receivedAt;
        const stages = timing.stages || [];
        container.replaceChildren();
        stages.forEach((stage, i) => {
            const item = document.createElement("span");
            item.className = "pill";
            item.textContent = `${labels[stage.status] || stage.status}: ${elapsed(stage, stages[i + 1], now) || new Date(stage.entered_at).toLocaleTimeString()}`;
            item.title = `Entered ${stage.entered_at}`;
            container.append(item, document.createTextNode(" "));
        });
    }
    function attach(socket) {
        const container = document.createElement("div");
        container.className = "card";
        container.setAttribute("aria-label", "Trip stage durations");
        const anchor = document.querySelector("#passenger-pipeline-card") || document.querySelector("main");
        anchor.append(container);
        let current = null;
        socket.on("trip_snapshot", ({snapshot}) => {
            if (!snapshot) return;
            current = {trip: snapshot, receivedAt: Date.now()};
            render(container, current.trip, current.receivedAt);
        });
        setInterval(() => { if (current) render(container, current.trip, current.receivedAt); }, 1000);
    }
    return {clock, elapsed, render, attach};
})();
