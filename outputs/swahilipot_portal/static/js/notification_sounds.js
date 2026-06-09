/**
 * notification_sounds.js — SAH-VisionDevs
 *
 * Generates notification sounds using the Web Audio API (no external files needed).
 * Sound levels are mapped to notification priorities:
 *
 *   low      → soft single ping       (gentle, barely-there)
 *   medium   → double chime           (friendly attention chime)
 *   high     → triple alert tone      (clear attention-getter)
 *   critical → pulsing alarm beeps    (urgent, cannot miss)
 *
 * Usage (global):
 *   window.portalSound.play("low")
 *   window.portalSound.play("medium")
 *   window.portalSound.play("high")
 *   window.portalSound.play("critical")
 */

(function () {
  "use strict";

  // --- Audio context (created lazily on first user interaction) ---
  let ctx = null;

  function getCtx() {
    if (!ctx) {
      try {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
      } catch (e) {
        return null;
      }
    }
    // Re-resume if suspended (browser autoplay policy)
    if (ctx.state === "suspended") {
      ctx.resume();
    }
    return ctx;
  }

  /**
   * Play a single tone burst.
   * @param {number} frequency   Hz
   * @param {number} duration    seconds
   * @param {number} volume      0..1
   * @param {number} startAt     seconds offset from now
   * @param {"sine"|"square"|"sawtooth"|"triangle"} type  waveform
   */
  function tone(frequency, duration, volume, startAt, type) {
    const ac = getCtx();
    if (!ac) return;

    type = type || "sine";

    const osc   = ac.createOscillator();
    const gain  = ac.createGain();
    const now   = ac.currentTime + startAt;

    osc.type      = type;
    osc.frequency.setValueAtTime(frequency, now);

    // Smooth envelope to avoid clicks
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(volume, now + 0.02);
    gain.gain.setValueAtTime(volume, now + duration - 0.04);
    gain.gain.linearRampToValueAtTime(0, now + duration);

    osc.connect(gain);
    gain.connect(ac.destination);

    osc.start(now);
    osc.stop(now + duration);
  }

  // ── Sound definitions ────────────────────────────────────────────────────

  /**
   * LOW — soft single ping (820 Hz, 0.18 s, very quiet)
   * Use for: check-in / check-out / informational updates
   */
  function playLow() {
    tone(820, 0.18, 0.18, 0, "sine");
  }

  /**
   * MEDIUM — pleasant double chime (660 → 880 Hz, 0.22 s each)
   * Use for: task assigned, event notification, late arrival, auto-checkout warning
   */
  function playMedium() {
    tone(660, 0.22, 0.32, 0.00, "sine");
    tone(880, 0.22, 0.32, 0.25, "sine");
  }

  /**
   * HIGH — triple ascending alert (440 → 660 → 880 Hz)
   * Use for: location turned off, important system alerts
   */
  function playHigh() {
    tone(440, 0.20, 0.45, 0.00, "triangle");
    tone(660, 0.20, 0.45, 0.22, "triangle");
    tone(880, 0.20, 0.45, 0.44, "triangle");
  }

  /**
   * CRITICAL — rapid pulsing alarm (1000 Hz square wave, 4 pulses)
   * Use for: geofence violation, security alerts, critical errors
   */
  function playCritical() {
    for (let i = 0; i < 4; i++) {
      tone(1000, 0.12, 0.7, i * 0.18, "square");
      tone(750,  0.08, 0.5, i * 0.18 + 0.13, "square");
    }
  }

  // ── Public API ───────────────────────────────────────────────────────────

  window.portalSound = {
    /**
     * Play a notification sound by priority level.
     * @param {"low"|"medium"|"high"|"critical"} priority
     */
    play: function (priority) {
      const ac = getCtx();
      if (!ac) return; // Web Audio not supported

      switch ((priority || "low").toLowerCase()) {
        case "critical": playCritical(); break;
        case "high":     playHigh();     break;
        case "medium":   playMedium();   break;
        default:         playLow();      break;
      }
    },

    /**
     * Must be called once from a user gesture (click, keydown) to unlock
     * audio on browsers that require user interaction before audio playback.
     * The base template calls this automatically on any click / keydown.
     */
    unlock: function () {
      getCtx();
    },
  };

  // Unlock audio context on any user interaction
  ["click", "keydown", "touchstart"].forEach(function (evType) {
    document.addEventListener(evType, function _unlock() {
      window.portalSound.unlock();
      document.removeEventListener(evType, _unlock);
    }, { once: true, passive: true });
  });

})();
