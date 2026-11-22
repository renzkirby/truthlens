const ageMs = performance.now();
const timing = document.getElementById("timing");

timing.textContent = `First script executed at ${ageMs.toFixed(1)} ms after navigation start.`;

console.info("[TruthLens popup control]", {
  event: "minimal_popup_script_executed",
  contextAgeMs: Number(ageMs.toFixed(2)),
  timestampMs: Math.round(performance.timeOrigin + ageMs),
  readyState: document.readyState,
});
