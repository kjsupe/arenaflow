function localDateString(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-");
}

const SCHEDULE_REFRESH_MS = 5000;
let scheduleRefreshTimer = null;
let scheduleRefreshInFlight = false;

const WEEKDAYS = [
  { key: "monday", label: "Monday" },
  { key: "tuesday", label: "Tuesday" },
  { key: "wednesday", label: "Wednesday" },
  { key: "thursday", label: "Thursday" },
  { key: "friday", label: "Friday" },
  { key: "saturday", label: "Saturday" },
  { key: "sunday", label: "Sunday" },
];

const GLOBAL_SETTING_KEYS = new Set([
  "venue_name",
  "venue_timezone",
  "app_logo_image",
  "public_base_url",
  "printer_mode",
  "printer_host",
  "printer_port",
  "cups_queue",
  "ticket_logo_enabled",
  "ticket_logo_raster",
  "ticket_logo_preview",
  "ticket_logo_width",
  "ticket_logo_height",
  "ticket_width_chars",
  "ticket_show_qr",
  "ticket_qr_label",
  "theme",
]);

const ATTRACTION_SETTING_KEYS = new Set([
  "open_time",
  "first_game_time",
  "close_time",
  "game_interval_minutes",
  "max_players_per_game",
  "default_blaster_count",
  "ticket_heading",
  "ticket_logo_text",
  "ticket_footer",
  "customer_reschedule_enabled",
  "customer_reschedule_last_game",
]);

const views = {
  login: document.querySelector('[data-view="login"]'),
  desk: document.querySelector('[data-view="desk"]'),
};

const state = {
  user: null,
  date: localDateString(),
  followCurrentDate: true,
  schedule: null,
  selectedSlot: null,
  slotSelectionMode: "auto",
  attractions: [],
  selectedAttractionId: null,
  adminSettings: null,
  adminAttractions: [],
  adminSelectedAttractionId: null,
  scheduleOverrides: [],
};

const els = {
  loginForm: document.getElementById("loginForm"),
  loginStatus: document.getElementById("loginStatus"),
  logoutButton: document.getElementById("logoutButton"),
  sessionUser: document.getElementById("sessionUser"),
  loginAppLogo: document.getElementById("loginAppLogo"),
  headerAppLogo: document.getElementById("headerAppLogo"),
  scheduleToggle: document.getElementById("scheduleToggle"),
  settingsToggle: document.getElementById("settingsToggle"),
  scheduleScreen: document.getElementById("scheduleScreen"),
  settingsScreen: document.getElementById("settingsScreen"),
  attractionTabs: document.getElementById("attractionTabs"),
  selectedAttractionTitle: document.getElementById("selectedAttractionTitle"),
  scheduleDate: document.getElementById("scheduleDate"),
  todayButton: document.getElementById("todayButton"),
  activeBlasters: document.getElementById("activeBlasters"),
  saveBlasters: document.getElementById("saveBlasters"),
  blasterStatus: document.getElementById("blasterStatus"),
  capacityText: document.getElementById("capacityText"),
  slotSummary: document.getElementById("slotSummary"),
  scheduleGrid: document.getElementById("scheduleGrid"),
  bookingForm: document.getElementById("bookingForm"),
  bookingGameTime: document.getElementById("bookingGameTime"),
  selectedSlotLabel: document.getElementById("selectedSlotLabel"),
  groupName: document.getElementById("groupName"),
  players: document.getElementById("players"),
  playersHint: document.getElementById("playersHint"),
  notes: document.getElementById("notes"),
  printTicket: document.getElementById("printTicket"),
  bookingStatus: document.getElementById("bookingStatus"),
  settingsForm: document.getElementById("settingsForm"),
  settingsStatus: document.getElementById("settingsStatus"),
  adminAttractionTabs: document.getElementById("adminAttractionTabs"),
  addAttraction: document.getElementById("addAttraction"),
  deleteAttraction: document.getElementById("deleteAttraction"),
  deleteAttractionHint: document.getElementById("deleteAttractionHint"),
  attractionName: document.getElementById("attractionName"),
  attractionActive: document.getElementById("attractionActive"),
  weeklySchedule: document.getElementById("weeklySchedule"),
  overrideDate: document.getElementById("overrideDate"),
  overrideLabel: document.getElementById("overrideLabel"),
  overrideClosed: document.getElementById("overrideClosed"),
  overrideOpenTime: document.getElementById("overrideOpenTime"),
  overrideFirstGameTime: document.getElementById("overrideFirstGameTime"),
  overrideCloseTime: document.getElementById("overrideCloseTime"),
  overrideInterval: document.getElementById("overrideInterval"),
  addOverride: document.getElementById("addOverride"),
  overrideList: document.getElementById("overrideList"),
  testPrinter: document.getElementById("testPrinter"),
  appLogoFile: document.getElementById("appLogoFile"),
  appLogoPreviewWrap: document.getElementById("appLogoPreviewWrap"),
  appLogoPreview: document.getElementById("appLogoPreview"),
  appLogoStatus: document.getElementById("appLogoStatus"),
  clearAppLogo: document.getElementById("clearAppLogo"),
  ticketLogoFile: document.getElementById("ticketLogoFile"),
  ticketLogoPreviewWrap: document.getElementById("ticketLogoPreviewWrap"),
  ticketLogoPreview: document.getElementById("ticketLogoPreview"),
  ticketLogoStatus: document.getElementById("ticketLogoStatus"),
  clearLogo: document.getElementById("clearLogo"),
  faviconLink: document.getElementById("appFavicon"),
  passwordForm: document.getElementById("passwordForm"),
  passwordStatus: document.getElementById("passwordStatus"),
};

function setStatus(el, message, type = "") {
  el.textContent = message || "";
  el.className = `status-line ${type}`.trim();
}

function setBlasterStatus(message, type = "") {
  els.blasterStatus.textContent = message;
  els.blasterStatus.className = `control-status ${type}`.trim();
}

function setLogoStatus(message, type = "") {
  els.ticketLogoStatus.textContent = message || "";
  els.ticketLogoStatus.className = `status-line ${type}`.trim();
}

function setAppLogoStatus(message, type = "") {
  els.appLogoStatus.textContent = message || "";
  els.appLogoStatus.className = `status-line ${type}`.trim();
}

function refreshFavicon() {
  if (!els.faviconLink) return;
  els.faviconLink.href = `/favicon.svg?v=${Date.now()}`;
}

function setPlayerWarning(message) {
  els.playersHint.textContent = message || "";
  els.playersHint.classList.toggle("hidden", !message);
}

function availableSpotsLabel(available) {
  return `${available} spot${available === 1 ? "" : "s"}`;
}

function localEffectiveAt() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${localDateString(now)}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function parseClockMinutes(value) {
  const [hour, minute] = String(value).split(":").map(Number);
  return (hour * 60) + minute;
}

function dateFromServiceDate(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(year, month - 1, day);
}

function slotStartDate(slot, schedule) {
  const slotClock = parseClockMinutes(slot.game_time);
  const firstGameClock = parseClockMinutes(schedule.settings.first_game_time);
  const closeClock = parseClockMinutes(schedule.settings.close_time);
  const start = dateFromServiceDate(schedule.date);
  start.setHours(Math.floor(slotClock / 60), slotClock % 60, 0, 0);
  if (closeClock <= firstGameClock && slotClock < firstGameClock) {
    start.setDate(start.getDate() + 1);
  }
  return start;
}

function currentMinute() {
  const now = new Date();
  now.setSeconds(0, 0);
  return now;
}

function isSlotBookable(slot, schedule) {
  if (!slot || Number(slot.available) < 1) return false;
  if (schedule.date === (schedule.current_service_date || localDateString())) {
    if (slot.starts_at && schedule.venue_now) {
      return slot.starts_at >= schedule.venue_now;
    }
    return slotStartDate(slot, schedule) >= currentMinute();
  }
  return true;
}

function findNextBookableSlot(schedule) {
  return schedule.slots.find((slot) => isSlotBookable(slot, schedule))
    || schedule.slots.find((slot) => Number(slot.available) > 0)
    || schedule.slots[0]
    || null;
}

function selectedSlotNeedsRefresh(schedule) {
  if (!state.selectedSlot) return true;
  const selected = schedule.slots.find((slot) => slot.game_time === state.selectedSlot.game_time);
  return !isSlotBookable(selected, schedule);
}

function updateSelectedSlot(schedule) {
  if (state.slotSelectionMode === "auto" || selectedSlotNeedsRefresh(schedule)) {
    state.slotSelectionMode = "auto";
    state.selectedSlot = findNextBookableSlot(schedule);
    return;
  }
  state.selectedSlot = schedule.slots.find((slot) => slot.game_time === state.selectedSlot.game_time);
}

async function refreshScheduleNow() {
  if (!state.user || views.desk.classList.contains("hidden") || scheduleRefreshInFlight) return;
  scheduleRefreshInFlight = true;
  try {
    await loadState();
  } catch (error) {
    setStatus(els.bookingStatus, error.message, "error");
  } finally {
    scheduleRefreshInFlight = false;
  }
}

function startScheduleAutoRefresh() {
  if (scheduleRefreshTimer) return;
  scheduleRefreshTimer = window.setInterval(refreshScheduleNow, SCHEDULE_REFRESH_MS);
}

function stopScheduleAutoRefresh() {
  if (!scheduleRefreshTimer) return;
  window.clearInterval(scheduleRefreshTimer);
  scheduleRefreshTimer = null;
}

function enforcePlayerLimit(notify = false) {
  const slot = state.selectedSlot;
  if (!slot) {
    setPlayerWarning("");
    return false;
  }

  const available = Number(slot.available);
  const requested = Number(els.players.value || 1);
  els.players.max = Math.max(1, available);

  if (available < 1) {
    const message = "This game is full. Select another game time.";
    setPlayerWarning(message);
    if (notify) {
      setStatus(els.bookingStatus, message, "error");
    }
    return true;
  }

  if (requested > available) {
    els.players.value = String(available);
    const message = `Only ${availableSpotsLabel(available)} are available for this game. Player count was adjusted to ${available}.`;
    setPlayerWarning(message);
    if (notify) {
      setStatus(els.bookingStatus, message, "error");
    }
    return true;
  }

  if (requested < 1) {
    els.players.value = "1";
  }
  setPlayerWarning("");
  return false;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function fileToImage(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Logo image could not be loaded."));
    image.src = URL.createObjectURL(file);
  });
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 8192;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function base64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function rasterToPreviewDataUrl(settings) {
  const width = Number(settings.ticket_logo_width || 0);
  const height = Number(settings.ticket_logo_height || 0);
  const raster = settings.ticket_logo_raster || "";
  if (!raster || width < 8 || height < 1 || width % 8 !== 0) return "";

  const bytes = base64ToBytes(raster);
  const rowBytes = width / 8;
  if (bytes.length !== rowBytes * height) return "";

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.fillStyle = "#111111";
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const byte = bytes[(y * rowBytes) + Math.floor(x / 8)];
      if (byte & (0x80 >> (x % 8))) {
        context.fillRect(x, y, 1, 1);
      }
    }
  }
  return canvas.toDataURL("image/png");
}

function logoPreviewSource(settings) {
  return settings.ticket_logo_preview || rasterToPreviewDataUrl(settings);
}

function renderLogoPreview(settings) {
  const source = logoPreviewSource(settings);
  if (!source) {
    els.ticketLogoPreview.removeAttribute("src");
    els.ticketLogoPreviewWrap.classList.add("hidden");
    return;
  }
  els.ticketLogoPreview.src = source;
  els.ticketLogoPreviewWrap.classList.remove("hidden");
}

function renderAppLogo(settings = {}) {
  if (!Object.prototype.hasOwnProperty.call(settings, "app_logo_image")) return;
  const source = settings.app_logo_image || "";
  [els.loginAppLogo, els.headerAppLogo].forEach((image) => {
    if (!image) return;
    if (!source) {
      image.removeAttribute("src");
      image.classList.add("hidden");
      return;
    }
    image.src = source;
    image.classList.remove("hidden");
  });
}

function renderAppLogoPreview(settings = {}) {
  const source = settings.app_logo_image || "";
  if (!source) {
    els.appLogoPreview.removeAttribute("src");
    els.appLogoPreviewWrap.classList.add("hidden");
    return;
  }
  els.appLogoPreview.src = source;
  els.appLogoPreviewWrap.classList.remove("hidden");
}

async function logoFileToRaster(file) {
  if (!file || !file.size) return null;
  if (file.size > 3 * 1024 * 1024) {
    throw new Error("Logo image must be smaller than 3 MB.");
  }

  const image = await fileToImage(file);
  const maxWidth = 384;
  const maxHeight = 160;
  const scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
  const drawnWidth = Math.max(8, Math.round(image.naturalWidth * scale));
  const drawnHeight = Math.max(1, Math.round(image.naturalHeight * scale));
  const width = Math.ceil(drawnWidth / 8) * 8;
  const height = drawnHeight;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.drawImage(image, Math.floor((width - drawnWidth) / 2), 0, drawnWidth, drawnHeight);
  URL.revokeObjectURL(image.src);

  const pixels = context.getImageData(0, 0, width, height).data;
  const rowBytes = width / 8;
  const raster = new Uint8Array(rowBytes * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const pixelIndex = (y * width + x) * 4;
      const red = pixels[pixelIndex];
      const green = pixels[pixelIndex + 1];
      const blue = pixels[pixelIndex + 2];
      const alpha = pixels[pixelIndex + 3] / 255;
      const luminance = ((red * 0.299) + (green * 0.587) + (blue * 0.114)) * alpha + (255 * (1 - alpha));
      if (luminance < 168) {
        raster[(y * rowBytes) + Math.floor(x / 8)] |= 0x80 >> (x % 8);
      }
    }
  }

  return {
    ticket_logo_raster: bytesToBase64(raster),
    ticket_logo_preview: canvas.toDataURL("image/png"),
    ticket_logo_width: String(width),
    ticket_logo_height: String(height),
  };
}

async function appLogoFileToDataUrl(file) {
  if (!file || !file.size) return null;
  if (file.size > 3 * 1024 * 1024) {
    throw new Error("App logo image must be smaller than 3 MB.");
  }

  const image = await fileToImage(file);
  const maxWidth = 640;
  const maxHeight = 240;
  const scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);
  URL.revokeObjectURL(image.src);

  return {
    app_logo_image: canvas.toDataURL("image/png"),
  };
}

function showDesk(user) {
  state.user = user;
  views.login.classList.add("hidden");
  views.desk.classList.remove("hidden");
  els.sessionUser.textContent = `${user.display_name} (${user.role})`;
  els.settingsToggle.classList.toggle("hidden", user.role !== "admin");
  startScheduleAutoRefresh();
  if (user.role !== "admin") {
    showScreen("schedule");
  }
}

function showLogin() {
  state.user = null;
  stopScheduleAutoRefresh();
  views.login.classList.remove("hidden");
  views.desk.classList.add("hidden");
}

function applyTheme(theme) {
  document.body.dataset.theme = theme || "laser";
}

async function loadPublicSettings() {
  const data = await api("/api/public-settings");
  applyTheme(data.settings.theme);
  renderAppLogo(data.settings);
}

function showScreen(screen) {
  const canUseSettings = state.user && state.user.role === "admin";
  const isSettings = screen === "settings" && canUseSettings;
  els.scheduleScreen.classList.toggle("hidden", isSettings);
  els.settingsScreen.classList.toggle("hidden", !isSettings);
  els.scheduleToggle.classList.toggle("active", !isSettings);
  els.settingsToggle.classList.toggle("active", isSettings);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadState(options = {}) {
  const params = new URLSearchParams({ date: state.date });
  if (state.selectedAttractionId) {
    params.set("attraction_id", String(state.selectedAttractionId));
  }
  const data = await api(`/api/state?${params.toString()}`);
  const shouldFollowCurrentDate = state.followCurrentDate || options.forceCurrentDate;
  if (
    shouldFollowCurrentDate
    && !options.skipCurrentDateRedirect
    && data.current_service_date
    && data.current_service_date !== state.date
  ) {
    state.date = data.current_service_date;
    state.selectedSlot = null;
    state.slotSelectionMode = "auto";
    els.scheduleDate.value = state.date;
    await loadState({ skipCurrentDateRedirect: true });
    return;
  }
  state.schedule = data;
  state.attractions = data.attractions || [];
  if (data.attraction) {
    state.selectedAttractionId = Number(data.attraction.id);
  }
  if (data.user) {
    state.user = data.user;
  }
  renderState();
}

function renderAttractionTabs() {
  const attractions = state.attractions || [];
  if (!attractions.length) {
    els.attractionTabs.innerHTML = "";
    return;
  }
  els.attractionTabs.innerHTML = attractions.map((attraction) => `
    <button
      class="attraction-tab ${Number(attraction.id) === Number(state.selectedAttractionId) ? "active" : ""}"
      type="button"
      role="tab"
      aria-selected="${Number(attraction.id) === Number(state.selectedAttractionId) ? "true" : "false"}"
      data-attraction-id="${attraction.id}">
      ${escapeHtml(attraction.name)}
    </button>
  `).join("");
  els.attractionTabs.querySelectorAll("[data-attraction-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextId = Number(button.dataset.attractionId);
      if (nextId === Number(state.selectedAttractionId)) return;
      state.selectedAttractionId = nextId;
      state.selectedSlot = null;
      state.slotSelectionMode = "auto";
      await loadState();
    });
  });
}

function renderState() {
  const data = state.schedule;
  if (!data) return;

  applyTheme(data.settings.theme);
  renderAppLogo(data.settings);
  renderAttractionTabs();
  const attractionName = data.attraction ? data.attraction.name : "Schedule";
  els.selectedAttractionTitle.textContent = `${attractionName} Schedule`;
  els.scheduleDate.value = data.date;
  els.activeBlasters.value = data.active_blasters;
  const maxPlayers = Number(data.settings.max_players_per_game);
  const capacity = Math.min(maxPlayers, Number(data.active_blasters));
  els.capacityText.textContent = `${capacity} players`;

  const booked = data.slots.reduce((total, slot) => total + Number(slot.booked), 0);
  const openGames = data.slots.filter((slot) => slot.available > 0).length;
  const scheduleLabel = data.settings.schedule_label ? `${data.settings.schedule_label} / ` : "";
  els.slotSummary.textContent = data.settings.schedule_closed === "yes"
    ? `${scheduleLabel}closed`
    : `${scheduleLabel}${data.slots.length} games / every ${data.settings.game_interval_minutes} min / ${openGames} open / ${booked} booked`;

  updateSelectedSlot(data);

  renderSchedule();
  renderSelectedSlot();
}

function renderSchedule() {
  const slots = state.schedule.slots;
  if (!slots.length) {
    els.scheduleGrid.innerHTML = `
      <div class="empty-schedule">
        <strong>No games scheduled</strong>
        <span>This date is closed or does not have any configured game times.</span>
      </div>
    `;
    return;
  }

  els.scheduleGrid.innerHTML = slots.map((slot) => {
    const classes = [
      "slot-card",
      slot.status === "full" ? "full" : "",
      state.selectedSlot && state.selectedSlot.game_time === slot.game_time ? "selected" : "",
    ].filter(Boolean).join(" ");

    const bookings = slot.bookings.length
      ? slot.bookings.map(renderBookingChip).join("")
      : '<span class="booking-meta">No bookings</span>';

    return `
      <div class="${classes}" role="button" tabindex="0" data-slot="${slot.game_time}">
        <span class="slot-time">
          <strong>${escapeHtml(slot.display_time)}</strong>
          <span>Game start</span>
        </span>
        <span class="slot-bookings">${bookings}</span>
        <span class="slot-count">
          <strong>${slot.available}</strong>
          <span>of ${slot.capacity}</span>
        </span>
      </div>
    `;
  }).join("");

  els.scheduleGrid.querySelectorAll(".slot-card").forEach((row) => {
    const selectSlot = () => {
      state.selectedSlot = state.schedule.slots.find((slot) => slot.game_time === row.dataset.slot);
      state.slotSelectionMode = "manual";
      renderState();
    };
    row.addEventListener("click", selectSlot);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectSlot();
      }
    });
  });

  els.scheduleGrid.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const bookingId = button.dataset.bookingId;
      const action = button.dataset.action;
      if (action === "cancel" && !confirm("Cancel this booking?")) return;
      try {
        const result = await api(`/api/bookings/${bookingId}/${action}`, { method: "POST", body: "{}" });
        if (result.state) {
          state.schedule = result.state;
          renderState();
        }
        if (result.print_result) {
          setStatus(els.bookingStatus, result.print_result.message, result.print_result.status === "ok" ? "ok" : "error");
        }
      } catch (error) {
        setStatus(els.bookingStatus, error.message, "error");
      }
    });
  });
}

function renderBookingChip(booking) {
  const type = booking.booking_type === "party" ? '<span class="party-badge">Party</span>' : "";
  const note = booking.notes ? `<span class="booking-meta">${escapeHtml(booking.notes)}</span>` : "";
  const actions = booking.status === "booked" ? `
    <span class="chip-actions">
      <button type="button" data-action="reprint" data-booking-id="${booking.id}">Reprint</button>
      <button type="button" data-action="cancel" data-booking-id="${booking.id}">Cancel</button>
    </span>
  ` : "";
  return `
    <span class="booking-chip ${booking.status === "cancelled" ? "cancelled" : ""}">
      ${type}
      <span class="booking-title">${escapeHtml(booking.group_name)}</span>
      <span class="booking-meta">${booking.admitted} player${Number(booking.admitted) === 1 ? "" : "s"}</span>
      ${note}
      ${actions}
    </span>
  `;
}

function renderSelectedSlot() {
  const slot = state.selectedSlot;
  if (!slot) {
    els.bookingGameTime.value = "";
    els.selectedSlotLabel.textContent = "Select a game";
    els.bookingForm.querySelector("button[type='submit']").disabled = true;
    return;
  }
  els.bookingGameTime.value = slot.game_time;
  els.selectedSlotLabel.textContent = `${slot.display_time} / ${slot.available} open`;
  els.bookingForm.querySelector("button[type='submit']").disabled = slot.available < 1;
  enforcePlayerLimit();
}

function resetBookingFormForNextEntry() {
  const keepPrintTicket = els.printTicket.checked;
  els.bookingForm.reset();
  els.printTicket.checked = keepPrintTicket;
  els.groupName.value = "";
  els.groupName.disabled = false;
  els.groupName.readOnly = false;
  els.players.value = "1";
  els.notes.value = "";
  setPlayerWarning("");
  renderSelectedSlot();
  window.requestAnimationFrame(() => {
    els.groupName.focus({ preventScroll: true });
  });
}

function parseSettingsJson(value, fallback) {
  try {
    const parsed = JSON.parse(value || "");
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function defaultDaySettings(settings = state.adminSettings || {}) {
  return {
    closed: false,
    open_time: settings.open_time || "12:00",
    first_game_time: settings.first_game_time || "12:00",
    close_time: settings.close_time || "22:00",
    game_interval_minutes: settings.game_interval_minutes || "15",
  };
}

function normalizeClientDaySchedule(raw = {}, fallback = defaultDaySettings()) {
  return {
    closed: Boolean(raw.closed),
    open_time: raw.open_time || fallback.open_time,
    first_game_time: raw.first_game_time || fallback.first_game_time,
    close_time: raw.close_time || fallback.close_time,
    game_interval_minutes: String(raw.game_interval_minutes || fallback.game_interval_minutes),
  };
}

function renderWeeklySchedule(settings) {
  const defaults = defaultDaySettings(settings);
  const weekly = parseSettingsJson(settings.weekly_schedule_json, {});
  els.weeklySchedule.innerHTML = WEEKDAYS.map((day) => {
    const daySettings = normalizeClientDaySchedule(weekly[day.key], defaults);
    return `
      <div class="weekly-row" data-weekday="${day.key}">
        <strong>${day.label}</strong>
        <label class="check-row compact-check">
          <input type="checkbox" data-weekly-field="closed" ${daySettings.closed ? "checked" : ""}>
          Closed
        </label>
        <label>
          Open
          <input type="time" data-weekly-field="open_time" value="${escapeHtml(daySettings.open_time)}" required>
        </label>
        <label>
          First game
          <input type="time" data-weekly-field="first_game_time" value="${escapeHtml(daySettings.first_game_time)}" required>
        </label>
        <label>
          Close
          <input type="time" data-weekly-field="close_time" value="${escapeHtml(daySettings.close_time)}" required>
        </label>
        <label>
          Interval
          <input type="number" data-weekly-field="game_interval_minutes" min="5" max="120" value="${escapeHtml(daySettings.game_interval_minutes)}" required>
        </label>
      </div>
    `;
  }).join("");
}

function collectWeeklySchedule() {
  const weekly = {};
  els.weeklySchedule.querySelectorAll("[data-weekday]").forEach((row) => {
    const day = row.dataset.weekday;
    weekly[day] = {
      closed: row.querySelector("[data-weekly-field='closed']").checked,
      open_time: row.querySelector("[data-weekly-field='open_time']").value,
      first_game_time: row.querySelector("[data-weekly-field='first_game_time']").value,
      close_time: row.querySelector("[data-weekly-field='close_time']").value,
      game_interval_minutes: row.querySelector("[data-weekly-field='game_interval_minutes']").value,
    };
  });
  return weekly;
}

function resetOverrideDraft(settings = state.adminSettings || {}) {
  const defaults = defaultDaySettings(settings);
  els.overrideDate.value = "";
  els.overrideLabel.value = "";
  els.overrideClosed.checked = false;
  els.overrideOpenTime.value = defaults.open_time;
  els.overrideFirstGameTime.value = defaults.first_game_time;
  els.overrideCloseTime.value = defaults.close_time;
  els.overrideInterval.value = defaults.game_interval_minutes;
}

function renderScheduleOverrides() {
  if (!state.scheduleOverrides.length) {
    els.overrideList.innerHTML = '<p class="field-note">No holiday overrides are configured.</p>';
    return;
  }

  els.overrideList.innerHTML = state.scheduleOverrides.map((override) => {
    const status = override.closed
      ? "Closed"
      : `${escapeHtml(override.open_time)} / first ${escapeHtml(override.first_game_time)} / close ${escapeHtml(override.close_time)} / ${escapeHtml(override.game_interval_minutes)} min`;
    return `
      <div class="override-row">
        <span>
          <strong>${escapeHtml(override.date)}</strong>
          <em>${escapeHtml(override.label || "Holiday override")}</em>
          <small>${status}</small>
        </span>
        <button class="ghost-action" type="button" data-remove-override="${escapeHtml(override.date)}">Remove</button>
      </div>
    `;
  }).join("");

  els.overrideList.querySelectorAll("[data-remove-override]").forEach((button) => {
    button.addEventListener("click", () => {
      state.scheduleOverrides = state.scheduleOverrides.filter((override) => override.date !== button.dataset.removeOverride);
      renderScheduleOverrides();
    });
  });
}

function collectOverrideDraft() {
  const date = els.overrideDate.value;
  if (!date) {
    throw new Error("Choose a date for the holiday override.");
  }
  return {
    date,
    label: els.overrideLabel.value.trim() || "Holiday override",
    closed: els.overrideClosed.checked,
    open_time: els.overrideOpenTime.value,
    first_game_time: els.overrideFirstGameTime.value,
    close_time: els.overrideCloseTime.value,
    game_interval_minutes: els.overrideInterval.value,
  };
}

function selectedAdminAttraction() {
  return (state.adminAttractions || []).find((attraction) => Number(attraction.id) === Number(state.adminSelectedAttractionId))
    || (state.adminAttractions || [])[0]
    || null;
}

function renderAdminAttractionTabs() {
  const attractions = state.adminAttractions || [];
  if (!attractions.length) {
    els.adminAttractionTabs.innerHTML = '<p class="field-note">No attractions are configured.</p>';
    return;
  }
  els.adminAttractionTabs.innerHTML = attractions.map((attraction) => `
    <button
      class="attraction-tab ${Number(attraction.id) === Number(state.adminSelectedAttractionId) ? "active" : ""} ${attraction.active ? "" : "inactive"}"
      type="button"
      role="tab"
      aria-selected="${Number(attraction.id) === Number(state.adminSelectedAttractionId) ? "true" : "false"}"
      data-admin-attraction-id="${attraction.id}">
      ${escapeHtml(attraction.name)}
    </button>
  `).join("");
  els.adminAttractionTabs.querySelectorAll("[data-admin-attraction-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.adminSelectedAttractionId = Number(button.dataset.adminAttractionId);
      fillAttractionSettings();
      setStatus(els.settingsStatus, "Editing attraction settings. Save settings to keep changes.", "");
    });
  });
}

function fillGlobalSettings(settings) {
  for (const [key, value] of Object.entries(settings)) {
    if (!GLOBAL_SETTING_KEYS.has(key)) continue;
    const field = els.settingsForm.elements[key];
    if (field) field.value = value;
  }
}

function updateAttractionDeleteState(attraction) {
  if (!els.deleteAttraction || !els.deleteAttractionHint) return;
  if (!attraction) {
    els.deleteAttraction.disabled = true;
    els.deleteAttractionHint.textContent = "Select an attraction before deleting.";
    return;
  }

  const bookingCount = Number(attraction.booking_count || 0);
  const canDelete = Boolean(attraction.can_delete);
  els.deleteAttraction.disabled = !canDelete;
  if (state.adminAttractions.length <= 1) {
    els.deleteAttractionHint.textContent = "At least one attraction is required.";
  } else if (bookingCount > 0) {
    els.deleteAttractionHint.textContent = `${bookingCount} booking${bookingCount === 1 ? "" : "s"} use this attraction. Hide it from the marshal schedule instead.`;
  } else {
    els.deleteAttractionHint.textContent = "This unused attraction can be permanently deleted.";
  }
}

function fillAttractionSettings() {
  const attraction = selectedAdminAttraction();
  renderAdminAttractionTabs();
  if (!attraction) {
    els.attractionName.value = "";
    els.attractionActive.value = "yes";
    updateAttractionDeleteState(null);
    return;
  }
  els.attractionName.value = attraction.name || "";
  els.attractionActive.value = attraction.active ? "yes" : "no";
  const settings = attraction.settings || {};
  for (const key of ATTRACTION_SETTING_KEYS) {
    const field = els.settingsForm.elements[key];
    if (field && Object.prototype.hasOwnProperty.call(settings, key)) {
      field.value = settings[key];
    }
  }
  renderWeeklySchedule(settings);
  const overrides = parseSettingsJson(settings.schedule_overrides_json, []);
  state.scheduleOverrides = Array.isArray(overrides) ? overrides : [];
  renderScheduleOverrides();
  resetOverrideDraft(settings);
  updateAttractionDeleteState(attraction);
}

async function loadAdminSettings() {
  if (state.user.role !== "admin") return;
  const data = await api("/api/admin/settings");
  state.adminSettings = data.settings;
  state.adminAttractions = data.attractions || [];
  if (!state.adminSelectedAttractionId || !state.adminAttractions.some((item) => Number(item.id) === Number(state.adminSelectedAttractionId))) {
    state.adminSelectedAttractionId = state.selectedAttractionId || (state.adminAttractions[0] && Number(state.adminAttractions[0].id));
  }
  fillGlobalSettings(data.settings);
  fillAttractionSettings();
  els.appLogoFile.value = "";
  renderAppLogo(data.settings);
  renderAppLogoPreview(data.settings);
  if (data.settings.app_logo_image) {
    setAppLogoStatus("Full-color app logo configured.", "ok");
  } else {
    setAppLogoStatus("No app logo uploaded. ArenaFlow text branding will be used.", "");
  }
  els.ticketLogoFile.value = "";
  renderLogoPreview(data.settings);
  if (data.settings.ticket_logo_raster) {
    setLogoStatus(`Logo image configured (${data.settings.ticket_logo_width} x ${data.settings.ticket_logo_height}).`, "ok");
  } else {
    setLogoStatus("No uploaded logo image. The ticket will use the logo text.", "");
  }
  applyTheme(data.settings.theme);
}

els.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus(els.loginStatus, "Checking login...");
  const form = new FormData(els.loginForm);
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password"),
      }),
    });
    showDesk(data.user);
    showScreen("schedule");
    state.followCurrentDate = true;
    els.scheduleDate.value = state.date;
    await loadState();
    setStatus(els.loginStatus, "");
  } catch (error) {
    setStatus(els.loginStatus, error.message, "error");
  }
});

els.logoutButton.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  await loadPublicSettings().catch(() => applyTheme("laser"));
  showLogin();
});

els.scheduleToggle.addEventListener("click", () => {
  showScreen("schedule");
  refreshScheduleNow();
});

window.addEventListener("focus", refreshScheduleNow);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshScheduleNow();
  }
});

els.settingsToggle.addEventListener("click", async () => {
  showScreen("settings");
  if (!state.adminSettings) {
    try {
      await loadAdminSettings();
    } catch (error) {
      setStatus(els.settingsStatus, error.message, "error");
    }
  }
});

els.scheduleDate.addEventListener("change", async () => {
  if (!els.scheduleDate.value) return;
  state.followCurrentDate = false;
  state.date = els.scheduleDate.value;
  state.selectedSlot = null;
  state.slotSelectionMode = "auto";
  await loadState();
});

els.todayButton.addEventListener("click", async () => {
  try {
    state.followCurrentDate = true;
    state.selectedSlot = null;
    state.slotSelectionMode = "auto";
    await loadState({ forceCurrentDate: true });
  } catch (error) {
    setStatus(els.bookingStatus, error.message, "error");
  }
});

els.saveBlasters.addEventListener("click", async () => {
  try {
    const effectiveAt = localEffectiveAt();
    const data = await api("/api/blasters", {
      method: "POST",
      body: JSON.stringify({
        attraction_id: state.selectedAttractionId,
        date: state.date,
        active_blasters: Number(els.activeBlasters.value),
        effective_at: effectiveAt,
      }),
    });
    state.schedule = data;
    renderState();
    setBlasterStatus("Applied from the current time forward. Future days will keep this blaster count until it is changed again.", "ok");
  } catch (error) {
    setBlasterStatus(error.message, "error");
  }
});

els.players.addEventListener("input", () => {
  enforcePlayerLimit(true);
});

els.bookingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedSlot) return;
  if (enforcePlayerLimit(true)) return;
  setStatus(els.bookingStatus, "Booking...");
  const form = new FormData(els.bookingForm);
  const payload = {
    attraction_id: state.selectedAttractionId,
    date: state.date,
    game_time: form.get("game_time"),
    group_name: form.get("group_name"),
    players: Number(form.get("players")),
    booking_type: form.get("booking_type"),
    notes: form.get("notes"),
    print_ticket: els.printTicket.checked,
  };
  try {
    const data = await api("/api/bookings", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.schedule = data.state;
    state.slotSelectionMode = "auto";
    renderState();
    resetBookingFormForNextEntry();
    const printResult = data.result.print_result;
    const printMessage = printResult ? ` ${printResult.message}` : "";
    setStatus(els.bookingStatus, `Booked ${data.result.booking.admitted} player${Number(data.result.booking.admitted) === 1 ? "" : "s"}.${printMessage}`, printResult && printResult.status === "error" ? "error" : "ok");
  } catch (error) {
    setStatus(els.bookingStatus, error.message, "error");
  }
});

els.settingsForm.querySelectorAll("input[name='theme']").forEach((themeInput) => {
  themeInput.addEventListener("change", () => {
    applyTheme(themeInput.value);
  });
});

els.addOverride.addEventListener("click", () => {
  try {
    const override = collectOverrideDraft();
    state.scheduleOverrides = [
      ...state.scheduleOverrides.filter((item) => item.date !== override.date),
      override,
    ].sort((left, right) => left.date.localeCompare(right.date));
    renderScheduleOverrides();
    resetOverrideDraft();
    setStatus(els.settingsStatus, "Holiday override added. Save settings to keep it.", "ok");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.addAttraction.addEventListener("click", async () => {
  const name = window.prompt("Attraction name", "New Attraction");
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    setStatus(els.settingsStatus, "Attraction name is required.", "error");
    return;
  }
  setStatus(els.settingsStatus, "Adding attraction...");
  try {
    const data = await api("/api/admin/attractions", {
      method: "POST",
      body: JSON.stringify({ name: trimmed }),
    });
    state.adminAttractions = data.attractions || [];
    state.adminSelectedAttractionId = Number(data.attraction.id);
    fillAttractionSettings();
    setStatus(els.settingsStatus, "Attraction added. Save settings after any schedule changes.", "ok");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.deleteAttraction.addEventListener("click", async () => {
  const attraction = selectedAdminAttraction();
  if (!attraction) {
    setStatus(els.settingsStatus, "Select an attraction first.", "error");
    return;
  }
  if (!attraction.can_delete) {
    const bookingCount = Number(attraction.booking_count || 0);
    const reason = bookingCount > 0
      ? "This attraction has booking history. Set 'Show on marshal schedule' to No instead."
      : "At least one attraction is required.";
    setStatus(els.settingsStatus, reason, "error");
    return;
  }
  if (!window.confirm(`Delete "${attraction.name}"? This permanently removes the attraction and its capacity changes.`)) {
    return;
  }
  setStatus(els.settingsStatus, "Deleting attraction...");
  try {
    const data = await api(`/api/admin/attractions/${attraction.id}`, { method: "DELETE" });
    state.adminAttractions = data.attractions || [];
    if (Number(state.selectedAttractionId) === Number(attraction.id)) {
      state.selectedAttractionId = null;
    }
    state.adminSelectedAttractionId = (state.adminAttractions[0] && Number(state.adminAttractions[0].id)) || null;
    fillAttractionSettings();
    await loadState();
    setStatus(els.settingsStatus, "Attraction deleted.", "ok");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus(els.settingsStatus, "Saving...");
  const form = new FormData(els.settingsForm);
  const settings = {};
  const attractionSettings = {};
  for (const [key, value] of form.entries()) {
    if (GLOBAL_SETTING_KEYS.has(key)) {
      settings[key] = value;
    } else if (ATTRACTION_SETTING_KEYS.has(key)) {
      attractionSettings[key] = value;
    }
  }
  attractionSettings.weekly_schedule_json = JSON.stringify(collectWeeklySchedule());
  attractionSettings.schedule_overrides_json = JSON.stringify(state.scheduleOverrides);
  try {
    const appLogoSettings = await appLogoFileToDataUrl(els.appLogoFile.files[0]);
    if (appLogoSettings) {
      Object.assign(settings, appLogoSettings);
      setAppLogoStatus("Full-color app logo prepared for the login and scheduler screens.", "ok");
    }
    const logoSettings = await logoFileToRaster(els.ticketLogoFile.files[0]);
    if (logoSettings) {
      Object.assign(settings, logoSettings);
      setLogoStatus("Logo image converted for the ticket printer.", "ok");
    }
    const data = await api("/api/admin/settings", {
      method: "POST",
      body: JSON.stringify({
        settings,
        attraction: {
          id: state.adminSelectedAttractionId,
          name: els.attractionName.value,
          active: els.attractionActive.value,
          settings: attractionSettings,
        },
      }),
    });
    state.adminSettings = data.settings;
    state.adminAttractions = data.attractions || [];
    fillAttractionSettings();
    els.appLogoFile.value = "";
    renderAppLogo(data.settings);
    renderAppLogoPreview(data.settings);
    if (data.settings.app_logo_image) {
      setAppLogoStatus("Full-color app logo configured.", "ok");
    } else {
      setAppLogoStatus("No app logo uploaded. ArenaFlow text branding will be used.", "");
    }
    els.ticketLogoFile.value = "";
    renderLogoPreview(data.settings);
    if (data.settings.ticket_logo_raster) {
      setLogoStatus(`Logo image configured (${data.settings.ticket_logo_width} x ${data.settings.ticket_logo_height}).`, "ok");
    } else {
      setLogoStatus("No uploaded logo image. The ticket will use the logo text.", "");
    }
    applyTheme(data.settings.theme);
    refreshFavicon();
    const savedAttraction = selectedAdminAttraction();
    if (savedAttraction && !savedAttraction.active && Number(state.selectedAttractionId) === Number(savedAttraction.id)) {
      state.selectedAttractionId = null;
    }
    await loadState();
    setStatus(els.settingsStatus, "Settings saved.", "ok");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.testPrinter.addEventListener("click", async () => {
  setStatus(els.settingsStatus, "Sending test ticket...");
  try {
    const data = await api("/api/admin/printer-test", { method: "POST", body: "{}" });
    const result = data.print_result;
    setStatus(els.settingsStatus, result.message, result.status === "ok" ? "ok" : "error");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.clearAppLogo.addEventListener("click", async () => {
  setStatus(els.settingsStatus, "Removing app logo...");
  try {
    const data = await api("/api/admin/settings", {
      method: "POST",
      body: JSON.stringify({
        settings: {
          app_logo_image: "",
        },
      }),
    });
    state.adminSettings = data.settings;
    els.appLogoFile.value = "";
    renderAppLogo(data.settings);
    renderAppLogoPreview(data.settings);
    refreshFavicon();
    setAppLogoStatus("No app logo uploaded. ArenaFlow text branding will be used.", "");
    setStatus(els.settingsStatus, "App logo removed.", "ok");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.clearLogo.addEventListener("click", async () => {
  setStatus(els.settingsStatus, "Removing logo...");
  try {
    const data = await api("/api/admin/settings", {
      method: "POST",
      body: JSON.stringify({
        settings: {
          ticket_logo_raster: "",
          ticket_logo_preview: "",
          ticket_logo_width: "0",
          ticket_logo_height: "0",
        },
      }),
    });
    state.adminSettings = data.settings;
    els.ticketLogoFile.value = "";
    renderLogoPreview(data.settings);
    refreshFavicon();
    setLogoStatus("No uploaded logo image. The ticket will use the logo text.", "");
    setStatus(els.settingsStatus, "Logo removed.", "ok");
  } catch (error) {
    setStatus(els.settingsStatus, error.message, "error");
  }
});

els.passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus(els.passwordStatus, "Updating...");
  const form = new FormData(els.passwordForm);
  try {
    await api("/api/admin/password", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password"),
      }),
    });
    els.passwordForm.reset();
    setStatus(els.passwordStatus, "Password updated.", "ok");
  } catch (error) {
    setStatus(els.passwordStatus, error.message, "error");
  }
});

async function boot() {
  els.scheduleDate.value = state.date;
  await loadPublicSettings().catch(() => {});
  try {
    const data = await api("/api/me");
    showDesk(data.user);
    showScreen("schedule");
    await loadState();
  } catch {
    showLogin();
  }
}

boot();
