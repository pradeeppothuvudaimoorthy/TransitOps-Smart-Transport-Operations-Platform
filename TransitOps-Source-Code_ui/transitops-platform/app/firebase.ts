import { initializeApp, getApps, getApp } from "firebase/app";
import { getAnalytics, isSupported } from "firebase/analytics";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyAGo2e0znCT1QBJH17xpPB5HYzzHcsTdlY",
  authDomain: "transitops-365ed.firebaseapp.com",
  projectId: "transitops-365ed",
  storageBucket: "transitops-365ed.firebasestorage.app",
  messagingSenderId: "144467868065",
  appId: "1:144467868065:web:5b5dac0799dff69de6f3e0",
  measurementId: "G-3DFMYYP45W"
};

// Initialize Firebase
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();
const db = getFirestore(app);

// Initialize Analytics conditionally (only in client browser environment)
let analytics = null;
if (typeof window !== "undefined") {
  isSupported().then((supported) => {
    if (supported) {
      analytics = getAnalytics(app);
    }
  });
}

export { app, db, analytics };
