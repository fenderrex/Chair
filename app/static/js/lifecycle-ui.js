(function () {
    'use strict';

    const TERMINAL = new Set(['COMPLETED', 'CANCELED']);

    const PASSENGER_PHASES = Object.freeze({
        SET_LOCATION: 'SET_LOCATION',
        LOOKING_FOR_DRIVER: 'LOOKING_FOR_DRIVER',
        FOUND_DRIVER: 'FOUND_DRIVER',
        ENROUTE_TO_PICKUP: 'ENROUTE_TO_PICKUP',
        DRIVER_ARRIVED: 'DRIVER_ARRIVED',
        ENROUTE_TO_DROPOFF: 'ENROUTE_TO_DROPOFF',
        DROPOFF: 'DROPOFF',
    });

    const PASSENGER_UI_MATRIX = Object.freeze({
        SET_LOCATION: new Set([
            'ride-pipeline',
            'trip-status',
            'trip',
            'estimate',
        ]),
        LOOKING_FOR_DRIVER: new Set([
            'ride-pipeline',
            'trip-status',
            'estimate',
            'drivers-reviewing',
            'assigned-driver',
            'ride-updates',
            'keep-searching',
        ]),
        FOUND_DRIVER: new Set([
            'ride-pipeline',
            'trip-status',
            'assigned-driver',
            'ride-updates',
            'message-driver',
        ]),
        ENROUTE_TO_PICKUP: new Set([
            'ride-pipeline',
            'trip-status',
            'assigned-driver',
            'ride-updates',
            'message-driver',
        ]),
        DRIVER_ARRIVED: new Set([
            
            'trip-status',
            'ride-updates',
            'driver-at-pickup',
            'assigned-driver',
            'confirm-pickup',
            'message-driver',
        ]),
        ENROUTE_TO_DROPOFF: new Set([
            
            'trip-status',
             'assigned-driver',
            'ride-updates',
            'message-driver',
        ]),
        DROPOFF: new Set([
            
            'trip-status',
            'assigned-driver',
            'ride-updates',
            'message-driver',
            'after-ride-survey',
        ]),
    });


    const DRIVER_PHASES = Object.freeze({
        AVAILABLE: 'AVAILABLE',
        REVIEW_RIDE: 'REVIEW_RIDE',
        RIDE_ACCEPTED: 'RIDE_ACCEPTED',
        ENROUTE_TO_PICKUP: 'ENROUTE_TO_PICKUP',
        DRIVER_ARRIVED: 'DRIVER_ARRIVED',
        WAITING_PASSENGER_CONFIRM: 'WAITING_PASSENGER_CONFIRM',
        ENROUTE_TO_DROPOFF: 'ENROUTE_TO_DROPOFF',
        DROPOFF: 'DROPOFF',
    });

    const DRIVER_UI_MATRIX = Object.freeze({
        AVAILABLE: new Set([
            'driver-status',
            'ride-requests',
        ]),
        REVIEW_RIDE: new Set([
            'driver-status',
            'ride-requests',
            'ride-offer',
        ]),
        RIDE_ACCEPTED: new Set([
            'driver-status',
            'active-ride',
            'route-controls',
            'message-passenger',
        ]),
        ENROUTE_TO_PICKUP: new Set([
            'driver-status',
            'active-ride',
            'route-controls',
            'message-passenger',
        ]),
        DRIVER_ARRIVED: new Set([
            'driver-status',
            'active-ride',
            'passenger-pickup',
            'message-passenger',
        ]),
        WAITING_PASSENGER_CONFIRM: new Set([
            'driver-status',
            'active-ride',
            'route-controls',
            'passenger-pickup',
            'message-passenger',
        ]),
        ENROUTE_TO_DROPOFF: new Set([
            'driver-status',
            'active-ride',
            'route-controls',
            'message-passenger',
        ]),
        DROPOFF: new Set([
            'driver-status',
            'active-ride',
            'message-passenger',
            'after-ride-survey',
        ]),
    });

    function resolveDriverUiPhase(snapshot) {
        if (!snapshot?.trip_id) return DRIVER_PHASES.AVAILABLE;

        switch (String(snapshot.status || '')) {
            case 'REQUESTED':
            case 'OFFERED':
                return DRIVER_PHASES.REVIEW_RIDE;
            case 'DRIVER_ASSIGNED':
                return DRIVER_PHASES.RIDE_ACCEPTED;
            case 'DRIVER_EN_ROUTE':
                return DRIVER_PHASES.ENROUTE_TO_PICKUP;
            case 'DRIVER_ARRIVED':
                return DRIVER_PHASES.DRIVER_ARRIVED;
            case 'PICKUP_PENDING':
                return DRIVER_PHASES.WAITING_PASSENGER_CONFIRM;
            case 'IN_PROGRESS':
                return DRIVER_PHASES.ENROUTE_TO_DROPOFF;
            case 'COMPLETED':
                return DRIVER_PHASES.DROPOFF;
            case 'CANCELED':
            default:
                return DRIVER_PHASES.AVAILABLE;
        }
    }

    function resolvePassengerUiPhase(snapshot) {
        if (!snapshot?.trip_id) return PASSENGER_PHASES.SET_LOCATION;

        switch (String(snapshot.status || '')) {
            case 'REQUESTED':
            case 'OFFERED':
                return PASSENGER_PHASES.LOOKING_FOR_DRIVER;
            case 'DRIVER_ASSIGNED':
                return PASSENGER_PHASES.FOUND_DRIVER;
            case 'DRIVER_EN_ROUTE':
                return PASSENGER_PHASES.ENROUTE_TO_PICKUP;
            case 'DRIVER_ARRIVED':
            case 'PICKUP_PENDING':
                return PASSENGER_PHASES.DRIVER_ARRIVED;
            case 'IN_PROGRESS':
                return PASSENGER_PHASES.ENROUTE_TO_DROPOFF;
            case 'COMPLETED':
                return PASSENGER_PHASES.DROPOFF;
            case 'CANCELED':
            default:
                return PASSENGER_PHASES.SET_LOCATION;
        }
    }

    class RideLifecycleManager {
        constructor(options) {
            this.role = options.role;
            this.cards = Array.from(document.querySelectorAll('[data-lifecycle-card]'));
            this.passengerUi = Array.from(document.querySelectorAll('[data-passenger-ui]'));
            this.driverUi = Array.from(document.querySelectorAll('[data-driver-ui]'));
            this.currentPassengerPhase = null;
            this.currentDriverPhase = null;
            this.modeKey = `rideshare:${this.role}:lifecycle-mode`;
            this.demoMode = this.readMode(options.defaultDemoMode);
            this.lastActiveKey = null;
            this.lastSnapshot = null;
            this.toggle = document.querySelector(options.toggleSelector || '[data-lifecycle-toggle]');
            this.bindToggle();
            this.applyModeClasses();
        }

        readMode(defaultDemoMode) {
            const saved = window.localStorage.getItem(this.modeKey);
            if (saved === 'demo') return true;
            if (saved === 'normal') return false;
            return Boolean(defaultDemoMode);
        }

        bindToggle() {
            if (!this.toggle) return;
            this.toggle.checked = this.demoMode;
            this.toggle.addEventListener('change', () => {
                this.setDemoMode(this.toggle.checked);
            });
        }

        setDemoMode(enabled) {
            this.demoMode = Boolean(enabled);
            window.localStorage.setItem(this.modeKey, this.demoMode ? 'demo' : 'normal');
            this.applyModeClasses();
            if (this.lastSnapshot) this.update(this.lastSnapshot, { scroll: false });
        }

        applyModeClasses() {
            document.body.classList.toggle('lifecycle-demo-mode', this.demoMode);
            document.body.classList.toggle('lifecycle-normal-mode', !this.demoMode);
            if (this.toggle) this.toggle.checked = this.demoMode;
        }

        statusesFor(card) {
            return String(card.dataset.lifecycleStatuses || '')
                .split(',')
                .map((value) => value.trim())
                .filter(Boolean);
        }

        isMatch(card, snapshot) {
            const status = String(snapshot?.status || 'IDLE');
            const statuses = this.statusesFor(card);
            if (statuses.includes(status)) return true;
            if (statuses.includes('TERMINAL') && TERMINAL.has(status)) return true;
            if (statuses.includes('IDLE') && !snapshot?.trip_id) return true;
            return false;
        }

        stageIndex(card) {
            const value = Number(card.dataset.lifecycleOrder || 0);
            return Number.isFinite(value) ? value : 0;
        }

        activeCard(snapshot) {
            return this.cards.find((card) => this.isMatch(card, snapshot)) || null;
        }

        freezeCard(card, snapshot) {
            if (!card || card.dataset.lifecycleFrozen === '1') return;
            card.dataset.lifecycleFrozen = '1';
            card.dataset.lifecycleFrozenStatus = String(snapshot?.status || '');
            card.dataset.lifecycleFrozenAt = new Date().toISOString();
            const stamp = card.querySelector('[data-lifecycle-stamp]');
            if (stamp) {
                stamp.textContent = `Completed ${new Date().toLocaleTimeString()}`;
            }
        }

        activateCard(card) {
            if (!card) return;
            card.dataset.lifecycleFrozen = '0';
            card.removeAttribute('data-lifecycle-frozen-status');
            card.removeAttribute('data-lifecycle-frozen-at');
        }

        updatePassengerUi(snapshot) {
            const phase = resolvePassengerUiPhase(snapshot);
            const enabled = PASSENGER_UI_MATRIX[phase] || new Set();

            this.passengerUi.forEach((element) => {
                const key = String(element.dataset.passengerUi || '');
                const visible = this.demoMode || enabled.has(key);
                element.classList.toggle('passenger-ui-hidden', !visible);
                element.dataset.passengerPhase = phase;
                element.dataset.passengerVisible = visible ? '1' : '0';
            });

            document.body.dataset.passengerUiPhase = phase;
            this.currentPassengerPhase = phase;
            return phase;
        }


        updateDriverUi(snapshot) {
            const phase = resolveDriverUiPhase(snapshot);
            const enabled = DRIVER_UI_MATRIX[phase] || new Set();

            this.driverUi.forEach((element) => {
                const key = String(element.dataset.driverUi || '');
                const visible = this.demoMode || enabled.has(key);
                element.classList.toggle('driver-ui-hidden', !visible);
                element.dataset.driverPhase = phase;
                element.dataset.driverVisible = visible ? '1' : '0';
            });

            document.body.dataset.driverUiPhase = phase;
            this.currentDriverPhase = phase;
            return phase;
        }

        update(snapshot, options = {}) {
            this.lastSnapshot = snapshot || {};

            if (this.role === 'passenger') {
                return this.updatePassengerUi(this.lastSnapshot);
            }

            if (this.role === 'driver') {
                return this.updateDriverUi(this.lastSnapshot);
            }

            const active = this.activeCard(this.lastSnapshot);
            const activeOrder = active ? this.stageIndex(active) : -1;
            const activeKey = active?.dataset.lifecycleKey || null;

            this.cards.forEach((card) => {
                const order = this.stageIndex(card);
                const isActive = card === active;
                const isPast = activeOrder >= 0 && order < activeOrder;
                const isTerminalHistory = TERMINAL.has(String(this.lastSnapshot?.status || '')) && order < activeOrder;

                card.classList.toggle('lifecycle-active', isActive);
                card.classList.toggle('lifecycle-complete', isPast || isTerminalHistory);
                card.classList.toggle('lifecycle-future', !isActive && !isPast && !isTerminalHistory);
                card.setAttribute('aria-current', isActive ? 'step' : 'false');
                card.dataset.lifecycleState = isActive ? 'ACTIVE' : (isPast || isTerminalHistory ? 'FROZEN' : 'NOT_STARTED');

                if (isActive) {
                    this.activateCard(card);
                } else if (isPast || isTerminalHistory) {
                    this.freezeCard(card, this.lastSnapshot);
                }

                if (this.demoMode) {
                    card.classList.remove('lifecycle-hidden');
                } else {
                    card.classList.toggle('lifecycle-hidden', !isActive);
                }
            });

            if (
                active &&
                activeKey !== this.lastActiveKey &&
                options.scroll !== false
            ) {
                window.setTimeout(() => {
                    active.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 80);
            }

            this.lastActiveKey = activeKey;
            return activeKey;
        }
    }

    window.DRIVER_PHASES = DRIVER_PHASES;
    window.DRIVER_UI_MATRIX = DRIVER_UI_MATRIX;
    window.resolveDriverUiPhase = resolveDriverUiPhase;
    window.PASSENGER_PHASES = PASSENGER_PHASES;
    window.PASSENGER_UI_MATRIX = PASSENGER_UI_MATRIX;
    window.resolvePassengerUiPhase = resolvePassengerUiPhase;
    window.RideLifecycleManager = RideLifecycleManager;
})();
