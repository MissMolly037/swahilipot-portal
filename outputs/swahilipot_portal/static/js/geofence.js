/**
 * geofence.js — SAH-VisionDevs
 *
 * Polls the user's GPS position every 60 seconds while they are checked in.
 * If they leave the allowed site radius it:
 *   1. Shows a prominent on-screen warning banner
 *   2. POSTs to /attendance/geofence-ping/ which:
 *      - Records a GeofenceViolation in the database
 *      - Sends an in-app notification to the user (CRITICAL priority)
 *      - Sends in-app alerts to all admins / program managers (CRITICAL priority)
 *   3. Plays a CRITICAL-level notification sound
 *
 * Location on/off tracking:
 *   - Watches for geolocation permission changes via the Permissions API
 *   - If location permission is revoked, reports to /attendance/location-status/
 *     and notifies both the user and management (HIGH priority sound + notification)
 *   - When permission is restored, reports on again (MEDIUM priority)
 */

(function () {
  "use strict";

  const PING_INTERVAL_MS = 60_000; // 60 s
  const checkedIn  = window.portalCheckedIn === true;
  const pingUrl    = window.geofencePingUrl;
  const csrf       = window.csrfToken;
  const locationStatusUrl = window.locationStatusUrl || "";

  if (!pingUrl || !navigator.geolocation) return;

  const statusBox = document.getElementById("geofenceStatus");
  const gfText    = document.getElementById("gfText");
  const gfSpinner = document.getElementById("gfSpinner");

  // ── Status UI helpers ────────────────────────────────────────────────────

  function setStatus(inside, distance, radius) {
    if (!statusBox) return;
    if (inside) {
      statusBox.className = "alert alert-success py-2 px-3 mb-3 d-flex align-items-center gap-2";
      gfSpinner.className  = "bi bi-geo-alt-fill text-success fs-5";
      gfText.innerHTML     =
        `<strong>Inside site perimeter</strong> — You are ${distance} m from the site centre (radius: ${radius} m).`;
    } else {
      statusBox.className = "alert alert-danger py-2 px-3 mb-3 d-flex align-items-center gap-2 border border-danger border-2";
      gfSpinner.className  = "bi bi-exclamation-triangle-fill text-danger fs-5";
      gfText.innerHTML     =
        `<strong>⚠ Outside site perimeter!</strong> You are <strong>${distance} m</strong> away (allowed: ${radius} m). ` +
        `A violation has been recorded and management has been notified. Please return to the site or check out.`;
      showOutsideBanner(distance, radius);
      // Critical sound for geofence breach
      if (window.portalSound) window.portalSound.play("critical");
    }
  }

  function setWaiting() {
    if (!statusBox) return;
    statusBox.className = "alert alert-info py-2 px-3 mb-3 d-flex align-items-center gap-2";
    if (gfSpinner) gfSpinner.className = "spinner-grow spinner-grow-sm text-info";
    if (gfText)    gfText.innerHTML    = "<strong>Location monitoring active</strong> — acquiring GPS…";
  }

  function setError(msg) {
    if (!statusBox) return;
    statusBox.className = "alert alert-warning py-2 px-3 mb-3 d-flex align-items-center gap-2";
    if (gfSpinner) gfSpinner.className = "bi bi-wifi-off text-warning fs-5";
    if (gfText)    gfText.innerHTML    = `<strong>Location unavailable:</strong> ${msg}`;
  }

  function setLocationOff() {
    if (!statusBox) return;
    statusBox.className = "alert alert-danger py-2 px-3 mb-3 d-flex align-items-center gap-2";
    if (gfSpinner) gfSpinner.className = "bi bi-geo-alt-fill text-danger fs-5";
    if (gfText)    gfText.innerHTML    =
      "<strong>⚠ Location Turned Off</strong> — GPS monitoring is inactive. " +
      "Re-enable location permissions to resume attendance tracking.";
    // High-priority sound for location off
    if (window.portalSound) window.portalSound.play("high");
  }

  /** Show a full-screen dismissible warning banner when the user is outside */
  function showOutsideBanner(distance, radius) {
    if (document.getElementById("gfBanner")) return; // already visible
    const banner = document.createElement("div");
    banner.id = "gfBanner";
    banner.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:9999;background:#dc3545;color:#fff;" +
      "padding:14px 20px;display:flex;align-items:center;justify-content:space-between;" +
      "font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,.4);";
    banner.innerHTML =
      `<span>⚠ You have left the site perimeter (${distance} m away, allowed ${radius} m). ` +
      `Management has been alerted. Please return or check out.</span>` +
      `<button onclick="document.getElementById('gfBanner').remove()" ` +
      `style="background:transparent;border:2px solid #fff;color:#fff;border-radius:4px;padding:4px 12px;cursor:pointer;font-weight:700;">Dismiss</button>`;
    document.body.prepend(banner);
  }

  // ── Location on/off reporting ─────────────────────────────────────────────

  /**
   * Report location status change to the server.
   * @param {"on"|"off"} status
   */
  function reportLocationStatus(status) {
    if (!locationStatusUrl || !csrf) return;
    fetch(locationStatusUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
      body: JSON.stringify({ status: status }),
    }).catch(function (e) {
      console.warn("Location status report failed:", e);
    });
  }

  // Track previous permission state to avoid duplicate reports
  let _lastPermissionState = null;

  /**
   * Watch for permission changes using the Permissions API.
   * This fires when the user explicitly revokes or grants location permission.
   */
  if (navigator.permissions && navigator.permissions.query) {
    navigator.permissions.query({ name: "geolocation" }).then(function (permStatus) {
      _lastPermissionState = permStatus.state;

      permStatus.onchange = function () {
        const newState = permStatus.state;
        if (newState === _lastPermissionState) return;
        _lastPermissionState = newState;

        if (newState === "denied" || newState === "prompt") {
          // Location turned off or permission revoked
          setLocationOff();
          reportLocationStatus("off");
        } else if (newState === "granted") {
          // Location turned back on
          if (window.portalSound) window.portalSound.play("medium");
          reportLocationStatus("on");
          // Resume pinging
          doGPSPing();
        }
      };
    }).catch(function () {
      // Permissions API not supported fully — silent fail
    });
  }

  // ── Geofence ping ────────────────────────────────────────────────────────

  async function ping(lat, lng) {
    try {
      const resp = await fetch(pingUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ latitude: lat, longitude: lng }),
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.checked_in) return; // session ended server-side
      setStatus(data.inside, data.distance, data.radius || (window.portalSite && window.portalSite.radius));
    } catch (e) {
      // Network error — don't surface to user
      console.warn("Geofence ping failed:", e);
    }
  }

  function doGPSPing() {
    setWaiting();
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        // If we were previously reported as "off", report back on
        if (_lastPermissionState === "denied") {
          reportLocationStatus("on");
          if (window.portalSound) window.portalSound.play("medium");
        }
        _lastPermissionState = "granted";
        ping(pos.coords.latitude, pos.coords.longitude);
      },
      function (err) {
        if (err.code === err.PERMISSION_DENIED) {
          // Location was denied — report off if not already reported
          if (_lastPermissionState !== "denied") {
            _lastPermissionState = "denied";
            setLocationOff();
            reportLocationStatus("off");
          } else {
            setError("Location permission denied");
          }
        } else {
          setError(err.message || "GPS error");
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  }

  // Only run geofence pings when the user is checked in
  if (checkedIn) {
    // First ping after a short delay, then every 60 s
    setTimeout(doGPSPing, 3000);
    setInterval(doGPSPing, PING_INTERVAL_MS);
  }

})();
