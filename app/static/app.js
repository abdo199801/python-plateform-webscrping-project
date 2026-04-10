const statusEl = document.getElementById("status");
const profileStatusEl = document.getElementById("profileStatus");
const loginFormEl = document.getElementById("loginForm");
const authStateMessageEl = document.getElementById("authStateMessage");
const logoutBtnEl = document.getElementById("logoutBtn");
const runsEl = document.getElementById("runs");
const businessesEl = document.getElementById("businesses");
const leadSummaryEl = document.getElementById("leadSummary");
const leadFilterFormEl = document.getElementById("leadFilterForm");
const savedSearchNameEl = document.getElementById("savedSearchName");
const savedSearchesEl = document.getElementById("savedSearches");
const runFilterFormEl = document.getElementById("runFilterForm");
const runsPaginationEl = document.getElementById("runsPagination");
const businessesPaginationEl = document.getElementById("businessesPagination");
const businessExportsEl = document.getElementById("businessExports");
const formEl = document.getElementById("scrape-form");
const mapPreviewFrameEl = document.getElementById("mapPreviewFrame");
const mapPreviewTitleEl = document.getElementById("mapPreviewTitle");
const mapPreviewMetaEl = document.getElementById("mapPreviewMeta");
const openMapPreviewLinkEl = document.getElementById("openMapPreviewLink");
const refreshMapPreviewEl = document.getElementById("refreshMapPreview");
const profileFormEl = document.getElementById("profile-form");
const userCreditsEl = document.getElementById("userCredits");
const statusCreditsEl = document.getElementById("statusCredits");
const creditWarningEl = document.getElementById("creditWarning");
const creditDisplayEl = document.getElementById("creditDisplay");
const paymentBannerEl = document.getElementById("paymentBanner");
const insightCardsEl = document.getElementById("insightCards");
const topCategoriesEl = document.getElementById("topCategories");
const topCitiesEl = document.getElementById("topCities");
const recentRunsEl = document.getElementById("recentRuns");
const heroTotalBusinessesEl = document.getElementById("heroTotalBusinesses");
const heroSuccessRateEl = document.getElementById("heroSuccessRate");
const heroContactableEl = document.getElementById("heroContactable");
const heroTopSignalEl = document.getElementById("heroTopSignal");
const dashboardEmptyEl = document.getElementById("dashboardEmpty");
const dashboardContentEl = document.getElementById("dashboardContent");
const dashboardSummaryEl = document.getElementById("dashboardSummary");
const dashboardSubscriptionStatusEl = document.getElementById("dashboardSubscriptionStatus");
const dashboardPaymentsEl = document.getElementById("dashboardPayments");
const dashboardSubscriptionsEl = document.getElementById("dashboardSubscriptions");
const dashboardUpgradeProEl = document.getElementById("dashboardUpgradePro");
const dashboardUpgradeEnterpriseEl = document.getElementById("dashboardUpgradeEnterprise");
const dashboardCancelSubscriptionEl = document.getElementById("dashboardCancelSubscription");
const dashboardEditProfileEl = document.getElementById("dashboardEditProfile");
const scrapeButtonEl = document.getElementById("scrapeBtn");
const saveProfileButtonEl = document.getElementById("saveProfileBtn");
const appConfig = window.APP_CONFIG || {};
const apiBaseUrl = (appConfig.apiBaseUrl || "").replace(/\/+$/, "");
const googleMapsEmbedApiKey = (appConfig.googleMapsEmbedApiKey || "").trim();
const nativeFetch = window.fetch.bind(window);

function resolveApiUrl(input) {
  if (typeof input !== "string" || !input.startsWith("/") || !apiBaseUrl) {
    return input;
  }

  return `${apiBaseUrl}${input}`;
}

function syncAdminLinks() {
  document.querySelectorAll('a[href="/admin/login"]').forEach((link) => {
    link.setAttribute("href", resolveApiUrl("/admin/login"));
  });
}

window.fetch = (input, init = {}) => {
  const headers = new Headers(init.headers || {});
  if (authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  return nativeFetch(resolveApiUrl(input), { ...init, headers });
};

let userEmail = localStorage.getItem("userEmail") || "";
let authToken = localStorage.getItem("authToken") || "";
let paymentConfig = {
  payments_enabled: false,
  paypal_enabled: false,
  publishable_key: "",
  paypal_client_id: "",
  paypal_currency: "USD",
  paypal_environment: "sandbox",
  paypal_sdk_base: "https://www.paypal.com/sdk/js",
  trial_days: 15,
};
let accessState = null;
const runListState = { page: 1, pageSize: 6 };
const runFiltersState = { search: "", status: "" };
const DEFAULT_MAX_RESULTS_PER_SCRAPE = 500;
const ENTERPRISE_MAX_RESULTS_PER_SCRAPE = 1000;
const businessListState = {
  page: 1,
  pageSize: 10,
  search: "",
  city: "",
  country: "",
  category: "",
  leadStatus: "",
  tag: "",
  savedOnly: false,
  scrapeRunId: null,
};
let latestRunId = null;
let dashboardState = null;
let savedSearchesState = [];
let scrapeMonitorTimer = null;
let hasInitializedRunStatuses = false;
const runStatusMap = new Map();
let runClockTimer = null;

const LEAD_STATUS_OPTIONS = ["new", "contacted", "qualified", "proposal", "won", "lost"];

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#a02b2b" : "";
}

function setProfileStatus(message, isError = false) {
  profileStatusEl.textContent = message;
  profileStatusEl.style.color = isError ? "#a02b2b" : "";
}

function setAuthStateMessage(message, isError = false) {
  authStateMessageEl.textContent = message;
  authStateMessageEl.style.color = isError ? "#a02b2b" : "";
}

async function ensureNotificationPermission() {
  if (!("Notification" in window)) {
    return "unsupported";
  }

  if (Notification.permission === "granted" || Notification.permission === "denied") {
    return Notification.permission;
  }

  try {
    return await Notification.requestPermission();
  } catch {
    return "default";
  }
}

function showBrowserNotification(title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") {
    return;
  }

  try {
    new Notification(title, { body, tag: "scrape-run-status" });
  } catch {
    // Ignore notification errors and keep the in-app status message as fallback.
  }
}

function startScrapeMonitor() {
  if (scrapeMonitorTimer) {
    return;
  }

  scrapeMonitorTimer = window.setInterval(async () => {
    try {
      await loadRuns();
    } catch {
      // Ignore polling errors to avoid spamming the status area.
    }
  }, 10000);
}

function stopScrapeMonitor() {
  if (!scrapeMonitorTimer) {
    return;
  }

  window.clearInterval(scrapeMonitorTimer);
  scrapeMonitorTimer = null;
}

function startRunClock() {
  if (runClockTimer) {
    return;
  }

  runClockTimer = window.setInterval(() => {
    refreshRunTimers();
  }, 1000);
}

function stopRunClock() {
  if (!runClockTimer) {
    return;
  }

  window.clearInterval(runClockTimer);
  runClockTimer = null;
}

function formatDuration(totalSeconds) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  if (minutes <= 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

function estimateRunDurationSeconds(run) {
  const requestedResults = Number(run.max_results || 0);
  const baseSeconds = 35;
  const perResultSeconds = 2.4;
  return Math.max(60, Math.min(1800, Math.round(baseSeconds + requestedResults * perResultSeconds)));
}

function getRunTiming(run) {
  const createdAtMs = new Date(run.created_at).getTime();
  const elapsedSeconds = Number.isFinite(createdAtMs)
    ? Math.max(0, Math.floor((Date.now() - createdAtMs) / 1000))
    : 0;
  const estimatedTotalSeconds = estimateRunDurationSeconds(run);
  const remainingSeconds = Math.max(0, estimatedTotalSeconds - elapsedSeconds);

  return {
    elapsedSeconds,
    estimatedTotalSeconds,
    remainingSeconds,
  };
}

function getRunProgressMeta(run) {
  const status = String(run.status || "queued").toLowerCase();
  if (status !== "queued" && status !== "running") {
    return null;
  }

  const timing = getRunTiming(run);
  const statusLabel = status === "running" ? "Running" : "Queued";
  const processedResults = Number(run.processed_results || 0);
  const requestedResults = Math.max(1, Number(run.max_results || 0));
  const progressPercent = status === "queued"
    ? 0
    : Math.max(2, Math.min(100, Math.round((processedResults / requestedResults) * 100)));
  const etaLabel = status === "queued"
    ? "Estimated time left: waiting for an available scraper slot"
    : timing.remainingSeconds > 0
      ? `Estimated time left: ${formatDuration(timing.remainingSeconds)}`
      : "Estimated time left: finishing up";

  return {
    statusLabel,
    targetLabel: `Target: up to ${formatNumber(run.max_results)} businesses`,
    downloadedLabel: `Downloaded: ${formatNumber(processedResults)} of ${formatNumber(run.max_results)} businesses`,
    timerLabel: `Elapsed: ${formatDuration(timing.elapsedSeconds)}`,
    etaLabel,
    progressPercent,
    progressMessage: run.progress_message || (status === "queued" ? "Waiting in queue..." : "Collecting businesses from Google Maps..."),
  };
}

function refreshRunTimers() {
  const timedCards = runsEl.querySelectorAll(".run-card[data-run-status]");
  let hasActiveTimedRun = false;

  timedCards.forEach((card) => {
    const status = (card.dataset.runStatus || "").toLowerCase();
    if (status !== "queued" && status !== "running") {
      return;
    }

    hasActiveTimedRun = true;
    const run = {
      status,
      created_at: card.dataset.createdAt,
      max_results: Number(card.dataset.maxResults || 0),
      processed_results: Number(card.dataset.processedResults || 0),
      progress_message: card.dataset.progressMessage || "",
    };
    const meta = getRunProgressMeta(run);
    if (!meta) {
      return;
    }

    const timerEl = card.querySelector("[data-role='run-timer']");
    const etaEl = card.querySelector("[data-role='run-eta']");
    if (timerEl) {
      timerEl.textContent = meta.timerLabel;
    }
    if (etaEl) {
      etaEl.textContent = meta.etaLabel;
    }
    const progressFillEl = card.querySelector("[data-role='run-progress-fill']");
    const downloadedEl = card.querySelector("[data-role='run-downloaded']");
    const messageEl = card.querySelector("[data-role='run-progress-message']");
    if (progressFillEl) {
      progressFillEl.style.width = `${meta.progressPercent}%`;
    }
    if (downloadedEl) {
      downloadedEl.textContent = meta.downloadedLabel;
    }
    if (messageEl) {
      messageEl.textContent = meta.progressMessage;
    }
  });

  if (!hasActiveTimedRun) {
    stopRunClock();
  }
}

function updateRunNotifications(runs) {
  const hasActiveRuns = runs.some((run) => ["queued", "running"].includes(String(run.status || "").toLowerCase()));

  if (!hasInitializedRunStatuses) {
    runs.forEach((run) => {
      runStatusMap.set(run.id, run.status);
    });
    hasInitializedRunStatuses = true;
    if (hasActiveRuns) {
      startScrapeMonitor();
      startRunClock();
    }
    return;
  }

  runs.forEach((run) => {
    const previousStatus = runStatusMap.get(run.id);
    runStatusMap.set(run.id, run.status);

    if (!previousStatus || previousStatus === run.status) {
      return;
    }

    if (["queued", "running"].includes(previousStatus) && run.status === "completed") {
      const message = `${run.keyword} finished with ${formatNumber(run.total_results)} saved businesses.`;
      setStatus(message);
      showBrowserNotification("Scrape completed", message);
      return;
    }

    if (["queued", "running"].includes(previousStatus) && run.status === "failed") {
      const reason = run.error_message || "Refresh runs for the latest status.";
      const message = `${run.keyword} failed during scraping. ${reason}`;
      setStatus(message, true);
      showBrowserNotification("Scrape failed", message);
    }
  });

  if (hasActiveRuns) {
    startScrapeMonitor();
    startRunClock();
  } else {
    stopScrapeMonitor();
    stopRunClock();
  }
}

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

async function readJsonResponse(response) {
  const raw = await response.text();
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(`Server returned an invalid response (${response.status}).`);
  }
}

function formatStatusLabel(value) {
  if (!value) {
    return "Unassigned";
  }

  return value.charAt(0).toUpperCase() + value.slice(1);
}

function buildMapQuery(keyword, location) {
  return [keyword, location]
    .map((value) => (value || "").trim())
    .filter(Boolean)
    .join(" ");
}

function buildGoogleMapsUrl(keyword, location) {
  const query = buildMapQuery(keyword, location) || "Google Maps";
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function buildGoogleMapsEmbedUrl(keyword, location) {
  const query = buildMapQuery(keyword, location) || "Google Maps";
  if (googleMapsEmbedApiKey) {
    return `https://www.google.com/maps/embed/v1/search?key=${encodeURIComponent(googleMapsEmbedApiKey)}&q=${encodeURIComponent(query)}`;
  }
  return `https://maps.google.com/maps?q=${encodeURIComponent(query)}&output=embed`;
}

function updateMapPreview(keyword, location) {
  if (!mapPreviewFrameEl || !mapPreviewTitleEl || !mapPreviewMetaEl || !openMapPreviewLinkEl) {
    return;
  }

  const cleanKeyword = (keyword || "").trim();
  const cleanLocation = (location || "").trim();
  const query = buildMapQuery(cleanKeyword, cleanLocation);

  mapPreviewTitleEl.textContent = query || "Live Search Preview";
  mapPreviewMetaEl.textContent = query
    ? `Previewing Google Maps for ${query}. Use this card to validate the target area before or during scraping.`
    : "Type a keyword and location to preview the map inside the platform.";
  mapPreviewFrameEl.src = buildGoogleMapsEmbedUrl(cleanKeyword, cleanLocation);
  openMapPreviewLinkEl.href = buildGoogleMapsUrl(cleanKeyword, cleanLocation);
}

function previewRunMap(keyword, location) {
  updateMapPreview(keyword, location);
  document.getElementById("scraper").scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildBusinessQueryString() {
  const params = new URLSearchParams({
    page: String(businessListState.page),
    page_size: String(businessListState.pageSize),
  });

  if (userEmail) {
    params.set("email", userEmail);
  }
  if (businessListState.search) {
    params.set("search", businessListState.search);
  }
  if (businessListState.city) {
    params.set("city", businessListState.city);
  }
  if (businessListState.country) {
    params.set("country", businessListState.country);
  }
  if (businessListState.category) {
    params.set("category", businessListState.category);
  }
  if (businessListState.leadStatus) {
    params.set("lead_status", businessListState.leadStatus);
  }
  if (businessListState.tag) {
    params.set("tag", businessListState.tag);
  }
  if (businessListState.savedOnly) {
    params.set("saved_only", "true");
  }
  if (businessListState.scrapeRunId) {
    params.set("scrape_run_id", String(businessListState.scrapeRunId));
  }

  return params.toString();
}

function buildBusinessExportQueryString() {
  const params = new URLSearchParams();

  if (userEmail) {
    params.set("email", userEmail);
  }
  if (businessListState.search) {
    params.set("search", businessListState.search);
  }
  if (businessListState.city) {
    params.set("city", businessListState.city);
  }
  if (businessListState.country) {
    params.set("country", businessListState.country);
  }
  if (businessListState.category) {
    params.set("category", businessListState.category);
  }
  if (businessListState.leadStatus) {
    params.set("lead_status", businessListState.leadStatus);
  }
  if (businessListState.tag) {
    params.set("tag", businessListState.tag);
  }
  if (businessListState.savedOnly) {
    params.set("saved_only", "true");
  }
  if (businessListState.scrapeRunId) {
    params.set("scrape_run_id", String(businessListState.scrapeRunId));
  }

  return params.toString();
}

function syncRunFilterForm() {
  if (!runFilterFormEl) {
    return;
  }

  runFilterFormEl.elements.search.value = runFiltersState.search;
  runFilterFormEl.elements.status.value = runFiltersState.status;
}

function getRunFilterPayload() {
  const data = new FormData(runFilterFormEl);
  return {
    search: (data.get("search") || "").toString().trim(),
    status: (data.get("status") || "").toString().trim(),
  };
}

function updateRunFilterState(nextState = {}) {
  runFiltersState.search = nextState.search || "";
  runFiltersState.status = nextState.status || "";
}

function syncLeadFilterForm() {
  if (!leadFilterFormEl) {
    return;
  }

  leadFilterFormEl.elements.search.value = businessListState.search;
  leadFilterFormEl.elements.city.value = businessListState.city;
  leadFilterFormEl.elements.country.value = businessListState.country;
  leadFilterFormEl.elements.category.value = businessListState.category;
  leadFilterFormEl.elements.lead_status.value = businessListState.leadStatus;
  leadFilterFormEl.elements.tag.value = businessListState.tag;
  leadFilterFormEl.elements.saved_only.checked = businessListState.savedOnly;
}

function getLeadFilterPayload() {
  const data = new FormData(leadFilterFormEl);
  return {
    search: (data.get("search") || "").toString().trim(),
    city: (data.get("city") || "").toString().trim(),
    country: (data.get("country") || "").toString().trim(),
    category: (data.get("category") || "").toString().trim(),
    leadStatus: (data.get("lead_status") || "").toString().trim(),
    tag: (data.get("tag") || "").toString().trim(),
    savedOnly: data.get("saved_only") === "on",
  };
}

function updateLeadFilterState(nextState = {}) {
  businessListState.search = nextState.search || "";
  businessListState.city = nextState.city || "";
  businessListState.country = nextState.country || "";
  businessListState.category = nextState.category || "";
  businessListState.leadStatus = nextState.leadStatus || "";
  businessListState.tag = nextState.tag || "";
  businessListState.savedOnly = Boolean(nextState.savedOnly);
}

function formatRelativeDayLabel(value) {
  if (!value) {
    return "No activity yet";
  }

  return new Date(value).toLocaleDateString();
}

function setPaymentBanner(message, tone) {
  if (!message) {
    paymentBannerEl.style.display = "none";
    paymentBannerEl.textContent = "";
    paymentBannerEl.dataset.tone = "";
    return;
  }

  paymentBannerEl.style.display = "block";
  paymentBannerEl.textContent = message;
  paymentBannerEl.dataset.tone = tone || "info";
}

function syncEmailFields(email) {
  userEmail = email.trim();
  if (userEmail) {
    localStorage.setItem("userEmail", userEmail);
  } else {
    localStorage.removeItem("userEmail");
  }
  const scrapeEmailField = formEl.querySelector('input[name="email"]');
  const profileEmailField = profileFormEl.querySelector('input[name="email"]');
  const loginEmailField = loginFormEl.querySelector('input[name="email"]');
  scrapeEmailField.value = userEmail;
  profileEmailField.value = userEmail;
  loginEmailField.value = userEmail;
}

function getProfilePayload() {
  const data = new FormData(profileFormEl);
  return {
    full_name: (data.get("full_name") || "").toString().trim(),
    company_name: (data.get("company_name") || "").toString().trim(),
    email: (data.get("email") || "").toString().trim(),
    phone: (data.get("phone") || "").toString().trim(),
    country: (data.get("country") || "").toString().trim(),
    preferred_payment_provider: data.get("preferred_payment_provider") || "card",
    password: (data.get("password") || "").toString(),
    confirm_password: (data.get("confirm_password") || "").toString(),
  };
}

function validateProfilePayload(payload) {
  return payload.full_name && payload.company_name && payload.email && payload.phone;
}

function updateAuthUi(user = null) {
  const passwordField = profileFormEl.querySelector('input[name="password"]');
  const confirmPasswordField = profileFormEl.querySelector('input[name="confirm_password"]');
  const passwordLabel = passwordField.closest("label");
  const confirmPasswordLabel = confirmPasswordField.closest("label");
  const profileEmailField = profileFormEl.querySelector('input[name="email"]');

  const authenticated = Boolean(user && authToken);
  loginFormEl.hidden = authenticated;
  logoutBtnEl.disabled = !authenticated;
  passwordLabel.hidden = authenticated;
  confirmPasswordLabel.hidden = authenticated;
  passwordField.required = !authenticated;
  confirmPasswordField.required = !authenticated;
  profileEmailField.readOnly = authenticated;
  profileEmailField.classList.toggle("readonly-field", authenticated);
  saveProfileButtonEl.textContent = authenticated ? "Save Profile" : "Create Account & Start Trial";

  if (authenticated) {
    setAuthStateMessage(`Signed in as ${user.email}. Your private dashboard and lead data are now scoped to this account.`);
  } else {
    setAuthStateMessage("No active customer session.");
  }
}

function setAuthSession(token, user) {
  authToken = token;
  localStorage.setItem("authToken", token);
  syncEmailFields(user.email);
  populateProfileForm(user);
  updateAuthUi(user);
}

function clearAuthSession() {
  authToken = "";
  accessState = null;
  dashboardState = null;
  localStorage.removeItem("authToken");
  syncEmailFields("");
  updateAccessDisplay();
  updateAuthUi(null);
  renderDashboardEmpty("Sign in to unlock your private dashboard and self-service subscription controls.");
  renderLeadSummary({ total: 0, active: 0, archived: 0, counts: {} });
  renderSavedSearches([]);
}

async function restoreSession() {
  if (!authToken) {
    clearAuthSession();
    return null;
  }

  const response = await fetch("/api/auth/me");
  if (!response.ok) {
    clearAuthSession();
    throw new Error("Your session expired. Please log in again.");
  }

  const user = await response.json();
  syncEmailFields(user.email);
  populateProfileForm(user);
  updateAuthUi(user);
  return user;
}

async function loginUserAccount(email, password) {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Login failed");
  }

  setAuthSession(data.access_token, data.user);
  return data.user;
}

function updateAccessDisplay() {
  const daysLeft = accessState ? accessState.trial_days_left : 0;
  statusCreditsEl.textContent = daysLeft;
  const maxResultsField = formEl.querySelector('input[name="max_results"]');

  if (!accessState) {
    creditDisplayEl.innerHTML = `<span class="credit-icon">⏳</span><span id="userCredits">0</span> trial days left`;
    creditWarningEl.style.display = "none";
    creditDisplayEl.style.opacity = "0.6";
    maxResultsField.max = String(DEFAULT_MAX_RESULTS_PER_SCRAPE);
    return;
  }

  if (accessState.has_active_subscription) {
    userCreditsEl.textContent = accessState.subscription_tier.toUpperCase();
    creditDisplayEl.innerHTML = `<span class="credit-icon">✓</span><span id="userCredits">${escapeHtml(accessState.subscription_tier.toUpperCase())}</span> active`;
    creditWarningEl.style.display = "none";
    statusCreditsEl.textContent = accessState.trial_days_left;
    creditDisplayEl.style.opacity = "1";
    maxResultsField.max = accessState.subscription_tier === "enterprise"
      ? String(ENTERPRISE_MAX_RESULTS_PER_SCRAPE)
      : String(DEFAULT_MAX_RESULTS_PER_SCRAPE);
    return;
  }

  creditDisplayEl.innerHTML = `<span class="credit-icon">⏳</span><span id="userCredits">${daysLeft}</span> trial days left`;
  creditWarningEl.style.display = accessState.requires_subscription ? "block" : "none";
  creditDisplayEl.style.opacity = accessState.can_scrape ? "1" : "0.75";
  maxResultsField.max = String(DEFAULT_MAX_RESULTS_PER_SCRAPE);
}

function renderSignalList(container, items, emptyMessage, formatter) {
  if (!items.length) {
    container.innerHTML = `<p class="signal-empty">${escapeHtml(emptyMessage)}</p>`;
    return;
  }

  container.innerHTML = items.map(formatter).join("");
}

function renderPagination(container, state, onPageChange) {
  if (!state || state.total_pages <= 1) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <button type="button" class="secondary" ${state.page <= 1 ? "disabled" : ""} data-page="prev">Previous</button>
    <span class="pagination-summary">Page ${state.page} of ${state.total_pages} • ${formatNumber(state.total)} total</span>
    <button type="button" class="secondary" ${state.page >= state.total_pages ? "disabled" : ""} data-page="next">Next</button>
  `;

  container.querySelectorAll("button[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = button.dataset.page === "prev" ? state.page - 1 : state.page + 1;
      onPageChange(nextPage);
    });
  });
}

function buildExportButtons(runId, variant = "inline") {
  if (!runId) {
    return `
      <button type="button" class="secondary export-button ${variant}" disabled>Excel</button>
      <button type="button" class="secondary export-button ${variant}" disabled>CSV</button>
      <button type="button" class="secondary export-button ${variant}" disabled>PDF</button>
    `;
  }

  return ["xlsx", "csv", "pdf"]
    .map((format) => {
      const label = format === "xlsx" ? "Excel" : format.toUpperCase();
      return `
        <a class="secondary export-button ${variant}" href="/api/scrapes/${runId}/exports/${format}" download>
          Download ${label}
        </a>
      `;
    })
    .join("");
}

function countContactableBusinesses(run) {
  const businesses = Array.isArray(run.businesses) ? run.businesses : [];
  return businesses.filter((business) => business.phone || business.email || business.website).length;
}

function getRunSummaryLabel(run) {
  const businesses = Array.isArray(run.businesses) ? run.businesses : [];
  if (!businesses.length) {
    return "No businesses stored yet";
  }

  const contactable = countContactableBusinesses(run);
  return `${formatNumber(businesses.length)} businesses stored • ${formatNumber(contactable)} with contact details`;
}

function fillScrapeFormFromRun(run) {
  formEl.querySelector('input[name="keyword"]').value = run.keyword || "";
  formEl.querySelector('input[name="location"]').value = run.location || "";
  formEl.querySelector('input[name="radius"]').value = run.radius || "10000";
  formEl.querySelector('input[name="max_results"]').value = String(run.max_results || 25);
  formEl.querySelector('input[name="headless"]').checked = Boolean(run.headless);
  formEl.querySelector('input[name="email"]').value = userEmail || formEl.querySelector('input[name="email"]').value;
  updateMapPreview(run.keyword || "", run.location || "");
}

async function focusBusinessesForRun(run) {
  businessListState.scrapeRunId = run.id;
  businessListState.page = 1;
  await loadBusinesses();
  document.getElementById("businesses").scrollIntoView({ behavior: "smooth", block: "start" });
  setStatus(`Showing businesses from run #${run.id}: ${run.keyword}.`);
}

async function deleteRun(runId) {
  const confirmed = window.confirm("Delete this saved run and all businesses attached to it?");
  if (!confirmed) {
    return;
  }

  const response = await fetch(`/api/scrapes/${runId}`, { method: "DELETE" });
  const data = await readJsonResponse(response);
  if (!response.ok) {
    throw new Error(data?.detail || "Failed to delete scrape run");
  }

  if (businessListState.scrapeRunId === runId) {
    businessListState.scrapeRunId = null;
  }
}

function buildAllDataExportButtons(variant = "toolbar") {
  const queryString = buildBusinessExportQueryString();

  return ["xlsx", "csv", "pdf"]
    .map((format) => {
      const label = format === "xlsx" ? "All Data Excel" : `All Data ${format.toUpperCase()}`;
      const href = `/api/businesses/exports/${format}${queryString ? `?${queryString}` : ""}`;
      return `
        <a class="secondary export-button ${variant}" href="${escapeHtml(href)}" download>
          ${escapeHtml(label)}
        </a>
      `;
    })
    .join("");
}

function renderBusinessExportToolbar() {
  businessExportsEl.innerHTML = `
    <div class="export-group">
      <span class="export-group-label">Latest run</span>
      ${buildExportButtons(latestRunId, "toolbar")}
    </div>
    <div class="export-group">
      <span class="export-group-label">All matching data</span>
      ${buildAllDataExportButtons("toolbar")}
    </div>
  `;
}

function populateProfileForm(profile) {
  if (!profile) {
    return;
  }

  profileFormEl.querySelector('input[name="full_name"]').value = profile.full_name || "";
  profileFormEl.querySelector('input[name="company_name"]').value = profile.company_name || "";
  profileFormEl.querySelector('input[name="email"]').value = profile.email || "";
  profileFormEl.querySelector('input[name="phone"]').value = profile.phone || "";
  profileFormEl.querySelector('input[name="country"]').value = profile.country || "";
  profileFormEl.querySelector('select[name="preferred_payment_provider"]').value = profile.preferred_payment_provider || "card";
}

function renderDashboardEmpty(message) {
  dashboardState = null;
  dashboardEmptyEl.hidden = false;
  dashboardEmptyEl.textContent = message;
  dashboardContentEl.hidden = true;
  dashboardSummaryEl.innerHTML = "";
  dashboardSubscriptionStatusEl.textContent = "";
  dashboardPaymentsEl.innerHTML = "";
  dashboardSubscriptionsEl.innerHTML = "";
  dashboardUpgradeProEl.disabled = true;
  dashboardUpgradeEnterpriseEl.disabled = true;
  dashboardCancelSubscriptionEl.disabled = true;
}

function renderDashboard(data) {
  dashboardState = data;
  populateProfileForm(data.profile);
  syncEmailFields(data.profile.email);

  dashboardEmptyEl.hidden = true;
  dashboardContentEl.hidden = false;

  const currentTier = data.current_subscription?.tier || (data.access.trial_active ? "trial" : "none");
  dashboardSummaryEl.innerHTML = `
    <article class="dashboard-metric">
      <span>Current Access</span>
      <strong>${escapeHtml(String(currentTier).toUpperCase())}</strong>
      <small>${data.access.has_active_subscription ? "Subscription active" : `${data.access.trial_days_left} trial days left`}</small>
    </article>
    <article class="dashboard-metric">
      <span>Total Scrapes</span>
      <strong>${formatNumber(data.activity.total_scrapes)}</strong>
      <small>Tracked on your account</small>
    </article>
    <article class="dashboard-metric">
      <span>Last Activity</span>
      <strong>${escapeHtml(formatRelativeDayLabel(data.activity.last_scrape_at))}</strong>
      <small>${escapeHtml(formatDate(data.activity.last_scrape_at))}</small>
    </article>
    <article class="dashboard-metric">
      <span>Member Since</span>
      <strong>${escapeHtml(new Date(data.activity.member_since).toLocaleDateString())}</strong>
      <small>${escapeHtml(data.profile.company_name)}</small>
    </article>
  `;

  if (data.current_subscription) {
    const subscription = data.current_subscription;
    dashboardSubscriptionStatusEl.textContent = subscription.cancel_at_period_end
      ? `Your ${subscription.tier.toUpperCase()} plan is set to end on ${formatDate(subscription.current_period_end)}.`
      : `Your ${subscription.tier.toUpperCase()} plan is active${subscription.current_period_end ? ` until ${formatDate(subscription.current_period_end)}` : ""}.`;
  } else if (data.access.trial_active) {
    dashboardSubscriptionStatusEl.textContent = `Free trial active with ${data.access.trial_days_left} days remaining. Upgrade whenever you want.`;
  } else {
    dashboardSubscriptionStatusEl.textContent = "No active paid subscription. Upgrade to Professional or Enterprise to keep scraping.";
  }

  renderSignalList(
    dashboardPaymentsEl,
    data.recent_payments,
    "No payments recorded yet.",
    (payment) => `
      <div class="signal-row signal-row-stack">
        <div>
          <strong>$${escapeHtml(String(payment.amount))} ${escapeHtml(String(payment.currency).toUpperCase())}</strong>
          <span>${escapeHtml(payment.description || "Subscription or account payment")}</span>
        </div>
        <div class="signal-run-meta">
          <strong>${escapeHtml(String(payment.status).toUpperCase())}</strong>
          <span>${escapeHtml(formatDate(payment.created_at))}</span>
        </div>
      </div>
    `
  );

  renderSignalList(
    dashboardSubscriptionsEl,
    data.subscription_history,
    "No subscription changes yet.",
    (subscription) => `
      <div class="signal-row signal-row-stack">
        <div>
          <strong>${escapeHtml(String(subscription.tier).toUpperCase())}</strong>
          <span>${subscription.is_active ? "Active" : "Inactive"}</span>
        </div>
        <div class="signal-run-meta">
          <strong>${subscription.cancel_at_period_end ? "Cancels at period end" : "Standard renewal"}</strong>
          <span>${escapeHtml(formatDate(subscription.created_at))}</span>
        </div>
      </div>
    `
  );

  const activeTier = data.current_subscription?.tier || null;
  dashboardUpgradeProEl.disabled = activeTier === "pro" || activeTier === "enterprise";
  dashboardUpgradeEnterpriseEl.disabled = activeTier === "enterprise";
  dashboardCancelSubscriptionEl.disabled = !data.current_subscription || data.current_subscription.cancel_at_period_end;
}

function renderRuns(runs, pagination) {
  latestRunId = runs.length ? runs[0].id : null;
  renderBusinessExportToolbar();

  if (!runs.length) {
    runsEl.innerHTML = "<p>No scrape runs saved yet.</p>";
    runsPaginationEl.innerHTML = "";
    return;
  }

  runsEl.innerHTML = runs
    .map((run) => {
      const progressMeta = getRunProgressMeta(run);
      const runStatus = String(run.status || "queued").toLowerCase();
      const resultsLine = progressMeta
        ? progressMeta.targetLabel
        : `${formatNumber(run.total_results)} saved businesses`;
      const runSummaryLabel = getRunSummaryLabel(run);

      return `
        <article class="run-card" data-run-status="${escapeHtml(runStatus)}" data-created-at="${escapeHtml(run.created_at)}" data-max-results="${escapeHtml(String(run.max_results))}" data-processed-results="${escapeHtml(String(run.processed_results || 0))}" data-progress-message="${escapeHtml(run.progress_message || "")}">
          <h3>${escapeHtml(run.keyword)}</h3>
          <p>${escapeHtml(run.location || "Worldwide")}</p>
          <p class="meta">${resultsLine}</p>
          <p class="meta">${escapeHtml(runSummaryLabel)}</p>
          <p class="meta">Radius: ${escapeHtml(run.radius)} | Max: ${run.max_results}</p>
          <p class="meta">Mode: ${run.headless ? "Background browser" : "Standard browser"}</p>
          <p class="meta">Status: ${escapeHtml((run.status || "queued").toUpperCase())}</p>
          ${progressMeta ? `<p class="meta run-progress-meta" data-role="run-downloaded">${escapeHtml(progressMeta.downloadedLabel)}</p>` : ""}
          ${progressMeta ? `<div class="run-progress-bar"><span class="run-progress-bar-fill" data-role="run-progress-fill" style="width: ${progressMeta.progressPercent}%"></span></div>` : ""}
          ${progressMeta ? `<p class="meta run-progress-meta" data-role="run-progress-message">${escapeHtml(progressMeta.progressMessage)}</p>` : ""}
          ${progressMeta ? `<p class="meta run-progress-meta" data-role="run-timer">${escapeHtml(progressMeta.timerLabel)}</p>` : ""}
          ${progressMeta ? `<p class="meta run-progress-meta" data-role="run-eta">${escapeHtml(progressMeta.etaLabel)}</p>` : ""}
          ${run.error_message ? `<p class="meta">Reason: ${escapeHtml(run.error_message)}</p>` : ""}
          <p class="meta">${formatDate(run.created_at)}</p>
          <div class="run-actions">
            <button type="button" class="secondary map-preview-button" data-map-preview data-keyword="${escapeHtml(run.keyword)}" data-location="${escapeHtml(run.location || "")}">Preview Map</button>
            <button type="button" class="secondary" data-run-businesses="${run.id}">View Businesses</button>
            <button type="button" class="secondary" data-run-again="${run.id}">Run Again</button>
            <button type="button" class="secondary danger-button" data-delete-run="${run.id}">Delete</button>
            ${run.status === "completed" ? buildExportButtons(run.id) : ""}
          </div>
        </article>
      `;
    })
    .join("");

  if (runs.some((run) => ["queued", "running"].includes(String(run.status || "").toLowerCase()))) {
    startRunClock();
    refreshRunTimers();
  } else {
    stopRunClock();
  }

  renderPagination(runsPaginationEl, pagination, async (nextPage) => {
    runListState.page = nextPage;
    await loadRuns();
  });

  runsEl.querySelectorAll("[data-map-preview]").forEach((button) => {
    button.addEventListener("click", () => {
      previewRunMap(button.dataset.keyword || "", button.dataset.location || "");
    });
  });

  runsEl.querySelectorAll("[data-run-businesses]").forEach((button) => {
    button.addEventListener("click", async () => {
      const run = runs.find((item) => item.id === Number(button.dataset.runBusinesses));
      if (!run) {
        return;
      }
      await focusBusinessesForRun(run);
    });
  });

  runsEl.querySelectorAll("[data-run-again]").forEach((button) => {
    button.addEventListener("click", () => {
      const run = runs.find((item) => item.id === Number(button.dataset.runAgain));
      if (!run) {
        return;
      }
      fillScrapeFormFromRun(run);
      document.getElementById("scraper").scrollIntoView({ behavior: "smooth", block: "start" });
      setStatus(`Loaded run #${run.id} back into the scraper form.`);
    });
  });

  runsEl.querySelectorAll("[data-delete-run]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await deleteRun(Number(button.dataset.deleteRun));
        await Promise.all([loadRuns(), loadBusinesses(), loadInsights()]);
        setStatus("Saved run deleted.");
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderBusinesses(businesses, pagination) {
  if (!businesses.length) {
    businessesEl.innerHTML = "<p>No businesses in the database yet.</p>";
    businessesPaginationEl.innerHTML = "";
    return;
  }

  const rows = businesses
    .map(
      (business) => `
        <tr>
          <td>
            <strong>${escapeHtml(business.name)}</strong>
            <div class="table-submeta">${escapeHtml(business.address || business.city || "")}</div>
          </td>
          <td>${escapeHtml(business.category || "")}</td>
          <td>${escapeHtml(business.city || "")}</td>
          <td>${escapeHtml(business.country || "")}</td>
          <td>
            <div>${escapeHtml(business.phone || "")}</div>
            <div class="table-submeta">${escapeHtml(business.email || "")}</div>
          </td>
          <td>${business.website ? `<a class="table-link" href="${escapeHtml(business.website)}" target="_blank" rel="noreferrer">Open</a>` : ""}</td>
          <td>${business.rating || 0}</td>
          <td class="lead-cell">
            ${userEmail ? `
              <div class="lead-controls" data-business-id="${business.id}">
                <select class="lead-status-select">
                  ${LEAD_STATUS_OPTIONS.map((status) => `<option value="${status}" ${business.lead_status === status ? "selected" : ""}>${formatStatusLabel(status)}</option>`).join("")}
                </select>
                <input class="lead-tags-input" placeholder="priority, follow-up" value="${escapeHtml((business.lead_tags || []).join(", "))}">
                <textarea class="lead-notes-input" rows="2" placeholder="Notes about outreach, pricing, fit...">${escapeHtml(business.lead_notes || "")}</textarea>
                <label class="checkbox checkbox-inline">
                  <input class="lead-archive-input" type="checkbox" ${business.lead_archived ? "checked" : ""}>
                  Archive
                </label>
                <button type="button" class="secondary lead-save-button" data-business-id="${business.id}">Save</button>
              </div>
            ` : `<span class="table-submeta">Save your profile to manage lead pipeline data.</span>`}
          </td>
        </tr>
      `
    )
    .join("");

  businessesEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Category</th>
          <th>City</th>
          <th>Country</th>
          <th>Contact</th>
          <th>Website</th>
          <th>Rating</th>
          <th>Lead Pipeline</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  attachLeadRowActions();

  renderPagination(businessesPaginationEl, pagination, async (nextPage) => {
    businessListState.page = nextPage;
    await loadBusinesses();
  });
}

function renderLeadSummary(summary) {
  if (!userEmail) {
    leadSummaryEl.innerHTML = `
      <article class="insight-card lead-empty-card">
        <span>Lead Desk Locked</span>
        <strong>Save Profile</strong>
        <small>Your email links saved businesses to a reusable pipeline.</small>
      </article>
    `;
    return;
  }

  const cards = [
    { label: "Tracked Leads", value: formatNumber(summary.total), hint: "saved pipeline records" },
    { label: "Active", value: formatNumber(summary.active), hint: "not archived" },
    { label: "Qualified", value: formatNumber(summary.counts.qualified || 0), hint: "ready for offers" },
    { label: "Won", value: formatNumber(summary.counts.won || 0), hint: "converted prospects" },
  ];

  leadSummaryEl.innerHTML = cards.map((card) => `
    <article class="insight-card">
      <span>${escapeHtml(card.label)}</span>
      <strong>${escapeHtml(card.value)}</strong>
      <small>${escapeHtml(card.hint)}</small>
    </article>
  `).join("");
}

function describeSavedSearch(savedSearch) {
  const parts = [];
  if (savedSearch.search_query) parts.push(`Search: ${savedSearch.search_query}`);
  if (savedSearch.city) parts.push(`City: ${savedSearch.city}`);
  if (savedSearch.country) parts.push(`Country: ${savedSearch.country}`);
  if (savedSearch.category) parts.push(`Category: ${savedSearch.category}`);
  if (savedSearch.lead_status) parts.push(`Status: ${formatStatusLabel(savedSearch.lead_status)}`);
  if (savedSearch.tag) parts.push(`Tag: ${savedSearch.tag}`);
  if (savedSearch.saved_only) parts.push("Saved only");
  return parts.length ? parts.join(" • ") : "No filters stored";
}

function renderSavedSearches(searches) {
  savedSearchesState = searches;

  if (!userEmail) {
    savedSearchesEl.innerHTML = `<p class="signal-empty">Save your profile to store reusable search views.</p>`;
    return;
  }

  if (!searches.length) {
    savedSearchesEl.innerHTML = `<p class="signal-empty">No saved searches yet. Filter businesses, then save the current view.</p>`;
    return;
  }

  savedSearchesEl.innerHTML = searches.map((savedSearch) => `
    <div class="signal-row signal-row-stack saved-search-row">
      <div>
        <strong>${escapeHtml(savedSearch.name)}</strong>
        <span>${escapeHtml(describeSavedSearch(savedSearch))}</span>
      </div>
      <div class="saved-search-actions">
        <button type="button" class="secondary apply-saved-search" data-search-id="${savedSearch.id}">Apply</button>
        <button type="button" class="secondary delete-saved-search" data-search-id="${savedSearch.id}">Delete</button>
      </div>
    </div>
  `).join("");

  savedSearchesEl.querySelectorAll(".apply-saved-search").forEach((button) => {
    button.addEventListener("click", async () => {
      const searchId = Number(button.dataset.searchId);
      const savedSearch = savedSearchesState.find((item) => item.id === searchId);
      if (!savedSearch) {
        return;
      }

      updateLeadFilterState({
        search: savedSearch.search_query || "",
        city: savedSearch.city || "",
        country: savedSearch.country || "",
        category: savedSearch.category || "",
        leadStatus: savedSearch.lead_status || "",
        tag: savedSearch.tag || "",
        savedOnly: Boolean(savedSearch.saved_only),
      });
      businessListState.page = 1;
      syncLeadFilterForm();
      await loadBusinesses();
      setStatus(`Applied saved search: ${savedSearch.name}.`);
    });
  });

  savedSearchesEl.querySelectorAll(".delete-saved-search").forEach((button) => {
    button.addEventListener("click", async () => {
      const searchId = Number(button.dataset.searchId);
      try {
        const response = await fetch(`/api/saved-searches/${searchId}?email=${encodeURIComponent(userEmail)}`, { method: "DELETE" });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not delete the saved search");
        }
        await loadSavedSearches();
        setStatus("Saved search deleted.");
      } catch (error) {
        setStatus(error.message, true);
      }
    });
  });
}

function attachLeadRowActions() {
  businessesEl.querySelectorAll(".lead-save-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const container = button.closest(".lead-controls");
      if (!container || !userEmail) {
        return;
      }

      const businessId = Number(container.dataset.businessId);
      const tags = container.querySelector(".lead-tags-input").value
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);

      button.disabled = true;
      try {
        const response = await fetch("/api/leads", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: userEmail,
            business_id: businessId,
            status: container.querySelector(".lead-status-select").value,
            tags,
            notes: container.querySelector(".lead-notes-input").value,
            is_archived: container.querySelector(".lead-archive-input").checked,
          }),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not save the lead record");
        }

        await Promise.all([loadBusinesses(), loadLeadSummary()]);
        setStatus(`Lead updated for business ${businessId}.`);
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderPricingPlans(plans) {
  const container = document.getElementById("pricingCards");

  container.innerHTML = plans
    .map((plan) => {
      if (plan.tier === "free") {
        return `
          <div class="pricing-card ${plan.popular ? "popular" : ""}">
            <h3>${escapeHtml(plan.name)}</h3>
            <div class="pricing-price">$${plan.price}<span>/${plan.billing_period}</span></div>
            <div class="pricing-credits">${plan.scrape_credits === 999 ? "Trial access" : `${plan.scrape_credits} scrapes`}</div>
            <ul class="pricing-features">
              ${plan.features.map((feature) => `<li>${escapeHtml(feature)}</li>`).join("")}
            </ul>
            <button type="button" data-action="save-profile">Activate Free Trial</button>
          </div>
        `;
      }

      return `
        <div class="pricing-card ${plan.popular ? "popular" : ""}">
          <h3>${escapeHtml(plan.name)}</h3>
          <div class="pricing-price">$${plan.price}<span>/${plan.billing_period}</span></div>
          <div class="pricing-credits">${plan.max_results_per_scrape} results per scrape</div>
          <ul class="pricing-features">
            ${plan.features.map((feature) => `<li>${escapeHtml(feature)}</li>`).join("")}
          </ul>
          <div class="pricing-actions-row">
            <button type="button" data-tier="${escapeHtml(plan.tier)}" data-action="request-upgrade">Choose ${escapeHtml(plan.name)}</button>
          </div>
        </div>
      `;
    })
    .join("");

  container.querySelectorAll("button[data-action='save-profile']").forEach((button) => {
    button.addEventListener("click", async () => {
      await saveProfile();
    });
  });

  container.querySelectorAll("button[data-action='request-upgrade']").forEach((button) => {
    button.addEventListener("click", async () => {
      await subscribeToPlan(button.dataset.tier || "pro", "card");
    });
  });
}

function renderInsights(insights) {
  const cards = [
    { label: "Total Runs", value: formatNumber(insights.total_runs), hint: "search missions completed" },
    { label: "Business Index", value: formatNumber(insights.total_businesses), hint: "saved lead records" },
    { label: "Avg Rating", value: insights.average_rating.toFixed(2), hint: "mean review score" },
    { label: "Contactable", value: formatNumber(insights.contactable_businesses), hint: "phone, email, or website available" },
  ];

  insightCardsEl.innerHTML = cards
    .map(
      (card) => `
        <article class="insight-card">
          <span>${escapeHtml(card.label)}</span>
          <strong>${escapeHtml(card.value)}</strong>
          <small>${escapeHtml(card.hint)}</small>
        </article>
      `
    )
    .join("");

  renderSignalList(topCategoriesEl, insights.top_categories, "No category data yet.", (item) => `
    <div class="signal-row">
      <span>${escapeHtml(item.label)}</span>
      <strong>${formatNumber(item.count)}</strong>
    </div>
  `);

  renderSignalList(topCitiesEl, insights.top_cities, "No city data yet.", (item) => `
    <div class="signal-row">
      <span>${escapeHtml(item.label)}</span>
      <strong>${formatNumber(item.count)}</strong>
    </div>
  `);

  renderSignalList(recentRunsEl, insights.recent_runs, "No recent runs yet.", (run) => `
    <div class="signal-row signal-row-stack">
      <div>
        <strong>${escapeHtml(run.keyword)}</strong>
        <span>${escapeHtml(run.location || "Worldwide")}</span>
      </div>
      <div class="signal-run-meta">
        <strong>${formatNumber(run.total_results)}</strong>
        <span>${formatDate(run.created_at)}</span>
      </div>
    </div>
  `);

  heroTotalBusinessesEl.textContent = formatNumber(insights.total_businesses);
  heroSuccessRateEl.textContent = `${insights.success_rate}%`;
  heroContactableEl.textContent = formatNumber(insights.contactable_businesses);
  heroTopSignalEl.textContent = insights.top_categories.length
    ? `${insights.top_categories[0].label} is currently the strongest category with ${formatNumber(insights.top_categories[0].count)} indexed leads.`
    : "Load data to reveal your hottest market.";
}

async function loadPaymentConfig() {
  paymentConfig = {
    payments_enabled: false,
    paypal_enabled: false,
    publishable_key: "",
    paypal_client_id: "",
    paypal_currency: "USD",
    paypal_environment: "sandbox",
    paypal_sdk_base: "",
    trial_days: 15,
  };
  setPaymentBanner("", "info");
}

async function loadRuns() {
  const params = new URLSearchParams({
    page: String(runListState.page),
    page_size: String(runListState.pageSize),
  });
  if (runFiltersState.search) {
    params.set("search", runFiltersState.search);
  }
  if (runFiltersState.status) {
    params.set("status", runFiltersState.status);
  }

  const response = await fetch(`/api/scrapes?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load scrape runs");
  }
  const data = await response.json();
  updateRunNotifications(data.items || []);
  renderRuns(data.items, data.pagination);
}

async function loadBusinesses() {
  const response = await fetch(`/api/businesses?${buildBusinessQueryString()}`);
  if (!response.ok) {
    throw new Error("Failed to load businesses");
  }
  const data = await response.json();
  renderBusinesses(data.items, data.pagination);
}

async function loadLeadSummary() {
  if (!userEmail) {
    renderLeadSummary({ total: 0, active: 0, archived: 0, counts: {} });
    return;
  }

  const response = await fetch(`/api/leads/summary/${encodeURIComponent(userEmail)}`);
  if (!response.ok) {
    throw new Error("Failed to load lead summary");
  }

  renderLeadSummary(await response.json());
}

async function loadSavedSearches() {
  if (!userEmail) {
    renderSavedSearches([]);
    return;
  }

  const response = await fetch(`/api/saved-searches/${encodeURIComponent(userEmail)}`);
  if (!response.ok) {
    throw new Error("Failed to load saved searches");
  }

  renderSavedSearches(await response.json());
}

async function loadInsights() {
  const response = await fetch("/api/insights/overview");
  if (!response.ok) {
    throw new Error("Failed to load platform insights");
  }
  renderInsights(await response.json());
}

async function loadPricing() {
  const response = await fetch("/api/pricing");
  if (!response.ok) {
    throw new Error("Failed to load pricing");
  }
  const data = await response.json();
  renderPricingPlans(data.plans);
}

async function loadAccessStatus() {
  if (!userEmail) {
    accessState = null;
    updateAccessDisplay();
    return;
  }

  const response = await fetch(`/api/users/access/${encodeURIComponent(userEmail)}`);
  if (!response.ok) {
    throw new Error("Failed to load access status");
  }

  accessState = await response.json();
  updateAccessDisplay();

  if (accessState.has_active_subscription) {
    setProfileStatus(`Subscription active on ${accessState.subscription_tier}. Scraping is unlocked.`, false);
  } else if (accessState.trial_active) {
    setProfileStatus(`Trial active. ${accessState.trial_days_left} days left before a Professional subscription is required.`, false);
  } else if (accessState.requires_subscription) {
    setProfileStatus("Trial finished. Upgrade to Professional or Enterprise to continue scraping.", true);
  }
}

async function loadUserDashboard() {
  if (!userEmail) {
    renderDashboardEmpty("Save your company profile to unlock the personal dashboard and self-service subscription controls.");
    return;
  }

  const response = await fetch(`/api/users/dashboard/${encodeURIComponent(userEmail)}`);
  if (response.status === 404) {
    renderDashboardEmpty("Save your company profile to unlock the personal dashboard and self-service subscription controls.");
    return;
  }
  if (!response.ok) {
    throw new Error("Failed to load user dashboard");
  }

  renderDashboard(await response.json());
}

async function saveProfile() {
  const payload = getProfilePayload();
  if (!validateProfilePayload(payload)) {
    setProfileStatus("Full name, company, email, and phone are required.", true);
    return false;
  }

  saveProfileButtonEl.disabled = true;
  try {
    const wantsAccountRegistration = !authToken && (payload.password || payload.confirm_password);
    if (wantsAccountRegistration && payload.password !== payload.confirm_password) {
      throw new Error("Password confirmation does not match");
    }

    const endpoint = wantsAccountRegistration
      ? "/api/auth/register"
      : "/api/users/profile";
    const method = wantsAccountRegistration ? "POST" : "PUT";
    const requestBody = wantsAccountRegistration
      ? payload
      : {
          full_name: payload.full_name,
          company_name: payload.company_name,
          email: payload.email,
          phone: payload.phone,
          country: payload.country,
          preferred_payment_provider: payload.preferred_payment_provider,
        };

    const response = await fetch(endpoint, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to save profile");
    }

    if (wantsAccountRegistration) {
      setAuthSession(data.access_token, data.user);
      loginFormEl.reset();
      setProfileStatus(`Account created for ${data.user.company_name}. Your 15-day trial is active until ${new Date(data.user.trial_ends_at).toLocaleDateString()}.`);
    } else {
      syncEmailFields(payload.email);
      populateProfileForm(data);
      updateAuthUi(data);
      setProfileStatus(`Profile saved for ${data.company_name}. Your trial or subscription access remains linked to this account.`);
    }

    await Promise.all([loadAccessStatus(), loadUserDashboard(), loadBusinesses(), loadLeadSummary(), loadSavedSearches()]);
    return true;
  } catch (error) {
    setProfileStatus(error.message, true);
    return false;
  } finally {
    saveProfileButtonEl.disabled = false;
  }
}

async function cancelOwnSubscription() {
  if (!userEmail) {
    setStatus("Save your profile first so the app can find your account.", true);
    return;
  }

  dashboardCancelSubscriptionEl.disabled = true;
  try {
    const response = await fetch("/api/users/subscription/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: userEmail }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Unable to cancel the subscription");
    }

    const endDate = data.current_period_end ? formatDate(data.current_period_end) : "the current billing period";
    setStatus(`Subscription cancellation registered. Access remains available until ${endDate}.`);
    await Promise.all([loadUserDashboard(), loadAccessStatus()]);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    dashboardCancelSubscriptionEl.disabled = false;
  }
}

async function subscribeToPlan(tier, provider) {
  const saved = await saveProfile();
  if (!saved) {
    setStatus("Save the profile first so the platform can link the upgrade request to your account.", true);
    return;
  }
  window.location.hash = "#pricing";
  setStatus(`${String(tier).toUpperCase()} plan selected. Your account profile is saved and ready.`, false);
}

profileFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveProfile();
});

loginFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(loginFormEl);
  const email = (formData.get("email") || "").toString().trim();
  const password = (formData.get("password") || "").toString();

  try {
    const user = await loginUserAccount(email, password);
    setStatus(`Logged in as ${user.email}.`);
    await Promise.all([loadAccessStatus(), loadUserDashboard(), loadBusinesses(), loadLeadSummary(), loadSavedSearches()]);
  } catch (error) {
    setAuthStateMessage(error.message, true);
  }
});

logoutBtnEl.addEventListener("click", async () => {
  clearAuthSession();
  loginFormEl.reset();
  profileFormEl.reset();
  renderBusinessExportToolbar();
  await Promise.all([loadBusinesses(), loadRuns(), loadInsights()]);
  setStatus("Logged out.");
});

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();

  const saved = await saveProfile();
  if (!saved) {
    setStatus("Profile information must be saved before scraping starts.", true);
    return;
  }

  await loadAccessStatus();
  if (!accessState || !accessState.can_scrape) {
    setStatus("Your trial has ended. Subscribe to Professional or Enterprise to continue scraping.", true);
    return;
  }

  const formData = new FormData(formEl);
  const payload = {
    keyword: formData.get("keyword"),
    email: userEmail,
    location: formData.get("location"),
    radius: formData.get("radius"),
    max_results: Number(formData.get("max_results") || 25),
    headless: formData.get("headless") === "on",
    save_files: formData.get("save_files") === "on",
  };
  updateMapPreview(String(payload.keyword || ""), String(payload.location || ""));
  const maxResultsAllowed = accessState?.has_active_subscription && accessState.subscription_tier === "enterprise"
    ? ENTERPRISE_MAX_RESULTS_PER_SCRAPE
    : DEFAULT_MAX_RESULTS_PER_SCRAPE;
  if (payload.max_results > maxResultsAllowed) {
    setStatus(`Your current plan allows up to ${maxResultsAllowed} results per scrape. Upgrade to scrape more.`, true);
    return;
  }

  scrapeButtonEl.disabled = true;
  setStatus(`Running scrape in ${payload.headless ? "background" : "standard"} mode. The Google Maps preview stays in-platform while businesses are collected...`);

  try {
    const response = await fetch("/api/scrapes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) {
      throw new Error(data?.detail || `Scrape failed (${response.status})`);
    }
    if (!data) {
      throw new Error("The server returned an empty response for the scrape request.");
    }

    if (data.run?.status === "queued") {
      await ensureNotificationPermission();
      setStatus(`Scrape queued successfully. The run is processing in the background. Access mode used: ${data.billing_mode}. Refresh runs in a few moments to see results.`);
    } else {
      setStatus(`Saved ${data.results.length} businesses. Access mode used: ${data.billing_mode}. Trial days left: ${data.remaining_credits}.`);
    }
    runListState.page = 1;
    businessListState.page = 1;
    await Promise.all([loadRuns(), loadBusinesses(), loadInsights(), loadAccessStatus()]);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    scrapeButtonEl.disabled = false;
  }
});

document.getElementById("refresh-runs").addEventListener("click", async () => {
  try {
    await loadRuns();
    setStatus("Runs refreshed.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

runFilterFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  updateRunFilterState(getRunFilterPayload());
  runListState.page = 1;
  try {
    await loadRuns();
    setStatus("Saved runs filtered.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("clearRunFilters").addEventListener("click", async () => {
  updateRunFilterState({ search: "", status: "" });
  syncRunFilterForm();
  runListState.page = 1;
  try {
    await loadRuns();
    setStatus("Saved run filters cleared.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("refresh-businesses").addEventListener("click", async () => {
  try {
    await loadBusinesses();
    setStatus("Businesses refreshed.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("refresh-leads").addEventListener("click", async () => {
  try {
    await Promise.all([loadLeadSummary(), loadSavedSearches(), loadBusinesses()]);
    setStatus("Lead desk refreshed.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("refresh-insights").addEventListener("click", async () => {
  try {
    await loadInsights();
    setStatus("Signal board refreshed.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("refresh-dashboard").addEventListener("click", async () => {
  try {
    await loadUserDashboard();
    setStatus("Dashboard refreshed.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

dashboardUpgradeProEl.addEventListener("click", async () => {
  await subscribeToPlan("pro", profileFormEl.querySelector('select[name="preferred_payment_provider"]').value || "card");
});

dashboardUpgradeEnterpriseEl.addEventListener("click", async () => {
  await subscribeToPlan("enterprise", profileFormEl.querySelector('select[name="preferred_payment_provider"]').value || "card");
});

dashboardCancelSubscriptionEl.addEventListener("click", async () => {
  await cancelOwnSubscription();
});

dashboardEditProfileEl.addEventListener("click", () => {
  document.getElementById("profile").scrollIntoView({ behavior: "smooth", block: "start" });
  profileFormEl.querySelector('input[name="full_name"]').focus();
});

leadFilterFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  updateLeadFilterState(getLeadFilterPayload());
  businessListState.page = 1;
  try {
    await loadBusinesses();
    setStatus("Lead filters applied.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("clearLeadFilters").addEventListener("click", async () => {
  updateLeadFilterState({});
  businessListState.page = 1;
  syncLeadFilterForm();
  try {
    await loadBusinesses();
    setStatus("Lead filters cleared.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("saveCurrentSearch").addEventListener("click", async () => {
  if (!userEmail) {
    setStatus("Save your profile first so the platform can attach the saved search to your account.", true);
    return;
  }

  const name = (savedSearchNameEl.value || "").trim();
  if (!name) {
    setStatus("Enter a name for the saved search.", true);
    return;
  }

  const filters = getLeadFilterPayload();
  try {
    const response = await fetch("/api/saved-searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: userEmail,
        name,
        search_query: filters.search || null,
        city: filters.city || null,
        country: filters.country || null,
        category: filters.category || null,
        lead_status: filters.leadStatus || null,
        tag: filters.tag || null,
        saved_only: filters.savedOnly,
        alert_enabled: true,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not save the search");
    }
    savedSearchNameEl.value = "";
    await loadSavedSearches();
    setStatus(`Saved search created: ${name}.`);
  } catch (error) {
    setStatus(error.message, true);
  }
});

if (userEmail) {
  syncEmailFields(userEmail);
}

formEl.querySelector('input[name="keyword"]').addEventListener("input", () => {
  updateMapPreview(
    formEl.querySelector('input[name="keyword"]').value,
    formEl.querySelector('input[name="location"]').value,
  );
});

formEl.querySelector('input[name="location"]').addEventListener("input", () => {
  updateMapPreview(
    formEl.querySelector('input[name="keyword"]').value,
    formEl.querySelector('input[name="location"]').value,
  );
});

refreshMapPreviewEl.addEventListener("click", () => {
  updateMapPreview(
    formEl.querySelector('input[name="keyword"]').value,
    formEl.querySelector('input[name="location"]').value,
  );
  setStatus("Google Maps preview refreshed.");
});

syncAdminLinks();
updateMapPreview(
  formEl.querySelector('input[name="keyword"]').value,
  formEl.querySelector('input[name="location"]').value,
);
renderBusinessExportToolbar();
renderDashboardEmpty("Save your company profile to unlock the personal dashboard and self-service subscription controls.");
syncLeadFilterForm();
syncRunFilterForm();
renderLeadSummary({ total: 0, active: 0, archived: 0, counts: {} });
renderSavedSearches([]);
updateAuthUi(null);
setPaymentBanner("", "info");

(async () => {
  try {
    await loadPaymentConfig();
    await Promise.all([loadPricing(), loadRuns(), loadBusinesses(), loadInsights()]);

    if (authToken) {
      await restoreSession();
      await Promise.all([loadAccessStatus(), loadUserDashboard(), loadLeadSummary(), loadSavedSearches(), loadBusinesses()]);
    } else if (userEmail) {
      await Promise.all([loadAccessStatus(), loadUserDashboard(), loadLeadSummary(), loadSavedSearches(), loadBusinesses()]);
    } else {
      updateAccessDisplay();
    }
  } catch (error) {
    setStatus(error.message, true);
  }
})();