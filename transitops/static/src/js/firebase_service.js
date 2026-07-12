/** @odoo-module **/
/**
 * TransitOps — Firebase Service Layer
 * =====================================
 * Initializes Firebase and exposes Firestore + Analytics
 * to all other TransitOps JS modules.
 *
 * Firebase Project : transitops-365ed
 * Services used   : Firebase Analytics, Cloud Firestore
 *
 * USAGE (in other modules):
 *   import { transitFirebase } from "./firebase_service";
 *   await transitFirebase.pushKPIs({ ... });
 */

// ============================================================
// Firebase SDK — loaded via CDN (ES module, no bundler needed)
// ============================================================
import { initializeApp }         from "https://www.gstatic.com/firebasejs/12.16.0/firebase-app.js";
import { getAnalytics, logEvent } from "https://www.gstatic.com/firebasejs/12.16.0/firebase-analytics.js";
import {
    getFirestore,
    doc,
    setDoc,
    collection,
    addDoc,
    serverTimestamp,
} from "https://www.gstatic.com/firebasejs/12.16.0/firebase-firestore.js";

// ============================================================
// Firebase Configuration
// ============================================================
const FIREBASE_CONFIG = {
    apiKey:            "AIzaSyAGo2e0znCT1QBJH17xpPB5HYzzHcsTdlY",
    authDomain:        "transitops-365ed.firebaseapp.com",
    projectId:         "transitops-365ed",
    storageBucket:     "transitops-365ed.firebasestorage.app",
    messagingSenderId: "144467868065",
    appId:             "1:144467868065:web:5b5dac0799dff69de6f3e0",
    measurementId:     "G-3DFMYYP45W",
};

// ============================================================
// Initialize Firebase App (singleton — safe to call multiple times)
// ============================================================
let _app       = null;
let _analytics = null;
let _db        = null;
let _ready     = false;

function _init() {
    if (_ready) return;
    try {
        _app       = initializeApp(FIREBASE_CONFIG);
        _analytics = getAnalytics(_app);
        _db        = getFirestore(_app);
        _ready     = true;
        console.info("[TransitOps Firebase] ✅ Initialized — project: transitops-365ed");
    } catch (err) {
        console.error("[TransitOps Firebase] ❌ Initialization failed:", err);
    }
}

// Initialize immediately on module load
_init();

// ============================================================
// Firestore Collection Paths
// ============================================================
const COLLECTIONS = {
    KPI_SNAPSHOTS:   "kpi_snapshots",      // Live dashboard snapshots
    FLEET_EVENTS:    "fleet_events",       // Dispatch / complete / cancel events
    AUDIT_LOG:       "audit_log",          // User action audit trail
};

// ============================================================
// Public Firebase Service API
// ============================================================
export const transitFirebase = {

    /**
     * True when Firebase is fully initialized.
     */
    get isReady() {
        return _ready;
    },

    // ----------------------------------------------------------
    // Firestore: Push KPI Snapshot
    // ----------------------------------------------------------
    /**
     * Write a full KPI snapshot to Firestore under
     * kpi_snapshots/latest (overwrite) for real-time dashboard sync.
     *
     * @param {Object} kpis — KPI object from transit.dashboard.get_fleet_kpis()
     * @returns {Promise<void>}
     */
    async pushKPIs(kpis) {
        if (!_ready || !_db) return;
        try {
            const ref = doc(_db, COLLECTIONS.KPI_SNAPSHOTS, "latest");
            await setDoc(ref, {
                ...kpis,
                synced_at: serverTimestamp(),
                source:    "odoo_backend",
            });

            // Also keep a historical time-series record
            const histRef = collection(_db, COLLECTIONS.KPI_SNAPSHOTS, "latest", "history");
            await addDoc(histRef, {
                ...kpis,
                recorded_at: serverTimestamp(),
            });

            console.debug("[TransitOps Firebase] KPI snapshot pushed:", kpis);
        } catch (err) {
            console.warn("[TransitOps Firebase] Failed to push KPI snapshot:", err);
        }
    },

    // ----------------------------------------------------------
    // Firestore: Log a Fleet Event
    // ----------------------------------------------------------
    /**
     * Log a business event (trip dispatched, vehicle in maintenance, etc.)
     * to the fleet_events collection for external consumers.
     *
     * @param {string} eventType — e.g. 'trip_dispatched', 'maintenance_opened'
     * @param {Object} payload   — event-specific data
     * @returns {Promise<string>} — Firestore document ID
     */
    async logFleetEvent(eventType, payload = {}) {
        if (!_ready || !_db) return null;
        try {
            const ref = collection(_db, COLLECTIONS.FLEET_EVENTS);
            const docRef = await addDoc(ref, {
                event_type:  eventType,
                occurred_at: serverTimestamp(),
                source:      "odoo_backend",
                ...payload,
            });
            console.debug(`[TransitOps Firebase] Fleet event logged: ${eventType}`, payload);
            return docRef.id;
        } catch (err) {
            console.warn("[TransitOps Firebase] Failed to log fleet event:", err);
            return null;
        }
    },

    // ----------------------------------------------------------
    // Analytics: Log UI Event
    // ----------------------------------------------------------
    /**
     * Log a user interaction event to Firebase Analytics.
     *
     * @param {string} eventName  — GA4 event name (snake_case)
     * @param {Object} params     — Event parameters
     */
    trackEvent(eventName, params = {}) {
        if (!_ready || !_analytics) return;
        try {
            logEvent(_analytics, eventName, {
                app_version: "18.0.1.0.0",
                module:      "transitops",
                ...params,
            });
            console.debug(`[TransitOps Firebase] Analytics event: ${eventName}`, params);
        } catch (err) {
            console.warn("[TransitOps Firebase] Analytics track failed:", err);
        }
    },

    // ----------------------------------------------------------
    // Analytics: Predefined Event Helpers
    // ----------------------------------------------------------
    /**
     * Track dashboard view (called on mount)
     */
    trackDashboardView() {
        this.trackEvent("transitops_dashboard_viewed", {
            timestamp: new Date().toISOString(),
        });
    },

    /**
     * Track KPI card click
     * @param {string} cardName
     */
    trackKPIClick(cardName) {
        this.trackEvent("transitops_kpi_clicked", { card_name: cardName });
    },

    /**
     * Track quick action button click
     * @param {string} action
     */
    trackQuickAction(action) {
        this.trackEvent("transitops_quick_action", { action_name: action });
    },

    /**
     * Track trip workflow event
     * @param {string} tripNumber
     * @param {string} action — 'dispatched' | 'completed' | 'cancelled'
     */
    trackTripEvent(tripNumber, action) {
        this.trackEvent(`transitops_trip_${action}`, {
            trip_number: tripNumber,
        });
        this.logFleetEvent(`trip_${action}`, { trip_number: tripNumber });
    },
};

// Make service available globally for debugging via browser console
if (typeof window !== "undefined") {
    window.__transitFirebase = transitFirebase;
}
