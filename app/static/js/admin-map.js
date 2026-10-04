(() => {
    const map = L.map('admin-platform-map').setView([33.7202, -116.217], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    const markers = new Map();
    const searchCircles = new Map();
    let centered = false;
    let randomCenter = map.getCenter();
    const centerMarker = L.circleMarker(randomCenter, {radius: 10, color: '#059669', fillOpacity: 0.1, dashArray: '4 4'})
        .addTo(map).bindTooltip('Randomization center');
    const message = document.querySelector('#admin-map-message');
    function fitEveryone() {
        const bounds = L.latLngBounds(
            [...markers.values()].map(marker => marker.getLatLng())
        );
        for (const circle of searchCircles.values()) {
            bounds.extend(circle.getBounds());
        }
        if (bounds.isValid()) {
            map.fitBounds(bounds, {padding: [35, 35], maxZoom: 14});
        }
    }
    function popup(person) {
        const element = document.createElement('div');
        for (const text of [person.name, `${person.role} • ${person.status}`, person.location_kind,
            person.trip_id ? `Trip #${person.trip_id}` : '',
            person.search_active ? `Search radius: ${Number(person.search_radius_miles || 0).toFixed(1)} mi / ${Number(person.max_search_radius_miles || 0).toFixed(1)} mi max` : '',
            person.recorded_at ? `Recorded: ${new Date(person.recorded_at).toLocaleString()}` : 'Timestamp unavailable']) {
            if (!text) continue;
            const line = document.createElement('div'); line.textContent = text; element.append(line);
        }
        return element;
    }
    adminSocket.on('admin_platform_map', ({people}) => {
        const present = new Set();
        const unlocated = document.querySelector('#admin-map-unlocated');
        unlocated.replaceChildren();
        let missing = 0;
        for (const person of people) {
            const lat = person.latitude, lng = person.longitude;
            if (typeof lat !== 'number' || typeof lng !== 'number' || !Number.isFinite(lat) || !Number.isFinite(lng)
                || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
                missing++;
                const row = document.createElement('li');
                row.textContent = `${person.name} • ${person.role} • ${person.status} • no location recorded`;
                unlocated.append(row);
                continue;
            }
            present.add(person.key);
            const color = person.role === 'PASSENGER' ? '#9333ea' : person.status === 'Offline' ? '#64748b'
                : person.status === 'Busy' ? '#f97316' : '#2563eb';
            let marker = markers.get(person.key);
            if (!marker) {
                marker = L.circleMarker([lat, lng], {radius: 8, weight: 2, fillOpacity: .85}).addTo(map);
                markers.set(person.key, marker);
            }
            marker.setLatLng([lat, lng]).setStyle({color, fillColor: color});
            marker.bindPopup(popup(person));
            const label = document.createElement('span'); label.textContent = person.name;
            marker.bindTooltip(label);

            if (person.role === 'PASSENGER' && person.search_active) {
                const radiusMeters = Math.max(1, Number(person.search_radius_miles || 0) * 1609.344);
                let circle = searchCircles.get(person.key);
                if (!circle) {
                    circle = L.circle([lat, lng], {
                        radius: radiusMeters,
                        color: '#9333ea',
                        weight: 2,
                        dashArray: '6 6',
                        fillColor: '#9333ea',
                        fillOpacity: 0.06,
                    }).addTo(map);
                    searchCircles.set(person.key, circle);
                }
                circle.setLatLng([lat, lng]);
                circle.setRadius(radiusMeters);
                circle.bindTooltip(
                    `${person.name} search • ${Number(person.search_radius_miles || 0).toFixed(1)} mi / ${Number(person.max_search_radius_miles || 0).toFixed(1)} mi max`
                );
            } else {
                const circle = searchCircles.get(person.key);
                if (circle) {
                    map.removeLayer(circle);
                    searchCircles.delete(person.key);
                }
            }
        }
        for (const [key, marker] of markers) {
            if (!present.has(key)) { map.removeLayer(marker); markers.delete(key); }
        }
        for (const [key, circle] of searchCircles) {
            if (!present.has(key)) { map.removeLayer(circle); searchCircles.delete(key); }
        }
        document.querySelector('#admin-map-summary').textContent = `${people.length} people • ${markers.size} mapped • ${searchCircles.size} active search radius${searchCircles.size === 1 ? '' : 'es'} • ${missing} without a recorded location`;
        if (!missing) { const row = document.createElement('li'); row.textContent = 'Everyone has a recorded location.'; unlocated.append(row); }
        if (!centered && markers.size) { fitEveryone(); centered = true; randomCenter = map.getCenter(); centerMarker.setLatLng(randomCenter); }
    });
    map.on('click', ({latlng}) => {
        randomCenter = latlng; centerMarker.setLatLng(latlng);
        message.textContent = `Randomization center: ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}. Choose a radius and click Randomize driver locations.`;
    });
    document.querySelector('#admin-map-fit').addEventListener('click', fitEveryone);
    document.querySelector('#admin-randomize-drivers').addEventListener('click', async event => {
        const button = event.currentTarget;
        const radiusInput = document.querySelector('#admin-random-radius');
        if (!radiusInput.reportValidity()) return;
        button.disabled = true;
        try {
            const result = await requestJson('/admin/demo/randomize-drivers', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({latitude: randomCenter.lat, longitude: randomCenter.lng, radius_miles: Number(radiusInput.value)}),
            });
            message.textContent = `Moved ${result.updated_driver_ids.length} drivers; skipped ${result.skipped_driver_ids.length} busy drivers. Online/offline status preserved.`;
            fitEveryone();
        } catch (error) { message.textContent = error.message; }
        finally { button.disabled = false; }
    });
    // Recover even if the socket connected before this script loaded.
    if (adminSocket.connected) adminSocket.emit('register_admin');
})();
