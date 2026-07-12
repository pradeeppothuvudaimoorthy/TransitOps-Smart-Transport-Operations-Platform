/** @odoo-module **/
/**
 * TransitOps Dashboard JS — v3.0 with Firebase Integration
 * =========================================================
 * - Fetches live KPIs from transit.dashboard via Odoo RPC
 * - Pushes KPI snapshots to Firebase Firestore in real-time
 * - Tracks user interactions via Firebase Analytics
 * - Animates KPI counters with ease-out cubic
 * - Auto-refreshes every 60 seconds
 */

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry }    from "@web/core/registry";
import { useService }  from "@web/core/utils/hooks";
import { transitFirebase } from "./firebase_service";

// ============================================================
// Counter Animation Utility
// ============================================================
/**
 * Smoothly animate a DOM element's text from 0 → target.
 * @param {HTMLElement} el
 * @param {number}      target
 * @param {number}      duration - ms
 * @param {boolean}     isCurrency
 */
function animateCounter(el, target, duration = 700, isCurrency = false) {
    if (!el || typeof target !== "number") return;
    const startTime = performance.now();

    function tick(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        // Ease-out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = target * eased;

        el.textContent = isCurrency
            ? formatCurrency(current)
            : Math.round(current).toLocaleString("en-IN");

        if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

/**
 * Format a number as Indian currency (₹ with commas).
 * @param {number} value
 * @returns {string}
 */
function formatCurrency(value) {
    return "₹ " + new Intl.NumberFormat("en-IN", {
        maximumFractionDigits: 0,
    }).format(Math.round(value));
}

// ============================================================
// KPI → DOM mapping
// ============================================================
const KPI_MAPPINGS = [
    { id: "kpi-active-vehicles",   key: "active_vehicles" },
    { id: "kpi-available-vehicles",key: "available_vehicles" },
    { id: "kpi-in-maintenance",    key: "vehicles_in_maintenance" },
    { id: "kpi-available-drivers", key: "drivers_available" },
    { id: "kpi-trips-today",       key: "trips_today" },
    { id: "kpi-active-trips",      key: "active_trips" },
    { id: "kpi-pending-trips",     key: "pending_trips" },
    { id: "kpi-fuel-cost",         key: "total_fuel_cost",         currency: true },
    { id: "kpi-maintenance-cost",  key: "total_maintenance_cost",  currency: true },
    { id: "kpi-revenue",           key: "total_revenue",           currency: true },
    { id: "kpi-health-score",      key: "fleet_health_score" },
    { id: "kpi-utilization",       key: "fleet_utilization" },
];

// ============================================================
// TransitOps Dashboard Component
// ============================================================
export class TransitOpsDashboard extends Component {
    setup() {
        this.rpc            = useService("rpc");
        this.notification   = useService("notification");
        this.state          = useState({
            kpis:        {},
            loading:     true,
            lastUpdated: null,
            error:       null,
            firebaseSync: false,
        });
        this._refreshTimer  = null;
        this.root           = useRef("dashboard");

        onMounted(async () => {
            // Track dashboard view in Firebase Analytics
            transitFirebase.trackDashboardView();

            // Initial KPI load
            await this._loadKPIs();

            // Auto-refresh every 60 s
            this._refreshTimer = setInterval(() => this._loadKPIs(), 60_000);

            // Re-load when tab becomes visible again
            document.addEventListener("visibilitychange", this._onVisibilityChange.bind(this));
        });

        onWillUnmount(() => {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            document.removeEventListener("visibilitychange", this._onVisibilityChange.bind(this));
        });
    }

    // ----------------------------------------------------------
    // Visibility handler
    // ----------------------------------------------------------
    _onVisibilityChange() {
        if (!document.hidden) this._loadKPIs();
    }

    // ----------------------------------------------------------
    // KPI Fetch + Firebase Push
    // ----------------------------------------------------------
    async _loadKPIs() {
        try {
            this.state.loading = true;
            this.state.error   = null;

            // 1. Fetch from Odoo backend
            const kpis = await this.rpc("/web/dataset/call_kw", {
                model:  "transit.dashboard",
                method: "get_fleet_kpis",
                args:   [],
                kwargs: {},
            });

            this.state.kpis        = kpis;
            this.state.lastUpdated = new Date().toLocaleTimeString("en-IN");

            // 2. Push snapshot to Firebase Firestore (non-blocking)
            transitFirebase.pushKPIs(kpis).then(() => {
                this.state.firebaseSync = true;
            }).catch(() => {
                this.state.firebaseSync = false;
            });

            // 3. Animate counters
            setTimeout(() => this._animateCounters(kpis), 80);

        } catch (err) {
            this.state.error = "Failed to load KPI data. Please refresh the page.";
            console.error("[TransitOps] KPI fetch failed:", err);
        } finally {
            this.state.loading = false;
        }
    }

    // ----------------------------------------------------------
    // Counter Animations
    // ----------------------------------------------------------
    _animateCounters(kpis) {
        const container = this.root.el;
        if (!container) return;

        for (const { id, key, currency } of KPI_MAPPINGS) {
            const el    = container.querySelector(`#${id}`);
            const value = kpis[key];
            if (el && typeof value === "number") {
                animateCounter(el, value, 700, !!currency);
            }
        }
    }

    // ----------------------------------------------------------
    // Manual Refresh (bound to refresh button)
    // ----------------------------------------------------------
    onRefreshClick() {
        transitFirebase.trackEvent("transitops_manual_refresh");
        this._loadKPIs();
    }

    // ----------------------------------------------------------
    // KPI Card Click Tracking
    // ----------------------------------------------------------
    onKPICardClick(cardName) {
        transitFirebase.trackKPIClick(cardName);
    }

    // ----------------------------------------------------------
    // Quick Action Tracking
    // ----------------------------------------------------------
    onQuickAction(actionName) {
        transitFirebase.trackQuickAction(actionName);
    }
}

TransitOpsDashboard.template = "transitops.Dashboard";

// ============================================================
// Tab Visibility Global Listener
// ============================================================
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        document.dispatchEvent(new CustomEvent("transitops:tab-visible"));
    }
});
