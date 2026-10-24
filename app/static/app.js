"use strict";

const FRAME_INTERVAL_MS = 250; // minimum time between two frames (~4 per second at most); keeps one viewer from using a whole CPU on a small host
const BOX_SMOOTHING_MS = 60; // boxes close ~63% of the gap to their target every this many milliseconds
const MAX_FRAME_WIDTH = 480; // frames are shrunk to this width before sending
const ATTENDANCE_REFRESH_MS = 5000;
const HEALTH_REFRESH_MS = 15000;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Names come from users, so we always build elements with textContent, never innerHTML.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Small browser memory. Optional: if storage is blocked, the page still works, it just forgets.
function recall(area, key) {
  try {
    return window[area].getItem(key);
  } catch {
    return null;
  }
}
function remember(area, key, value) {
  try {
    window[area].setItem(key, value);
  } catch {
    /* storage blocked: ignore */
  }
}

const state = { enrolled: 0 };
const seen = new Map(); // name -> time first recognized in this browser session
let activeTab = "live";

// ---------- talking to the API ----------

function errorText(body, status) {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join("; ");
  return `Request failed (${status})`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorText(body, response.status));
  return body;
}

function setNotice(selector, message, ok = false) {
  const node = $(selector);
  node.hidden = !message;
  node.textContent = message;
  node.classList.toggle("ok", ok);
}

let toastTimer;
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.hidden = true), 2500);
}

// ---------- server status ----------

async function refreshHealth() {
  try {
    const health = await api("/health");
    $$("[data-threshold]").forEach((node) => (node.textContent = health.threshold.toFixed(2)));
  } catch {
    /* the Live tab shows an error message when the server cannot be reached */
  }
}

// ---------- admin mode ----------
// A demo switch, not security: it only shows or hides the Employees and Attendance tabs.

const adminButton = $("#admin-toggle");
const adminOn = () => Boolean(recall("sessionStorage", "adminMode"));

function setAdmin(on) {
  remember("sessionStorage", "adminMode", on ? "1" : "");
  $$("[data-admin]").forEach((node) => (node.hidden = !on));
  adminButton.textContent = on ? "Exit admin" : "Try Admin";
  adminButton.title = on
    ? "Hide the Employees and Attendance tabs"
    : "Show the Employees and Attendance tabs (no password: this is a demo)";
  if (!on && (activeTab === "employees" || activeTab === "attendance")) showTab("live");
  renderChecklist();
}

adminButton.addEventListener("click", () => setAdmin(!adminOn()));

// ---------- getting started: banner, checklist ----------

function setEnrolled(count) {
  state.enrolled = count;
  $("#none-enrolled").hidden = count > 0;
  renderChecklist();
}

async function refreshEnrolled() {
  try {
    setEnrolled((await api("/employees")).length);
  } catch {
    /* the Live tab shows an error message when the server cannot be reached */
  }
}

function renderChecklist() {
  const steps = [
    ["Click Try Admin (top right) to unlock the Employees tab", adminOn()],
    ["Open Employees and enroll yourself with one photo", state.enrolled > 0],
    ["Come back to Live and look at the camera", seen.size > 0],
    ["Open Attendance and find yourself under Present", Boolean(recall("sessionStorage", "attendanceChecked"))],
  ];
  const current = steps.findIndex(([, done]) => !done);
  const list = $("#checklist");
  list.replaceChildren(...steps.map(([text, done], index) => el("li", done ? "done" : index === current ? "current" : "", text)));
  $("#checklist-done").hidden = current !== -1;
}

// The privacy banners link to the "How recognition works" section of the Guide.
$$("[data-how-it-works]").forEach((button) =>
  button.addEventListener("click", () => {
    showTab("guide");
    const section = $("#how-it-works");
    section.open = true;
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  }),
);

$("#show-me").addEventListener("click", () => {
  setAdmin(true);
  showTab("employees");
});

// ---------- camera ----------

let stream = null;
const GATE_TEXT = "Face Attendance uses your camera to find faces. Each picture is analyzed by this server and is not kept.";

function cameraMessage(error) {
  switch (error.name) {
    case "InsecureContext":
      return "This address cannot use the camera. Open the page as http://localhost:8000 (browsers block cameras on other plain-HTTP addresses).";
    case "NotAllowedError":
    case "SecurityError":
      return "The camera is blocked. Click the camera icon in the address bar, choose Allow, then press Try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found. Plug in a webcam and press Try again.";
    case "NotReadableError":
      return "The camera is in use by another app. Close that app and press Try again.";
    default:
      return `Camera problem: ${error.message}`;
  }
}

async function startCamera() {
  if (stream) return;
  if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error("camera not available"), { name: "InsecureContext" });
  stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 640 }, height: { ideal: 480 } },
    audio: false,
  });
  for (const video of $$("video")) video.srcObject = stream;
}

function stopCamera() {
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  for (const video of $$("video")) video.srcObject = null;
}

// The explanation shown over the camera area before (or instead of) the browser's own permission prompt.
function showGate(message, isError = false) {
  for (const gate of $$(".gate")) {
    gate.hidden = false;
    gate.classList.toggle("error", isError);
    gate.querySelector(".gate-text").textContent = message;
    gate.querySelector(".start-camera").textContent = isError ? "Try again" : "Start camera";
  }
}

function hideGates() {
  $$(".gate").forEach((gate) => (gate.hidden = true));
}

async function enableCamera() {
  try {
    await startCamera();
    remember("sessionStorage", "cameraAllowed", "1");
    hideGates();
    if (activeTab === "live") liveLoop();
  } catch (error) {
    showGate(cameraMessage(error), true);
  }
}

// Start the camera if the visitor already agreed in this session; otherwise explain and wait for a click.
function openCamera() {
  if (stream) {
    if (activeTab === "live") liveLoop();
  } else if (recall("sessionStorage", "cameraAllowed")) {
    enableCamera();
  } else {
    showGate(GATE_TEXT);
  }
}

$$(".start-camera").forEach((button) => button.addEventListener("click", enableCamera));

// Match the frame box to the real camera shape (4:3, 16:9, ...).
for (const video of $$("video")) {
  video.addEventListener("loadedmetadata", () => {
    video.parentElement.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
  });
}

// Copy the current video frame into a shrunken JPEG.
function captureFrame(video) {
  if (!video.videoWidth) throw new Error("camera is not ready yet");
  const scale = Math.min(1, MAX_FRAME_WIDTH / video.videoWidth);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve({ blob, width: canvas.width, height: canvas.height }) : reject(new Error("could not capture a frame"))),
      "image/jpeg",
      0.85,
    ),
  );
}

// ---------- tabs ----------

function showTab(name) {
  activeTab = name;
  $$(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
  $$(".panel").forEach((panel) => (panel.hidden = panel.id !== `tab-${name}`));

  if (name === "live") {
    refreshEnrolled();
    openCamera();
  } else if (name === "employees") {
    openCamera();
    loadEmployees();
  } else {
    stopCamera(); // the camera light goes off when we are not using it
    if (name === "attendance") loadAttendance();
  }
}

$$(".tab").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));

// ---------- live tab ----------

let liveRunning = false;

async function liveLoop() {
  if (liveRunning || !stream) return;
  liveRunning = true;
  try {
    // One request at a time: we only send the next frame after the previous answer arrives.
    while (activeTab === "live" && stream && !document.hidden) {
      const started = performance.now();
      try {
        const frame = await captureFrame($("#live-video"));
        const form = new FormData();
        form.append("frame", frame.blob, "frame.jpg");
        const result = await api("/recognize", { method: "POST", body: form });
        setTargets(result.faces, frame);
        showLiveStats(result.faces);
        setNotice("#live-notice", "");
      } catch (error) {
        if (activeTab === "live") setNotice("#live-notice", error.message);
        clearOverlay();
      }
      await sleep(Math.max(0, FRAME_INTERVAL_MS - (performance.now() - started)));
    }
  } finally {
    liveRunning = false;
    if (activeTab !== "live") clearOverlay();
  }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && activeTab === "live") liveLoop();
});

// The server answers a few times a second, but the screen redraws ~60 times a second. Each box on screen
// ("shown") glides toward the latest position the server reported ("target") so the motion looks smooth.
const overlay = $("#overlay");
let shown = []; // [{x, y, w, h, target: {x, y, w, h, label, colour}}], x/y/w/h = where the box is drawn right now

function clearOverlay() {
  shown = [];
}

function setTargets(faces, frame) {
  if (overlay.width !== frame.width) overlay.width = frame.width; // the canvas uses the sent frame's pixels, so box coordinates match directly
  if (overlay.height !== frame.height) overlay.height = frame.height;

  const targets = faces.map((face) => {
    const [x, y, w, h] = face.box;
    const known = face.name !== null;
    const score = face.similarity === null ? "" : `  ${face.similarity.toFixed(2)}`;
    return {
      x: frame.width - x - w, // the video is mirrored, so the box is mirrored too
      y,
      w,
      h,
      label: `${known ? face.name : "Unknown"}${score}`,
      colour: known ? "#2ecc71" : "#ffa94d",
    };
  });

  // Keep each box that is already on screen gliding: pair every new target with the nearest old box.
  const unused = [...shown];
  shown = targets.map((target) => {
    let nearest = null;
    let nearestDistance = target.w; // farther away than one face width counts as a different face
    for (const old of unused) {
      const distance = Math.hypot(old.x + old.w / 2 - (target.x + target.w / 2), old.y + old.h / 2 - (target.y + target.h / 2));
      if (distance < nearestDistance) [nearest, nearestDistance] = [old, distance];
    }
    if (nearest) unused.splice(unused.indexOf(nearest), 1);
    const start = nearest ?? target; // a brand new face appears in place instead of flying in
    return { x: start.x, y: start.y, w: start.w, h: start.h, target };
  });
}

let lastFrameTime = performance.now();
function animateOverlay(now) {
  const ctx = overlay.getContext("2d");
  const step = 1 - Math.exp(-(now - lastFrameTime) / BOX_SMOOTHING_MS); // time-based, so it looks the same on any screen speed
  lastFrameTime = now;
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.lineWidth = 3;
  ctx.font = "600 18px system-ui, sans-serif";
  ctx.textBaseline = "top";

  for (const box of shown) {
    for (const key of ["x", "y", "w", "h"]) box[key] += (box.target[key] - box[key]) * step;
    const labelTop = Math.max(0, box.y - 28);
    ctx.strokeStyle = box.target.colour;
    ctx.strokeRect(box.x, box.y, box.w, box.h);
    ctx.fillStyle = box.target.colour;
    ctx.fillRect(box.x, labelTop, ctx.measureText(box.target.label).width + 12, 28);
    ctx.fillStyle = "#0b1020";
    ctx.fillText(box.target.label, box.x + 6, labelTop + 5);
  }
  requestAnimationFrame(animateOverlay);
}
requestAnimationFrame(animateOverlay);

function showLiveStats(faces) {
  $("#stat-faces").textContent = faces.length;

  let changed = false;
  for (const face of faces) {
    if (face.name === null) continue;
    if (face.newly_marked) toast(`${face.name} marked present`);
    if (!seen.has(face.name)) {
      seen.set(face.name, new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      changed = true;
    }
  }
  if (changed) {
    renderSeen();
    renderChecklist();
  }
}

function renderSeen() {
  const list = $("#live-seen");
  list.replaceChildren();
  if (!seen.size) {
    list.append(el("li", "muted", "Nobody recognized yet."));
    return;
  }
  for (const [name, time] of seen) {
    const row = el("li");
    row.append(el("span", "", `✓ ${name}`), el("span", "muted", time));
    list.append(row);
  }
}

// ---------- employees tab ----------

$("#enroll-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#enroll-button");
  button.disabled = true;
  try {
    const frame = await captureFrame($("#enroll-video"));
    const form = new FormData();
    form.append("name", $("#employee-name").value.trim());
    form.append("photo", frame.blob, "photo.jpg");
    const employee = await api("/employees", { method: "POST", body: form });
    $("#employee-name").value = "";
    setNotice("#enroll-notice", `${employee.name} enrolled. Go to the Live tab and look at the camera.`, true);
    await loadEmployees();
  } catch (error) {
    setNotice("#enroll-notice", error.message);
  } finally {
    button.disabled = false;
  }
});

async function loadEmployees() {
  const list = $("#employee-list");
  try {
    const employees = await api("/employees");
    setEnrolled(employees.length);
    $("#employee-count").textContent = employees.length ? `(${employees.length})` : "";
    $("#clear-all").hidden = !employees.length;
    list.replaceChildren();
    if (!employees.length) list.append(el("li", "muted", "Nobody enrolled yet. Type your name and capture a photo."));
    for (const employee of employees) {
      const remove = el("button", "danger", "Delete");
      remove.addEventListener("click", () => deleteEmployee(employee));
      const row = el("li");
      row.append(el("span", "", employee.name), remove);
      list.append(row);
    }
  } catch (error) {
    list.replaceChildren(el("li", "muted", error.message));
  }
}

async function deleteEmployee(employee) {
  if (!confirm(`Delete ${employee.name}? Their face data and attendance history are removed.`)) return;
  try {
    await api(`/employees/${employee.id}`, { method: "DELETE" });
    seen.delete(employee.name);
    renderSeen();
    await loadEmployees();
  } catch (error) {
    setNotice("#enroll-notice", error.message);
  }
}

$("#clear-all").addEventListener("click", async () => {
  if (!confirm("Delete ALL employees, their face data and the whole attendance history? This cannot be undone.")) return;
  try {
    await api("/employees", { method: "DELETE" });
    seen.clear();
    renderSeen();
    remember("sessionStorage", "attendanceChecked", "");
    setNotice("#enroll-notice", "");
    await loadEmployees();
    toast("All data cleared");
  } catch (error) {
    setNotice("#enroll-notice", error.message);
  }
});

// ---------- attendance tab ----------

async function loadAttendance(quiet = false) {
  const day = $("#day").value;
  try {
    const data = await api(day ? `/attendance?day=${encodeURIComponent(day)}` : "/attendance");
    $("#day").value = data.day; // first load: show the server's idea of "today"
    $("#counts").textContent = `${data.present.length} present`;

    const body = $("#present-body");
    body.replaceChildren();
    if (!data.present.length) {
      const row = el("tr");
      const cell = el("td", "empty", "Nobody was recognized on this day.");
      cell.colSpan = 3;
      row.append(cell);
      body.append(row);
    }
    for (const person of data.present) {
      const time = new Date(person.first_seen_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const row = el("tr");
      row.append(el("td", "", person.name), el("td", "", time), el("td", "", person.confidence.toFixed(2)));
      body.append(row);
    }

    setNotice("#att-notice", "");

    if (data.present.length && activeTab === "attendance" && !recall("sessionStorage", "attendanceChecked")) {
      remember("sessionStorage", "attendanceChecked", "1");
      renderChecklist();
    }
  } catch (error) {
    if (!quiet) setNotice("#att-notice", error.message);
  }
}

$("#day").addEventListener("change", () => loadAttendance());
setInterval(() => {
  if (activeTab === "attendance" && !document.hidden) loadAttendance(true);
}, ATTENDANCE_REFRESH_MS);

// ---------- welcome card (shown every time the page opens) ----------

function closeWelcome() {
  $("#welcome").hidden = true;
}

$("#welcome-ok").addEventListener("click", closeWelcome);
$("#welcome-guide").addEventListener("click", () => {
  closeWelcome();
  showTab("guide");
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#welcome").hidden) closeWelcome();
});

// ---------- start ----------

setAdmin(adminOn()); // remember the choice while this browser tab stays open
renderSeen();
renderChecklist();
refreshHealth();
setInterval(refreshHealth, HEALTH_REFRESH_MS);
showTab("live");
$("#welcome").hidden = false;
