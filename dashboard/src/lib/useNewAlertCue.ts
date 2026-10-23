import { useEffect, useRef, useState } from "react";
import type { Alert } from "./types";

const TITLE_PREFIX = "● New alert — ";

function playTone() {
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.2, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.6);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.6);
  } catch {
    // Audio can be blocked until the page is interacted with; the title and announcement still fire.
  }
}

/** Cues the operator once per real alert raised after this page opened; returns the screen-reader announcement. */
export function useNewAlertCue(alert: Alert | null, now: () => number = Date.now): string {
  const openedAt = useRef(now());
  const seen = useRef(new Set<string>());
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    if (!alert || alert.source !== "real" || seen.current.has(alert.alert_id) || Date.parse(alert.created_at) < openedAt.current) return;
    seen.current.add(alert.alert_id);
    playTone();
    if (!document.title.startsWith(TITLE_PREFIX)) document.title = TITLE_PREFIX + document.title;
    setAnnouncement(`New real drone alert at ${alert.location.lat.toFixed(5)}, ${alert.location.lon.toFixed(5)}`);
  }, [alert]);
  useEffect(() => {
    const clear = () => { if (document.title.startsWith(TITLE_PREFIX)) document.title = document.title.slice(TITLE_PREFIX.length); };
    window.addEventListener("focus", clear);
    return () => { window.removeEventListener("focus", clear); clear(); };
  }, []);
  return announcement;
}
