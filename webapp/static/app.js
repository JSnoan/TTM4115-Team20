const BASE_POSITION = { lat: 63.42, lon: 10.39 };
const TRONDHEIM_CENTER = { lat: 63.4305, lon: 10.3951 };
const MIN_DISPATCH_BATTERY = 90;
const BASE_DOCKED_RADIUS_M = 5;
const PROCESS_EMERGENCY = "emergency_first_aid";
const PROCESS_ROUTINE = "routine_medicine";
const TRONDHEIM_BOUNDS = {
  minLat: 63.395,
  maxLat: 63.455,
  minLon: 10.33,
  maxLon: 10.45,
};

const stateCopy = {
  docked: "Docked at base. The drone can be dispatched when the battery guard allows it.",
  navigating: "Autonomous navigation is active. Watch the route progress and telemetry update.",
  manual_control: "Manual guidance is active after proximity alert.",
  waiting_onsite: "The drone is on site and waiting for mission completion.",
  returning: "The drone is returning to base.",
  unknown: "Waiting for telemetry from DroneClient.py.",
};

const latestUseCases = {
  emergency_requests: [],
  registrations: [],
  delivery_requests: [],
};
let latestStatus = {};
let latestEvents = [];
let lastPopupEventId = null;
let mapMode = "origin";
let emergencyLeafletMap = null;
let originLeafletMarker = null;
let destinationLeafletMarker = null;
let emergencyRoutePolyline = null;
let trackingLeafletMap = null;
let trackingBaseMarker = null;
let trackingTargetMarker = null;
let trackingDroneMarker = null;
let trackingRoutePolyline = null;
let trackingReturnPolyline = null;
let lastTrackingBoundsKey = "";
let selectedMissionOptionId = "";

const elements = {
  navTargets: [...document.querySelectorAll("[data-screen-target]")],
  screens: [...document.querySelectorAll(".screen")],
  feedback: document.querySelector("#feedback"),
  connection: document.querySelector("#connection"),
  state: document.querySelector("#state"),
  missionSummary: document.querySelector("#mission-summary"),
  activeMissionTitle: document.querySelector("#active-mission-title"),
  activeMissionSubtitle: document.querySelector("#active-mission-subtitle"),
  dashboardProgress: document.querySelector("#dashboard-progress"),
  battery: document.querySelector("#battery"),
  position: document.querySelector("#position"),
  target: document.querySelector("#target"),
  senseHat: document.querySelector("#sense-hat"),
  senseHatSource: document.querySelector("#sense-hat-source"),
  dispatchGuard: document.querySelector("#dispatch-guard"),
  mapRouteState: document.querySelector("#map-route-state"),
  statusAge: document.querySelector("#status-age"),
  chainMqtt: document.querySelector("#chain-mqtt"),
  chainPi: document.querySelector("#chain-pi"),
  chainTelemetry: document.querySelector("#chain-telemetry"),
  uc1Count: document.querySelector("#uc1-count"),
  uc2Count: document.querySelector("#uc2-count"),
  uc3Count: document.querySelector("#uc3-count"),
  targetLat: document.querySelector("#target-lat"),
  targetLon: document.querySelector("#target-lon"),
  speed: document.querySelector("#speed"),
  distanceTarget: document.querySelector("#distance-target"),
  distanceBase: document.querySelector("#distance-base"),
  trackingState: document.querySelector("#tracking-state"),
  trackingSubtitle: document.querySelector("#tracking-subtitle"),
  trackingBattery: document.querySelector("#tracking-battery"),
  journeyProgress: document.querySelector("#journey-progress"),
  journeyDrone: document.querySelector("#journey-drone"),
  routeStartLabel: document.querySelector("#route-start-label"),
  routeEndLabel: document.querySelector("#route-end-label"),
  trackingMap: document.querySelector("#tracking-map"),
  trackingMapLoading: document.querySelector("#tracking-map-loading"),
  trackingMapPopup: document.querySelector("#tracking-map-popup"),
  trackingPopupTitle: document.querySelector("#tracking-popup-title"),
  trackingPopupMessage: document.querySelector("#tracking-popup-message"),
  restrictedMapAlert: document.querySelector("#restricted-map-alert"),
  solveAlertComplete: document.querySelector("#solve-alert-complete"),
  solveAlertAbort: document.querySelector("#solve-alert-abort"),
  trackingMapOrigin: document.querySelector("#tracking-map-origin"),
  trackingMapDrone: document.querySelector("#tracking-map-drone"),
  trackingMapTarget: document.querySelector("#tracking-map-target"),
  rawStatus: document.querySelector("#raw-status"),
  events: document.querySelector("#events"),
  emergencyMap: document.querySelector("#emergency-map"),
  mapLoading: document.querySelector("#map-loading"),
  mapModeLabel: document.querySelector("#map-mode-label"),
  originLat: document.querySelector("#emergency-origin-lat"),
  originLon: document.querySelector("#emergency-origin-lon"),
  emergencyLat: document.querySelector("#emergency-lat"),
  emergencyLon: document.querySelector("#emergency-lon"),
  originReadout: document.querySelector("#origin-readout"),
  destinationReadout: document.querySelector("#destination-readout"),
  emergencyDistance: document.querySelector("#emergency-distance"),
  emergencyRequester: document.querySelector("#emergency-requester"),
  emergencyContact: document.querySelector("#emergency-contact"),
  emergencyNeed: document.querySelector("#emergency-need"),
  emergencyPriority: document.querySelector("#emergency-priority"),
  emergencyNotes: document.querySelector("#emergency-notes"),
  emergencySelect: document.querySelector("#emergency-select"),
  emergencyList: document.querySelector("#emergency-list"),
  createEmergency: document.querySelector("#create-emergency"),
  dispatchEmergency: document.querySelector("#dispatch-emergency"),
  registrationRequester: document.querySelector("#registration-requester"),
  registrationContact: document.querySelector("#registration-contact"),
  registrationPatientId: document.querySelector("#registration-patient-id"),
  registrationAddress: document.querySelector("#registration-address"),
  registrationMedicines: document.querySelector("#registration-medicines"),
  registrationLat: document.querySelector("#registration-lat"),
  registrationLon: document.querySelector("#registration-lon"),
  registrationContainer: document.querySelector("#registration-container"),
  registrationDropoffNotes: document.querySelector("#registration-dropoff-notes"),
  registrationList: document.querySelector("#registration-list"),
  registerRequester: document.querySelector("#register-requester"),
  deliveryRegistration: document.querySelector("#delivery-registration"),
  deliveryMedicine: document.querySelector("#delivery-medicine"),
  deliveryPriority: document.querySelector("#delivery-priority"),
  deliverySelect: document.querySelector("#delivery-select"),
  deliveryList: document.querySelector("#delivery-list"),
  createDelivery: document.querySelector("#create-delivery"),
  approveDelivery: document.querySelector("#approve-delivery"),
  dispatchDelivery: document.querySelector("#dispatch-delivery"),
  missionOrderSelect: document.querySelector("#mission-order-select"),
  missionOrderDetail: document.querySelector("#mission-order-detail"),
  processFlowCard: document.querySelector("#process-flow-card"),
  dispatchSelectedOrder: document.querySelector("#dispatch-selected-order"),
  missionActionHint: document.querySelector("#mission-action-hint"),
};

const commandButtons = [...document.querySelectorAll("[data-command]")];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function setText(element, value) {
  if (element) element.textContent = value;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeCoord(value) {
  if (Array.isArray(value) && value.length >= 2) {
    const lat = Number(value[0]);
    const lon = Number(value[1]);
    return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
  }

  if (value && typeof value === "object") {
    const lat = Number(value.lat);
    const lon = Number(value.lon);
    return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
  }

  return null;
}

function readCoord(latInput, lonInput) {
  if (!latInput || !lonInput) return null;
  const lat = Number(latInput.value);
  const lon = Number(lonInput.value);
  return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
}

function formatCoordPair(value) {
  const coord = normalizeCoord(value);
  if (!coord) return "-";
  return `${coord.lat.toFixed(6)}, ${coord.lon.toFixed(6)}`;
}

function formatMeters(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(1)} m`;
}

function distanceMeters(a, b) {
  if (!a || !b) return null;
  const earthRadius = 6371000;
  const lat1 = a.lat * Math.PI / 180;
  const lat2 = b.lat * Math.PI / 180;
  const deltaLat = (b.lat - a.lat) * Math.PI / 180;
  const deltaLon = (b.lon - a.lon) * Math.PI / 180;
  const haversine = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2) ** 2;
  return 2 * earthRadius * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

function assertNotBaseDestination(coord) {
  if (coord && distanceMeters(BASE_POSITION, coord) < 10) {
    throw new Error("Delivery destination cannot be the same as the base station");
  }
}

function distanceToBase(status = latestStatus) {
  const telemetryDistance = Number(status.telemetry?.distance_to_base_m);
  if (Number.isFinite(telemetryDistance)) return telemetryDistance;
  const pos = normalizeCoord(status.pos);
  return pos ? distanceMeters(pos, BASE_POSITION) : null;
}

function isDroneAtBase(status = latestStatus) {
  const distance = distanceToBase(status);
  return distance !== null && distance <= BASE_DOCKED_RADIUS_M;
}

function setMapMode(mode) {
  mapMode = mode === "origin" ? "destination" : mode;
  document.querySelectorAll("[data-map-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mapMode === mapMode);
  });
  setText(elements.mapModeLabel, "Picking destination");
}

function leafletLatLng(coord) {
  return [coord.lat, coord.lon];
}

function makeMapLabel(label, type) {
  return L.divIcon({
    className: "",
    html: `<div class="leaflet-marker-label ${type}">${label}</div>`,
    iconSize: [108, 42],
    iconAnchor: [54, 42],
  });
}

function makeTrackingPin(label, type) {
  return L.divIcon({
    className: "",
    html: `<div class="tracking-pin ${type}">${label}</div>`,
    iconSize: [76, 34],
    iconAnchor: [38, 34],
  });
}

function makeDroneIcon() {
  return L.divIcon({
    className: "",
    html: `
      <div class="tracking-drone-icon" aria-label="Drone">
        <svg viewBox="0 0 64 64" aria-hidden="true">
          <circle cx="14" cy="16" r="8"></circle>
          <circle cx="50" cy="16" r="8"></circle>
          <circle cx="14" cy="48" r="8"></circle>
          <circle cx="50" cy="48" r="8"></circle>
          <path d="M20 20 32 32 44 20M20 44l12-12 12 12"></path>
          <rect x="25" y="25" width="14" height="14" rx="4"></rect>
        </svg>
      </div>
    `,
    iconSize: [54, 54],
    iconAnchor: [27, 27],
  });
}

function initEmergencyMap() {
  if (emergencyLeafletMap || !elements.emergencyMap) return;

  if (!window.L) {
    if (elements.mapLoading) {
      elements.mapLoading.textContent = "Real map unavailable. Check internet access for Leaflet/OpenStreetMap.";
      elements.mapLoading.classList.add("error");
    }
    return;
  }

  updateBaseOriginInputs();
  const origin = BASE_POSITION;
  const destination = readCoord(elements.emergencyLat, elements.emergencyLon) || TRONDHEIM_CENTER;

  emergencyLeafletMap = L.map(elements.emergencyMap, {
    zoomControl: true,
    scrollWheelZoom: true,
  }).setView(leafletLatLng(TRONDHEIM_CENTER), 13);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(emergencyLeafletMap);

  originLeafletMarker = L.marker(leafletLatLng(origin), {
    draggable: false,
    icon: makeMapLabel("Base", "origin"),
  }).addTo(emergencyLeafletMap);

  destinationLeafletMarker = L.marker(leafletLatLng(destination), {
    draggable: true,
    icon: makeMapLabel("Destination", "destination"),
  }).addTo(emergencyLeafletMap);

  emergencyRoutePolyline = L.polyline([leafletLatLng(origin), leafletLatLng(destination)], {
    color: "#12aaa4",
    weight: 4,
    opacity: 0.9,
    dashArray: "8 8",
  }).addTo(emergencyLeafletMap);

  destinationLeafletMarker.on("dragend", () => {
    const point = destinationLeafletMarker.getLatLng();
    updateCoordInputs("destination", { lat: point.lat, lon: point.lng });
  });

  emergencyLeafletMap.on("click", (event) => {
    updateCoordInputs("destination", {
      lat: event.latlng.lat,
      lon: event.latlng.lng,
    });
  });

  elements.mapLoading?.remove();
  updateEmergencyMap();
}

function updateEmergencyMap() {
  updateBaseOriginInputs();
  const origin = BASE_POSITION;
  const destination = readCoord(elements.emergencyLat, elements.emergencyLon);

  setText(elements.originReadout, formatCoordPair(origin));
  setText(elements.destinationReadout, destination ? formatCoordPair(destination) : "-");
  setText(elements.emergencyDistance, destination ? formatMeters(distanceMeters(origin, destination)) : "-");

  if (emergencyLeafletMap && originLeafletMarker && destinationLeafletMarker && emergencyRoutePolyline && destination) {
    originLeafletMarker.setLatLng(leafletLatLng(origin));
    destinationLeafletMarker.setLatLng(leafletLatLng(destination));
    emergencyRoutePolyline.setLatLngs([leafletLatLng(origin), leafletLatLng(destination)]);
  }

  if (destination && elements.targetLat && elements.targetLon) {
    elements.targetLat.value = destination.lat.toFixed(6);
    elements.targetLon.value = destination.lon.toFixed(6);
  }
}

function updateCoordInputs(mode, coord) {
  if (mode === "origin") {
    updateBaseOriginInputs();
  } else {
    elements.emergencyLat.value = coord.lat.toFixed(6);
    elements.emergencyLon.value = coord.lon.toFixed(6);
  }
  updateEmergencyMap();
}

function updateBaseOriginInputs() {
  if (elements.originLat) elements.originLat.value = BASE_POSITION.lat.toFixed(6);
  if (elements.originLon) elements.originLon.value = BASE_POSITION.lon.toFixed(6);
}

function initTrackingMap() {
  if (trackingLeafletMap || !elements.trackingMap) return;

  if (!window.L) {
    if (elements.trackingMapLoading) {
      elements.trackingMapLoading.textContent = "Live map unavailable. Check internet access for Leaflet/OpenStreetMap.";
      elements.trackingMapLoading.classList.add("error");
    }
    return;
  }

  trackingLeafletMap = L.map(elements.trackingMap, {
    zoomControl: true,
    scrollWheelZoom: true,
  }).setView(leafletLatLng(TRONDHEIM_CENTER), 13);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(trackingLeafletMap);

  trackingBaseMarker = L.marker(leafletLatLng(BASE_POSITION), {
    icon: makeTrackingPin("Base", "base"),
  }).addTo(trackingLeafletMap);

  trackingTargetMarker = L.marker(leafletLatLng(readCoord(elements.targetLat, elements.targetLon) || TRONDHEIM_CENTER), {
    icon: makeTrackingPin("Drop", "target"),
  }).addTo(trackingLeafletMap);

  trackingDroneMarker = L.marker(leafletLatLng(BASE_POSITION), {
    icon: makeDroneIcon(),
    zIndexOffset: 700,
  }).addTo(trackingLeafletMap);

  trackingRoutePolyline = L.polyline([leafletLatLng(BASE_POSITION), leafletLatLng(TRONDHEIM_CENTER)], {
    color: "#12aaa4",
    weight: 5,
    opacity: 0.9,
  }).addTo(trackingLeafletMap);

  trackingReturnPolyline = L.polyline([], {
    color: "#f0a020",
    weight: 4,
    opacity: 0.9,
    dashArray: "8 10",
  }).addTo(trackingLeafletMap);

  elements.trackingMapLoading?.remove();
  updateTrackingMap(latestStatus);
}

function activeMissionFromStatus(status = latestStatus) {
  if (Object.prototype.hasOwnProperty.call(status, "active_mission")) {
    return status.active_mission || null;
  }
  return status.mission || null;
}

function trackingTarget(status) {
  const activeMission = activeMissionFromStatus(status);
  if (activeMission) {
    return normalizeCoord(status.target) || normalizeCoord(activeMission.target) || readCoord(elements.targetLat, elements.targetLon) || null;
  }

  const selectedOrder = selectedMissionOrder({ preferActive: false });
  return normalizeCoord(selectedOrder?.target) || readCoord(elements.targetLat, elements.targetLon) || normalizeCoord(status.target) || null;
}

function updateTrackingMap(status = {}) {
  setText(elements.trackingMapOrigin, formatCoordPair(BASE_POSITION));

  const target = trackingTarget(status);
  const dronePosition = normalizeCoord(status.pos) || BASE_POSITION;
  setText(elements.trackingMapDrone, formatCoordPair(dronePosition));
  setText(elements.trackingMapTarget, target ? formatCoordPair(target) : "-");

  if (!trackingLeafletMap || !trackingBaseMarker || !trackingTargetMarker || !trackingDroneMarker) {
    return;
  }

  trackingBaseMarker.setLatLng(leafletLatLng(BASE_POSITION));
  trackingDroneMarker.setLatLng(leafletLatLng(dronePosition));

  if (target) {
    trackingTargetMarker.setLatLng(leafletLatLng(target));
    trackingTargetMarker.addTo(trackingLeafletMap);
    trackingRoutePolyline.setLatLngs([leafletLatLng(BASE_POSITION), leafletLatLng(target)]);

    if (status.state === "returning") {
      trackingReturnPolyline.setLatLngs([leafletLatLng(dronePosition), leafletLatLng(BASE_POSITION)]);
    } else {
      trackingReturnPolyline.setLatLngs([]);
    }

    const boundsKey = `${target.lat.toFixed(5)}:${target.lon.toFixed(5)}`;

    if (boundsKey !== lastTrackingBoundsKey) {
      lastTrackingBoundsKey = boundsKey;
      const bounds = L.latLngBounds([
        leafletLatLng(BASE_POSITION),
        leafletLatLng(target),
        leafletLatLng(dronePosition),
      ]);
      trackingLeafletMap.fitBounds(bounds.pad(0.24), { animate: true, maxZoom: 15 });
    }
  } else {
    trackingTargetMarker.remove();
    trackingRoutePolyline.setLatLngs([]);
    trackingReturnPolyline.setLatLngs([]);
    trackingLeafletMap.setView(leafletLatLng(BASE_POSITION), 13);
  }
}

function activateScreen(screenName) {
  elements.screens.forEach((screen) => {
    screen.classList.toggle("active", screen.id === `screen-${screenName}`);
  });

  document.querySelectorAll("[data-screen-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.screenTarget === screenName);
  });

  if (screenName === "emergency") {
    requestAnimationFrame(() => {
      initEmergencyMap();
      emergencyLeafletMap?.invalidateSize();
      updateEmergencyMap();
    });
  }

  if (screenName === "tracking") {
    requestAnimationFrame(() => {
      initTrackingMap();
      trackingLeafletMap?.invalidateSize();
      updateTrackingMap(latestStatus);
      handlePopupEvents(latestEvents);
    });
  }
}

function showFeedback(message, kind = "ok") {
  if (!elements.feedback) return;
  elements.feedback.textContent = message;
  elements.feedback.dataset.kind = kind;
  window.clearTimeout(showFeedback.timeout);
  showFeedback.timeout = window.setTimeout(() => {
    elements.feedback.textContent = "";
    elements.feedback.removeAttribute("data-kind");
  }, 3600);
}

function showTrackingMapPopup(event) {
  if (!elements.trackingMapPopup) return;

  setText(elements.trackingPopupTitle, event.title || "Final approach reached");
  setText(
    elements.trackingPopupMessage,
    event.message || "Drone reached 99% of the route. Final guidance has started.",
  );

  elements.trackingMapPopup.dataset.kind = event.kind || "info";
  elements.trackingMapPopup.classList.add("active");
  window.clearTimeout(showTrackingMapPopup.timeout);
  showTrackingMapPopup.timeout = window.setTimeout(() => {
    elements.trackingMapPopup?.classList.remove("active");
  }, Number(event.duration_ms || 2000));
}

function handlePopupEvents(events) {
  const trackingScreen = document.querySelector("#screen-tracking");
  if (!trackingScreen?.classList.contains("active")) return;

  const now = Date.now();
  const popupEvent = events.find((event) => {
    if (!event.popup || event.id === lastPopupEventId) return false;
    if (!event.timestamp) return true;
    return now - Number(event.timestamp) * 1000 < 10000;
  });

  if (!popupEvent) return;

  lastPopupEventId = popupEvent.id;
  showTrackingMapPopup(popupEvent);
}

function activeMissionLabel() {
  const mission = activeMissionFromStatus(latestStatus);
  if (mission) {
    return {
      title: mission.label || "Active drone mission",
      subtitle: `${processLabel(mission.process_type)} · ${mission.phase || "active"}`,
    };
  }

  const emergencies = latestUseCases.emergency_requests || [];
  const deliveries = latestUseCases.delivery_requests || [];
  const activeEmergency = emergencies.slice().reverse().find((request) => request.status === "dispatched");
  const activeDelivery = deliveries.slice().reverse().find((delivery) => delivery.status === "dispatched");

  if (activeEmergency) {
    return {
      title: `Emergency aid to ${activeEmergency.requester}`,
      subtitle: `${activeEmergency.need} · ${formatCoordPair(activeEmergency.target)}`,
    };
  }
  if (activeDelivery) {
    return {
      title: `${activeDelivery.medicine} for ${activeDelivery.requester}`,
      subtitle: `Routine medicine delivery · ${formatCoordPair(activeDelivery.target)}`,
    };
  }
  if (latestStatus.state && !["unknown", "docked"].includes(latestStatus.state)) {
    return {
      title: "Direct MQTT drone mission",
      subtitle: `Current STMPY state: ${latestStatus.state}`,
    };
  }
  return {
    title: "Medical drone mission",
    subtitle: "No order dispatched yet",
  };
}

function missionAwareStateLabel(state, status = latestStatus) {
  const mission = activeMissionFromStatus(status);
  if (mission?.process_type === PROCESS_ROUTINE && mission?.phase === "restricted_alert") {
    return "restricted alert";
  }
  if (mission?.process_type === PROCESS_ROUTINE && mission?.phase === "delivering_medicine") {
    return "delivering medicine";
  }
  if (mission?.process_type === PROCESS_ROUTINE && mission?.phase === "dropping_medicine") {
    return "dropping medicine";
  }
  return (state || "unknown").replaceAll("_", " ");
}

function missionAwareStateCopy(state, status = latestStatus) {
  const mission = activeMissionFromStatus(status);
  if (mission?.process_type === PROCESS_ROUTINE && mission?.phase === "restricted_alert") {
    return "Restricted destination reached. Waiting for operator decision in the Solve Alert panel.";
  }
  if (mission?.process_type === PROCESS_ROUTINE && mission?.phase === "delivering_medicine") {
    return "Medicine package is being delivered automatically before the drone returns.";
  }
  if (mission?.process_type === PROCESS_ROUTINE && mission?.phase === "dropping_medicine") {
    return "Medicine package is being dropped after restricted-zone completion.";
  }
  return stateCopy[state] || stateCopy.unknown;
}

function processLabel(processType) {
  if (processType === PROCESS_EMERGENCY) return "Emergency First Aid";
  if (processType === PROCESS_ROUTINE) return "Routine Medicine";
  return "Mission";
}

function orderStatusAllowsDispatch(status) {
  return ["created", "queued", "approved"].includes(status);
}

function missionOrders() {
  const emergencyOrders = (latestUseCases.emergency_requests || []).map((order) => ({
    ...order,
    process_type: PROCESS_EMERGENCY,
    option_id: `${PROCESS_EMERGENCY}:${order.id}`,
    label: `Emergency #${order.id} · ${order.requester} · ${order.status}`,
  }));
  const routineOrders = (latestUseCases.delivery_requests || []).map((order) => ({
    ...order,
    process_type: PROCESS_ROUTINE,
    option_id: `${PROCESS_ROUTINE}:${order.id}`,
    label: `Routine #${order.id} · ${order.requester} · ${order.medicine} · ${order.status}`,
  }));
  return [...emergencyOrders, ...routineOrders];
}

function selectedMissionOrder(options = {}) {
  const preferActive = options.preferActive !== false;
  const selected = selectedMissionOptionId || elements.missionOrderSelect?.value;
  const orders = missionOrders();
  const activeMission = activeMissionFromStatus(latestStatus);
  const activeOrder = orders.find(
    (order) => order.process_type === activeMission?.process_type
      && Number(order.id) === Number(activeMission?.order_id),
  );
  if (preferActive && activeOrder) return activeOrder;
  return orders.find((order) => order.option_id === selected) || orders.find((order) => orderStatusAllowsDispatch(order.status)) || orders[0] || null;
}

function updateSelectedMissionTarget(order = selectedMissionOrder()) {
  const target = normalizeCoord(order?.target);
  if (!target) return;
  if (elements.targetLat) elements.targetLat.value = target.lat.toFixed(6);
  if (elements.targetLon) elements.targetLon.value = target.lon.toFixed(6);
  updateTrackingMap({ ...latestStatus, target });
}

function renderProcessFlow(order, activeMission = activeMissionFromStatus(latestStatus)) {
  if (!elements.processFlowCard) return;

  const processType = activeMission?.process_type || order?.process_type || "none";
  const restricted = Boolean(activeMission?.restricted_zone || order?.restricted_zone);
  elements.processFlowCard.dataset.process = processType;
  elements.processFlowCard.dataset.restricted = restricted ? "true" : "false";

  let label = "No mission selected";
  let title = "Create or select an order";
  let copy = "The available controls will adapt to the selected process.";

  if (processType === PROCESS_EMERGENCY) {
    label = restricted ? "Emergency First Aid · Restricted destination" : "Emergency First Aid";
    title = restricted ? "Restricted destination, emergency flow" : "Manual final approach";
    copy = restricted
      ? "A restricted-zone popup appears at arrival, then the emergency manual guidance flow continues."
      : "At arrival the drone enters manual guidance, then waits onsite until mission completion.";
  } else if (processType === PROCESS_ROUTINE) {
    label = restricted ? "Routine Medicine · Restricted destination" : "Routine Medicine";
    title = restricted ? "Operator resolution required" : "Automatic medicine delivery";
    copy = restricted
      ? "At arrival the drone enters manual control and the red Solve Alert panel decides complete or abort."
      : "At arrival the server shows Delivering medicine for 5 seconds, then sends the drone returning.";
  }

  elements.processFlowCard.innerHTML = `
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(title)}</strong>
    <small>${escapeHtml(copy)}</small>
  `;
}

function renderMissionOrderSelect() {
  if (!elements.missionOrderSelect) return;

  const orders = missionOrders();
  const previousValue = selectedMissionOptionId || elements.missionOrderSelect.value;
  elements.missionOrderSelect.innerHTML = "";

  if (!orders.length) {
    selectedMissionOptionId = "";
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No orders available";
    elements.missionOrderSelect.appendChild(option);
    setText(elements.missionOrderDetail, "Create an emergency or routine medicine order first.");
    return;
  }

  for (const order of orders) {
    const option = document.createElement("option");
    option.value = order.option_id;
    option.textContent = order.label;
    elements.missionOrderSelect.appendChild(option);
  }

  const activeMission = activeMissionFromStatus(latestStatus);
  const activeOrder = orders.find(
    (order) => order.process_type === activeMission?.process_type
      && Number(order.id) === Number(activeMission?.order_id),
  );
  const previousOrder = orders.find((order) => order.option_id === previousValue);
  const nextDispatchableOrder = orders.find((order) => orderStatusAllowsDispatch(order.status));
  const shouldMoveToNextDispatchable = !activeMission
    && latestStatus.state === "docked"
    && nextDispatchableOrder
    && (!previousOrder || !orderStatusAllowsDispatch(previousOrder.status));

  if (activeOrder) {
    elements.missionOrderSelect.value = activeOrder.option_id;
  } else if (shouldMoveToNextDispatchable) {
    elements.missionOrderSelect.value = nextDispatchableOrder.option_id;
  } else if ([...elements.missionOrderSelect.options].some((option) => option.value === previousValue)) {
    elements.missionOrderSelect.value = previousValue;
  } else {
    const preferred = nextDispatchableOrder || orders[0];
    elements.missionOrderSelect.value = preferred.option_id;
  }
  selectedMissionOptionId = elements.missionOrderSelect.value;

  const order = selectedMissionOrder();
  const restricted = order?.restricted_zone ? " · restricted destination" : "";
  setText(
    elements.missionOrderDetail,
    order
      ? `${processLabel(order.process_type)} · ${formatCoordPair(order.target)} · ${order.status}${restricted}`
      : "Create an emergency or routine medicine order first.",
  );
  renderProcessFlow(order);
  updateSelectedMissionTarget(order);
}

function renderMissionControls(status) {
  const order = selectedMissionOrder();
  const activeMission = activeMissionFromStatus(status);
  const state = status.state || "unknown";
  const allowed = status.allowed_commands || [];
  const batteryValue = status.battery === null || status.battery === undefined ? null : Number(status.battery);
  const showDispatch = Boolean(order)
    && orderStatusAllowsDispatch(order.status)
    && state === "docked"
    && !activeMission;
  const canDispatch = showDispatch && (batteryValue === null || batteryValue >= MIN_DISPATCH_BATTERY);

  if (elements.dispatchSelectedOrder) {
    elements.dispatchSelectedOrder.hidden = !showDispatch;
    elements.dispatchSelectedOrder.disabled = !canDispatch;
    elements.dispatchSelectedOrder.textContent = order
      ? `Dispatch ${processLabel(order.process_type)}`
      : "Dispatch Selected Order";
    elements.dispatchSelectedOrder.title = showDispatch && !canDispatch
      ? "Dispatch requires at least 90% battery"
      : "";
  }

  const routineActive = activeMission?.process_type === PROCESS_ROUTINE;
  const processType = activeMission?.process_type || order?.process_type || null;
  const phase = activeMission?.phase || "";
  const atBase = isDroneAtBase(status);
  const selectedRestricted = Boolean(activeMission?.restricted_zone || order?.restricted_zone);
  const restrictedRoutineAlert = routineActive
    && activeMission?.phase === "restricted_alert"
    && state === "manual_control";

  if (elements.restrictedMapAlert) {
    elements.restrictedMapAlert.hidden = !restrictedRoutineAlert;
  }
  renderProcessFlow(order, activeMission);

  const manualCompleteButton = document.querySelector("[data-command='manual_complete']");
  const manualAbortButton = document.querySelector("[data-command='manual_abort']");
  const missionCompleteButton = document.querySelector("[data-command='mission_complete']");
  const navAbortButton = document.querySelector("[data-command='nav_abort']");
  const dockedButton = document.querySelector("[data-command='successfully_docked']");

  const setCommandVisibility = (button, visible) => {
    if (!button) return false;
    button.hidden = !visible;
    if (visible) {
      button.disabled = !allowed.includes(button.dataset.command);
    }
    return visible;
  };

  const manualFlowItem = document.querySelector("[data-flow-state='manual_control']");
  if (manualFlowItem) {
    const strong = manualFlowItem.querySelector("strong");
    const small = manualFlowItem.querySelector("small");
    if (processType === PROCESS_ROUTINE && selectedRestricted) {
      setText(strong, "Restricted Alert");
      setText(small, "Solve alert");
    } else {
      setText(strong, "Manual Control");
      setText(small, "Dispatcher guidance");
    }
  }

  const visibleActions = [
    showDispatch,
    setCommandVisibility(navAbortButton, state === "navigating" && phase !== "delivering_medicine"),
    setCommandVisibility(
      manualCompleteButton,
      state === "manual_control" && processType !== PROCESS_ROUTINE,
    ),
    setCommandVisibility(
      manualAbortButton,
      state === "manual_control" && processType !== PROCESS_ROUTINE,
    ),
    setCommandVisibility(
      missionCompleteButton,
      state === "waiting_onsite" && processType !== PROCESS_ROUTINE,
    ),
    setCommandVisibility(dockedButton, state === "returning" && atBase),
  ].filter(Boolean).length;

  if (elements.missionActionHint) {
    elements.missionActionHint.hidden = visibleActions > 0;
    if (!visibleActions) {
      if (restrictedRoutineAlert) {
        elements.missionActionHint.textContent = "Use the restricted zone alert on the map to resolve this routine delivery.";
      } else if (state === "navigating" && phase === "delivering_medicine") {
        elements.missionActionHint.textContent = "Medicine delivery is being handled automatically by the mission server.";
      } else if (state === "returning" && !atBase) {
        const distance = distanceToBase(status);
        const distanceText = distance === null ? "unknown distance" : `${distance.toFixed(1)} m`;
        elements.missionActionHint.textContent = `Returning to base. Confirm Docked appears when the drone is at base (${distanceText} away).`;
      } else if (!order) {
        elements.missionActionHint.textContent = "Create an emergency or routine medicine order first.";
      } else {
        elements.missionActionHint.textContent = "No manual action is needed for this step.";
      }
    }
  }
}

function routeProgress(status) {
  const target = trackingTarget(status);
  const pos = normalizeCoord(status.pos) || BASE_POSITION;
  if (!target) return 0;
  const routeDistance = distanceMeters(BASE_POSITION, target) || 1;
  const travelled = distanceMeters(BASE_POSITION, pos) || 0;
  return clamp(travelled / routeDistance, 0, 1);
}

function updateJourney(status) {
  const progress = routeProgress(status);
  const pct = Math.round(progress * 100);
  const target = trackingTarget(status);
  const pos = normalizeCoord(status.pos);

  setText(elements.dashboardProgress, `${pct}%`);
  if (elements.journeyProgress) elements.journeyProgress.style.width = `${pct}%`;
  if (elements.journeyDrone) elements.journeyDrone.style.left = `${5 + progress * 90}%`;
  setText(elements.routeStartLabel, "Base station");
  setText(elements.routeEndLabel, target ? formatCoordPair(target) : "Destination");
  setText(
    elements.mapRouteState,
    target && pos ? `${formatMeters(distanceMeters(pos, target))} to target` : "No active route",
  );
  updateTrackingMap(status);
}

function updateCommunication(status) {
  elements.chainMqtt?.classList.toggle("active", Boolean(status.connected));
  elements.chainPi?.classList.toggle("active", Boolean(status.state && status.state !== "unknown"));
  elements.chainTelemetry?.classList.toggle("active", Boolean(status.telemetry && Object.keys(status.telemetry).length));
}

function renderStatus(status) {
  latestStatus = status;
  const state = status.state || "unknown";
  const telemetry = status.telemetry || {};
  const senseHat = status.sense_hat || {};
  const senseHatDisplay = status.sense_hat_display || {};
  const allowed = status.allowed_commands || [];
  const battery = status.battery === null || status.battery === undefined ? null : Number(status.battery);

  document.body.dataset.state = state;
  setText(
    elements.connection,
    status.connected
      ? `MQTT connected · last status ${status.last_status_age_s ?? "waiting"}s ago`
      : "MQTT disconnected",
  );
  setText(elements.state, missionAwareStateLabel(state, status));
  if (elements.state) elements.state.dataset.state = state;
  setText(elements.missionSummary, missionAwareStateCopy(state, status));
  setText(elements.battery, battery === null ? "-" : `${battery.toFixed(1)}%`);
  setText(elements.trackingBattery, battery === null ? "-" : `${battery.toFixed(1)}%`);
  setText(elements.position, formatCoordPair(status.pos));
  setText(elements.target, formatCoordPair(status.target));
  setText(elements.senseHat, senseHatDisplay.label || "Waiting for display mode");
  setText(
    elements.senseHatSource,
    `${senseHat.source || "unknown"} sensor / ${senseHatDisplay.source || "unknown"} display`,
  );
  setText(
    elements.dispatchGuard,
    battery === null
      ? "Waiting for battery"
      : battery >= MIN_DISPATCH_BATTERY
        ? "Ready: battery >= 90%"
        : "Blocked: battery below 90%",
  );
  setText(elements.statusAge, status.last_status_age_s === null ? "-" : `${status.last_status_age_s}s`);
  setText(elements.trackingState, missionAwareStateLabel(state, status));
  setText(elements.trackingSubtitle, missionAwareStateCopy(state, status));
  setText(
    elements.speed,
    telemetry.speed_mps === null || telemetry.speed_mps === undefined
      ? "-"
      : `${Number(telemetry.speed_mps).toFixed(1)} m/s`,
  );
  setText(elements.distanceTarget, formatMeters(telemetry.distance_to_target_m));
  setText(elements.distanceBase, formatMeters(telemetry.distance_to_base_m));

  const mission = activeMissionLabel();
  setText(elements.activeMissionTitle, mission.title);
  setText(elements.activeMissionSubtitle, mission.subtitle);

  if (elements.rawStatus) elements.rawStatus.textContent = JSON.stringify(status, null, 2);

  document.querySelectorAll("[data-flow-state]").forEach((item) => {
    item.classList.toggle("active", item.dataset.flowState === state);
  });

  commandButtons.forEach((button) => {
    const command = button.dataset.command;
    const batteryTooLow = command === "dispatch" && battery !== null && battery < MIN_DISPATCH_BATTERY;
    button.disabled = !allowed.includes(command) || batteryTooLow;
    button.title = batteryTooLow ? "Dispatch requires at least 90% battery" : "";
  });

  updateJourney(status);
  updateCommunication(status);
  renderMissionControls(status);
}

function renderRecord(container, records, emptyText, template) {
  if (!container) return;
  container.innerHTML = "";

  if (!records.length) {
    const empty = document.createElement("p");
    empty.className = "empty-list";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }

  for (const record of records.slice().reverse()) {
    const item = document.createElement("article");
    item.className = "record-item";
    item.innerHTML = template(record);
    container.appendChild(item);
  }
}

function setOptions(select, records, labelFn, emptyLabel = "None") {
  if (!select) return;
  const previousValue = select.value;
  select.innerHTML = "";

  if (!records.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = emptyLabel;
    select.appendChild(option);
    return;
  }

  for (const record of records) {
    const option = document.createElement("option");
    option.value = record.id;
    option.textContent = labelFn(record);
    select.appendChild(option);
  }

  if ([...select.options].some((option) => option.value === previousValue)) {
    select.value = previousValue;
  }
}

function renderUseCases(data) {
  latestUseCases.emergency_requests = data.emergency_requests || [];
  latestUseCases.registrations = data.registrations || [];
  latestUseCases.delivery_requests = data.delivery_requests || [];

  const emergencies = latestUseCases.emergency_requests;
  const registrations = latestUseCases.registrations;
  const deliveries = latestUseCases.delivery_requests;
  const validRegistrations = registrations.filter((registration) => registration.status === "registered");

  setText(elements.uc1Count, emergencies.length);
  setText(elements.uc3Count, validRegistrations.length);
  setText(elements.uc2Count, deliveries.length);

  setOptions(
    elements.emergencySelect,
    emergencies,
    (request) => `#${request.id} ${request.requester} · ${request.status}`,
    "No emergency requests",
  );

  setOptions(
    elements.deliveryRegistration,
    validRegistrations,
    (registration) => `#${registration.id} ${registration.requester}`,
    "No registered requesters",
  );

  const selectedRegistration = validRegistrations.find(
    (registration) => String(registration.id) === elements.deliveryRegistration?.value,
  ) || validRegistrations[0];
  const previousMedicine = elements.deliveryMedicine?.value;
  if (elements.deliveryMedicine) {
    elements.deliveryMedicine.innerHTML = "";
    const medicines = selectedRegistration?.approved_medicines || [];
    if (!medicines.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No approved medicines";
      elements.deliveryMedicine.appendChild(option);
    } else {
      for (const medicine of medicines) {
        const option = document.createElement("option");
        option.value = medicine;
        option.textContent = medicine;
        elements.deliveryMedicine.appendChild(option);
      }
    }
    if ([...elements.deliveryMedicine.options].some((option) => option.value === previousMedicine)) {
      elements.deliveryMedicine.value = previousMedicine;
    }
  }

  setOptions(
    elements.deliverySelect,
    deliveries,
    (delivery) => `#${delivery.id} ${delivery.requester} · ${delivery.medicine} · ${delivery.status}`,
    "No deliveries",
  );
  renderMissionOrderSelect();

  renderRecord(
    elements.emergencyList,
    emergencies,
    "No emergency requests yet.",
    (request) => `
      <div class="record-topline">
        <strong>#${request.id} ${escapeHtml(request.requester)}</strong>
        <span data-status="${escapeHtml(request.status)}">${escapeHtml(request.status)}</span>
      </div>
      <p>${escapeHtml(request.need)} · ${escapeHtml(request.priority || "urgent")}</p>
      <small>Base: ${formatCoordPair(request.origin)}</small>
      <small>Destination: ${formatCoordPair(request.target)}</small>
      <small>${request.restricted_zone ? "Restricted destination" : "Standard destination"}</small>
      <small>${escapeHtml(request.notes || "No notes")}</small>
    `,
  );

  renderRecord(
    elements.registrationList,
    registrations,
    "No registered requesters yet.",
    (registration) => `
      <div class="record-topline">
        <strong>#${registration.id} ${escapeHtml(registration.requester)}</strong>
        <span data-status="${escapeHtml(registration.status)}">${escapeHtml(registration.status)}</span>
      </div>
      <p>${escapeHtml(registration.address)}</p>
      <small>Approved: ${escapeHtml((registration.approved_medicines || []).join(", ") || "none")}</small>
      <small>Drop-off: ${formatCoordPair(registration.dropoff)}</small>
      <small>${registration.restricted_zone ? "Restricted destination" : "Standard destination"}</small>
    `,
  );

  renderRecord(
    elements.deliveryList,
    deliveries,
    "No routine deliveries queued yet.",
    (delivery) => `
      <div class="record-topline">
        <strong>#${delivery.id} ${escapeHtml(delivery.requester)}</strong>
        <span data-status="${escapeHtml(delivery.status)}">${escapeHtml(delivery.status)}</span>
      </div>
      <p>${escapeHtml(delivery.medicine)} · ${escapeHtml(delivery.priority || "standard")}</p>
      <small>Destination: ${formatCoordPair(delivery.target)}</small>
      <small>${delivery.restricted_zone ? "Restricted destination" : "Standard destination"}</small>
    `,
  );

  const mission = activeMissionLabel();
  setText(elements.activeMissionTitle, mission.title);
  setText(elements.activeMissionSubtitle, mission.subtitle);
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    renderStatus(await response.json());
  } catch (error) {
    setText(elements.connection, "Web server unreachable");
  }
}

async function refreshEvents() {
  try {
    const response = await fetch("/api/events");
    const data = await response.json();
    const events = data.events || [];
    latestEvents = events;
    elements.events.innerHTML = "";

    if (!events.length) {
      const item = document.createElement("li");
      item.textContent = "No MQTT events yet";
      elements.events.appendChild(item);
      return;
    }

    for (const event of events) {
      const item = document.createElement("li");
      item.innerHTML = `<span>${escapeHtml(event.time)}</span><strong>${escapeHtml(event.kind)}</strong>${escapeHtml(event.message)}`;
      elements.events.appendChild(item);
    }

    handlePopupEvents(events);
  } catch (error) {
    // Diagnostics can wait until the server is reachable.
  }
}

async function refreshUseCases() {
  const response = await fetch("/api/usecases");
  renderUseCases(await response.json());
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();

  if (!response.ok || !result.ok) {
    throw new Error(result.error || "Request failed");
  }

  return result;
}

async function runUseCaseAction(action, options = {}) {
  try {
    const result = await action();
    showFeedback(result.message || "Action completed", "ok");
    await refreshUseCases();
    await refreshStatus();
    await refreshEvents();
    if (options.screen) activateScreen(options.screen);
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

async function sendCommand(command) {
  const payload = { command };

  if (command === "dispatch") {
    payload.target = {
      lat: Number(elements.targetLat.value),
      lon: Number(elements.targetLon.value),
    };
  }

  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();

    if (!response.ok || !result.ok) {
      showFeedback(result.error || "Command failed", "error");
      return;
    }

    showFeedback(`Sent ${result.command}`, "ok");
    await refreshStatus();
    await refreshEvents();
  } catch (error) {
    showFeedback(error.message, "error");
  }
}

elements.navTargets.forEach((target) => {
  target.addEventListener("click", () => activateScreen(target.dataset.screenTarget));
});

commandButtons.forEach((button) => {
  button.addEventListener("click", () => sendCommand(button.dataset.command));
});

document.querySelectorAll("[data-map-mode]").forEach((button) => {
  button.addEventListener("click", () => setMapMode(button.dataset.mapMode));
});

[elements.originLat, elements.originLon, elements.emergencyLat, elements.emergencyLon].forEach((input) => {
  input?.addEventListener("input", updateEmergencyMap);
});

[elements.targetLat, elements.targetLon].forEach((input) => {
  input?.addEventListener("input", () => updateTrackingMap(latestStatus));
});

elements.missionOrderSelect?.addEventListener("change", () => {
  selectedMissionOptionId = elements.missionOrderSelect.value;
  const order = selectedMissionOrder({ preferActive: false });
  const restricted = order?.restricted_zone ? " · restricted destination" : "";
  setText(
    elements.missionOrderDetail,
    order
      ? `${processLabel(order.process_type)} · ${formatCoordPair(order.target)} · ${order.status}${restricted}`
      : "Create an emergency or routine medicine order first.",
  );
  renderProcessFlow(order);
  updateSelectedMissionTarget(order);
  renderMissionControls(latestStatus);
});

elements.createEmergency?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const destination = readCoord(elements.emergencyLat, elements.emergencyLon);
    assertNotBaseDestination(destination);
    const result = await postJson("/api/emergency", {
      requester: elements.emergencyRequester.value,
      contact: elements.emergencyContact.value,
      need: elements.emergencyNeed.value,
      priority: elements.emergencyPriority.value,
      origin_lat: elements.originLat.value,
      origin_lon: elements.originLon.value,
      lat: elements.emergencyLat.value,
      lon: elements.emergencyLon.value,
      notes: elements.emergencyNotes.value,
    });
    return { message: `Created emergency request #${result.request.id}` };
  });
});

elements.dispatchEmergency?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const id = elements.emergencySelect.value;
    if (!id) throw new Error("Select an emergency request first");
    await postJson(`/api/emergency/${id}/dispatch`);
    return { message: `Dispatched emergency request #${id}` };
  }, { screen: "tracking" });
});

elements.registerRequester?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const dropoff = readCoord(elements.registrationLat, elements.registrationLon);
    assertNotBaseDestination(dropoff);
    const result = await postJson("/api/register", {
      requester: elements.registrationRequester.value,
      contact: elements.registrationContact.value,
      patient_id: elements.registrationPatientId.value,
      address: elements.registrationAddress.value,
      medicines: elements.registrationMedicines.value,
      lat: elements.registrationLat.value,
      lon: elements.registrationLon.value,
      container: elements.registrationContainer.value,
      dropoff_notes: elements.registrationDropoffNotes.value,
    });
    return { message: `Registration #${result.registration.id}: ${result.registration.status}` };
  });
});

elements.deliveryRegistration?.addEventListener("change", () => {
  renderUseCases(latestUseCases);
});

elements.createDelivery?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const result = await postJson("/api/delivery", {
      registration_id: elements.deliveryRegistration.value,
      medicine: elements.deliveryMedicine.value,
      priority: elements.deliveryPriority.value,
    });
    return { message: `Queued delivery #${result.delivery.id}` };
  });
});

elements.approveDelivery?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const id = elements.deliverySelect.value;
    if (!id) throw new Error("Select a delivery first");
    await postJson(`/api/delivery/${id}/approve`);
    return { message: `Approved delivery #${id}` };
  });
});

elements.dispatchDelivery?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const id = elements.deliverySelect.value;
    if (!id) throw new Error("Select a delivery first");
    await postJson(`/api/delivery/${id}/dispatch`);
    return { message: `Dispatched delivery #${id}` };
  }, { screen: "tracking" });
});

elements.dispatchSelectedOrder?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    const order = selectedMissionOrder();
    if (!order) throw new Error("Select an order first");
    await postJson("/api/orders/dispatch", {
      process_type: order.process_type,
      order_id: order.id,
    });
    return { message: `Dispatched ${processLabel(order.process_type)} #${order.id}` };
  }, { screen: "tracking" });
});

elements.solveAlertComplete?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    await postJson("/api/restricted/solve", { decision: "complete" });
    return { message: "Restricted delivery completed" };
  }, { screen: "tracking" });
});

elements.solveAlertAbort?.addEventListener("click", () => {
  runUseCaseAction(async () => {
    await postJson("/api/restricted/solve", { decision: "abort" });
    return { message: "Restricted delivery aborted" };
  }, { screen: "tracking" });
});

setMapMode("destination");
updateBaseOriginInputs();
updateEmergencyMap();
refreshStatus();
refreshEvents();
refreshUseCases();
setInterval(refreshStatus, 1000);
setInterval(refreshEvents, 1500);
setInterval(refreshUseCases, 2500);
