const statusEl = document.getElementById("status");
const profileStatusEl = document.getElementById("profileStatus");
const runsEl = document.getElementById("runs");
const businessesEl = document.getElementById("businesses");
const runsPaginationEl = document.getElementById("runsPagination");
const businessesPaginationEl = document.getElementById("businessesPagination");
const businessExportsEl = document.getElementById("businessExports");
const formEl = document.getElementById("scrape-form");
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

let userEmail = localStorage.getItem("userEmail") || "";
let stripe = null;
let paymentConfig = {
  payments_enabled: false,
  paypal_enabled: false,
  publishable_key: "",
  trial_days: 15,
};
let accessState = null;
const runListState = { page: 1, pageSize: 6 };
const businessListState = { page: 1, pageSize: 10 };
let latestRunId = null;
let dashboardState = null;

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#a02b2b" : "";
}

function setProfileStatus(message, isError = false) {
  profileStatusEl.textContent = message;
  profileStatusEl.style.color = isError ? "#a02b2b" : "";
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
  localStorage.setItem("userEmail", userEmail);
  const scrapeEmailField = formEl.querySelector('input[name="email"]');
  const profileEmailField = profileFormEl.querySelector('input[name="email"]');
  scrapeEmailField.value = userEmail;
  profileEmailField.value = userEmail;
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
  };
}

function validateProfilePayload(payload) {
  return payload.full_name && payload.company_name && payload.email && payload.phone;
}

function updateAccessDisplay() {
  const daysLeft = accessState ? accessState.trial_days_left : 0;
  statusCreditsEl.textContent = daysLeft;

  if (!accessState) {
    creditDisplayEl.innerHTML = `<span class="credit-icon">⏳</span><span id="userCredits">0</span> trial days left`;
    creditWarningEl.style.display = "none";
    creditDisplayEl.style.opacity = "0.6";
    return;
  }

  if (accessState.has_active_subscription) {
    userCreditsEl.textContent = accessState.subscription_tier.toUpperCase();
    creditDisplayEl.innerHTML = `<span class="credit-icon">✓</span><span id="userCredits">${escapeHtml(accessState.subscription_tier.toUpperCase())}</span> active`;
    creditWarningEl.style.display = "none";
    statusCreditsEl.textContent = accessState.trial_days_left;
    creditDisplayEl.style.opacity = "1";
    return;
  }

  creditDisplayEl.innerHTML = `<span class="credit-icon">⏳</span><span id="userCredits">${daysLeft}</span> trial days left`;
  creditWarningEl.style.display = accessState.requires_subscription ? "block" : "none";
  creditDisplayEl.style.opacity = accessState.can_scrape ? "1" : "0.75";
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

function renderBusinessExportToolbar() {
  businessExportsEl.innerHTML = buildExportButtons(latestRunId, "toolbar");
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
    .map(
      (run) => `
        <article class="run-card">
          <h3>${escapeHtml(run.keyword)}</h3>
          <p>${escapeHtml(run.location || "Worldwide")}</p>
          <p class="meta">${formatNumber(run.total_results)} saved businesses</p>
          <p class="meta">Radius: ${escapeHtml(run.radius)} | Max: ${run.max_results}</p>
          <p class="meta">Mode: ${run.headless ? "Headless" : "Visible browser"}</p>
          <p class="meta">${formatDate(run.created_at)}</p>
          <div class="run-actions">
            ${buildExportButtons(run.id)}
          </div>
        </article>
      `
    )
    .join("");

  renderPagination(runsPaginationEl, pagination, async (nextPage) => {
    runListState.page = nextPage;
    await loadRuns();
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
          <td>${escapeHtml(business.name)}</td>
          <td>${escapeHtml(business.category || "")}</td>
          <td>${escapeHtml(business.city || "")}</td>
          <td>${escapeHtml(business.country || "")}</td>
          <td>${escapeHtml(business.phone || "")}</td>
          <td>${business.website ? `<a href="${escapeHtml(business.website)}" target="_blank" rel="noreferrer">Open</a>` : ""}</td>
          <td>${business.rating || 0}</td>
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
          <th>Phone</th>
          <th>Website</th>
          <th>Rating</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  renderPagination(businessesPaginationEl, pagination, async (nextPage) => {
    businessListState.page = nextPage;
    await loadBusinesses();
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
            <button type="button" data-tier="${escapeHtml(plan.tier)}" data-provider="card" ${paymentConfig.payments_enabled ? "" : "disabled"}>Pay by Card</button>
            <button type="button" class="secondary" data-tier="${escapeHtml(plan.tier)}" data-provider="paypal" ${paymentConfig.paypal_enabled ? "" : "disabled"}>PayPal</button>
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

  container.querySelectorAll("button[data-tier]").forEach((button) => {
    button.addEventListener("click", async () => {
      await subscribeToPlan(button.dataset.tier, button.dataset.provider);
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
  const response = await fetch("/api/payment/config");
  if (!response.ok) {
    throw new Error("Failed to load payment configuration");
  }

  paymentConfig = await response.json();
  stripe = paymentConfig.payments_enabled && paymentConfig.publishable_key && window.Stripe
    ? window.Stripe(paymentConfig.publishable_key)
    : null;

  if (paymentConfig.payments_enabled && paymentConfig.paypal_enabled) {
    setPaymentBanner("Subscriptions are available by card and PayPal.", "success");
  } else if (paymentConfig.payments_enabled) {
    setPaymentBanner("Card checkout is ready. Add PAYPAL_SUBSCRIPTION_URL to enable PayPal too.", "warning");
  } else if (paymentConfig.paypal_enabled) {
    setPaymentBanner("PayPal is ready. Add STRIPE_PUBLISHABLE_KEY to enable card checkout too.", "warning");
  } else {
    setPaymentBanner("Payment providers are not configured yet. Users can still start the free trial.", "warning");
  }
}

async function loadRuns() {
  const response = await fetch(`/api/scrapes?page=${runListState.page}&page_size=${runListState.pageSize}`);
  if (!response.ok) {
    throw new Error("Failed to load scrape runs");
  }
  const data = await response.json();
  renderRuns(data.items, data.pagination);
}

async function loadBusinesses() {
  const response = await fetch(`/api/businesses?page=${businessListState.page}&page_size=${businessListState.pageSize}`);
  if (!response.ok) {
    throw new Error("Failed to load businesses");
  }
  const data = await response.json();
  renderBusinesses(data.items, data.pagination);
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
    const response = await fetch("/api/users/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Failed to save profile");
    }

    syncEmailFields(payload.email);
    setProfileStatus(`Profile saved for ${data.company_name}. Your 15-day trial is active until ${new Date(data.trial_ends_at).toLocaleDateString()}.`);
    await Promise.all([loadAccessStatus(), loadUserDashboard()]);
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
    setStatus("Save the profile first so the platform can link the subscription to your account.", true);
    return;
  }

  if (provider === "card" && !stripe) {
    setStatus("Card checkout is not configured yet.", true);
    return;
  }

  if (provider === "paypal" && !paymentConfig.paypal_enabled) {
    setStatus("PayPal checkout is not configured yet.", true);
    return;
  }

  try {
    const response = await fetch("/api/subscription/create-checkout-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: userEmail,
        tier,
        provider,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Subscription failed");
    }

    if (provider === "card") {
      const result = await stripe.redirectToCheckout({ sessionId: data.session_id });
      if (result.error) {
        throw new Error(result.error.message);
      }
      return;
    }

    setStatus("Redirecting to PayPal. Once payment is confirmed, an admin can activate the subscription immediately.");
    window.location.href = data.url;
  } catch (error) {
    setStatus(error.message, true);
  }
}

profileFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveProfile();
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

  scrapeButtonEl.disabled = true;
  setStatus(`Running scrape in ${payload.headless ? "headless" : "visible"} mode. Selenium is opening Google Maps and collecting businesses...`);

  try {
    const response = await fetch("/api/scrapes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Scrape failed");
    }

    setStatus(`Saved ${data.results.length} businesses. Access mode used: ${data.billing_mode}. Trial days left: ${data.remaining_credits}.`);
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

document.getElementById("refresh-businesses").addEventListener("click", async () => {
  try {
    await loadBusinesses();
    setStatus("Businesses refreshed.");
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

if (userEmail) {
  syncEmailFields(userEmail);
}

renderBusinessExportToolbar();
renderDashboardEmpty("Save your company profile to unlock the personal dashboard and self-service subscription controls.");

Promise.all([loadPaymentConfig(), loadPricing(), loadRuns(), loadBusinesses(), loadInsights()])
  .then(async () => {
    if (userEmail) {
      await Promise.all([loadAccessStatus(), loadUserDashboard()]);
    } else {
      updateAccessDisplay();
    }
  })
  .catch((error) => {
    setStatus(error.message, true);
  });