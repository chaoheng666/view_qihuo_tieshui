(function () {
    const REFRESH_INTERVAL_MS = 5000;
    const CHART_WINDOW_POINTS = 90;
    const QUALITY_LABELS = {
        ok: "正常",
        fallback: "降级",
        stale: "陈旧",
        needs_review: "待确认",
        missing: "缺失",
    };
    const SOURCE_LABELS = {
        akshare_realtime: "AkShare 期货实时",
        sina_futures: "新浪期货实时",
        sina_index: "新浪指数实时",
        eastmoney_index: "东方财富指数",
        last_valid_snapshot: "最近有效快照",
        cffex_daily: "中金所日线",
        index_daily: "指数历史日线",
        missing: "缺失",
    };
    const SOURCE_CATALOG = [
        {
            key: "sina_index",
            name: "新浪指数实时",
            url: "http://hq.sinajs.cn/list=sh000300,sh000905,sh000016,sh000852",
            intro: "沪深300、中证500、上证50和中证1000实时指数主源。",
        },
        {
            key: "eastmoney_index",
            name: "东方财富指数",
            url: "http://quote.eastmoney.com/center/hszs.html",
            intro: "指数备用链路，主源异常时回退使用。",
        },
        {
            key: "akshare_realtime",
            name: "AkShare 期货实时",
            url: "https://akshare.akfamily.xyz/data/futures/futures.html",
            intro: "IF、IC、IH 主力期货实时主源。",
        },
        {
            key: "sina_futures",
            name: "新浪期货实时",
            url: "http://hq.sinajs.cn/list=",
            intro: "IM 主力实时主源，同时作为股指期货备用源。",
        },
        {
            key: "cffex_daily",
            name: "中金所日线",
            url: "https://www.cffex.com.cn/lssjxz/",
            intro: "30日主力升贴水背景曲线的期货历史源。",
        },
        {
            key: "index_daily",
            name: "指数历史日线",
            url: "https://akshare.akfamily.xyz/data/index/index.html",
            intro: "30日背景曲线的指数历史源。",
        },
    ];
    const CHART_COLORS = {
        bg: "#ffffff",
        raw: "#94a3b8",
        rawFill: "rgba(217, 119, 6, 0.00)",
        smooth: "#475569",
        smoothFill: "rgba(15, 118, 110, 0.00)",
        futures: "#1d4ed8",
        futuresGlow: "rgba(29, 78, 216, 0.24)",
        index: "#c2410c",
        indexGlow: "rgba(194, 65, 12, 0.22)",
        up: "#d92d20",
        upGlow: "rgba(217, 45, 32, 0.13)",
        down: "#00875a",
        downGlow: "rgba(0, 135, 90, 0.14)",
        realtimePoint: "#ffffff",
        axis: "#475569",
        grid: "rgba(100, 116, 139, 0.18)",
        text: "#102033",
    };

    const state = {
        selectedSymbol: "IF",
        loading: false,
        refreshTimer: null,
        queuedLoad: false,
        queuedForceRefresh: false,
        thresholds: null,
        lastSelectedSnapshot: null,
        lastThresholdPromptKey: "",
        nextRefreshAt: 0,
    };

    const summaryGrid = document.getElementById("summaryGrid");
    const contractTableBody = document.getElementById("contractTableBody");
    const alertList = document.getElementById("alertList");
    const metricGrid = document.getElementById("metricGrid");
    const sourceBox = document.getElementById("sourceBox");
    const qualityBox = document.getElementById("qualityBox");
    const statusPulseBox = document.getElementById("statusPulseBox");
    const opsHeaderBadge = document.getElementById("opsHeaderBadge");
    const sourceCatalogGrid = document.getElementById("sourceCatalogGrid");
    const generatedAt = document.getElementById("generatedAt");
    const selectedSymbolLabel = document.getElementById("selectedSymbolLabel");
    const heroQuality = document.getElementById("heroQuality");
    const chartTitle = document.getElementById("chartTitle");
    const chartQuality = document.getElementById("chartQuality");
    const detailSubtitle = document.getElementById("detailSubtitle");
    const chartWrap = document.querySelector(".chart-wrap");
    const refreshButton = document.getElementById("refreshButton");
    const topProgress = document.getElementById("topProgress");
    const refreshCountdownLabel = document.getElementById("refreshCountdownLabel");
    const refreshCountdownBar = document.getElementById("refreshCountdownBar");
    const headlineStrip = document.getElementById("headlineStrip");
    const signalStack = document.getElementById("signalStack");
    const alertConfigStatus = null;
    const saveAlertConfigButton = null;
    const sendAlertTestButton = null;
    const triggerThresholdInput = null;
    const cooldownMinutesInput = null;
    const popupEnabledInput = null;
    const emailEnabledInput = null;
    const emailHostInput = null;
    const emailPortInput = null;
    const emailSecurityInput = null;
    const emailSenderInput = null;
    const emailRecipientsInput = null;
    const emailUsernameInput = null;
    const emailPasswordInput = null;
    const emailSubjectPrefixInput = null;
    const feishuEnabledInput = null;
    const feishuWebhookInput = null;
    const feishuSecretInput = null;
    const wecomEnabledInput = null;
    const wecomWebhookInput = null;
    const thresholdModal = document.getElementById("thresholdModal");
    const thresholdModalBody = document.getElementById("thresholdModalBody");
    const thresholdModalClose = document.getElementById("thresholdModalClose");
    const thresholdModalAcknowledge = document.getElementById("thresholdModalAcknowledge");

    let chartOverlay = document.getElementById("chartOverlay");
    let chartMount = document.getElementById("premiumChartMount");
    let countdownTimer = null;
    let topProgressStartedAt = 0;
    let topProgressHideTimer = null;

    function toNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function formatNumber(value, digits) {
        const number = toNumber(value);
        return number === null ? "--" : number.toFixed(digits == null ? 2 : digits);
    }

    function formatSigned(value, digits) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        const sign = number > 0 ? "+" : "";
        return `${sign}${number.toFixed(digits == null ? 2 : digits)}`;
    }

    function formatPercent(value, digits) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        return `${number > 0 ? "+" : ""}${number.toFixed(digits == null ? 2 : digits)}%`;
    }

    function basisLabel(value) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        if (number === 0) {
            return "平水";
        }
        return number < 0 ? "贴水" : "升水";
    }

    function formatBasisRate(value, digits) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        return `${basisLabel(number)} ${Math.abs(number).toFixed(digits == null ? 2 : digits)}%`;
    }

    function formatBasisPoints(value, digits) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        return `${basisLabel(number)} ${Math.abs(number).toFixed(digits == null ? 2 : digits)}点`;
    }

    function getAnnualizedBasisRate(item) {
        if (!item) {
            return null;
        }
        const explicit = toNumber(item.annualized_basis_rate);
        if (explicit !== null) {
            return explicit;
        }
        const futuresPrice = toNumber(item.futures_price);
        const indexPrice = toNumber(item.index_price);
        const days = toNumber(item.days_to_expiry);
        if (futuresPrice !== null && futuresPrice > 0 && indexPrice !== null && indexPrice > 0 && days !== null && days > 0) {
            return (indexPrice - futuresPrice) / futuresPrice * 100 * 365 / days;
        }
        const legacyAnnualized = toNumber(item.annualized_rate);
        return legacyAnnualized === null ? null : -legacyAnnualized;
    }

    function formatAnnualizedBasis(item, digits) {
        const number = getAnnualizedBasisRate(item);
        if (number === null) {
            return "--";
        }
        if (number === 0) {
            return `年化平水 ${number.toFixed(digits == null ? 2 : digits)}%`;
        }
        return `${number > 0 ? "年化贴水" : "年化升水"} ${Math.abs(number).toFixed(digits == null ? 2 : digits)}%`;
    }

    function formatBasisGap(value, digits) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        if (number === 0) {
            return `持平 0.${"0".repeat(digits == null ? 3 : digits)}%`;
        }
        return `${number < 0 ? "贴水加深" : "贴水收敛"} ${Math.abs(number).toFixed(digits == null ? 3 : digits)}%`;
    }

    function formatBasisAxis(value) {
        const number = toNumber(value);
        if (number === null) {
            return "";
        }
        if (number === 0) {
            return "平水";
        }
        return `${number < 0 ? "贴水" : "升水"} ${Math.abs(number).toFixed(2)}%`;
    }

    function formatCount(value) {
        const number = toNumber(value);
        return number === null ? "--" : Math.round(number).toLocaleString("zh-CN");
    }

    function formatFreshness(value) {
        const number = toNumber(value);
        if (number === null) {
            return "--";
        }
        if (number < 60) {
            return `${Math.round(number)}秒前`;
        }
        if (number < 3600) {
            return `${Math.round(number / 60)}分钟前`;
        }
        return `${Math.round(number / 3600)}小时前`;
    }

    function formatFreshnessPlain(value) {
        const number = toNumber(value);
        return number === null ? "--" : `${Math.round(number)}秒`;
    }

    function formatQuoteClock(value) {
        const source = String(value || "").trim();
        if (!source) {
            return "--";
        }
        const parts = source.split(" ");
        return parts.length > 1 ? parts[1] : source;
    }

    function escapeHTML(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function qualityClass(value) {
        return `quality-${String(value || "ok").replace(/[^a-z_]/gi, "_").toLowerCase()}`;
    }

    function qualityText(value) {
        return QUALITY_LABELS[value] || String(value || "--");
    }

    function sourceText(value) {
        const key = String(value || "").trim();
        if (!key) {
            return "--";
        }
        return SOURCE_LABELS[key] || key.replace(/_/g, " ");
    }

    function sourceMeta(value) {
        const key = String(value || "").trim();
        if (!key) {
            return { key: "", name: "--", url: "", intro: "" };
        }
        return SOURCE_CATALOG.find(item => item.key === key) || {
            key,
            name: sourceText(key),
            url: "",
            intro: "",
        };
    }

    function renderExternalLink(url, label, className) {
        const normalized = String(url || "").trim();
        if (!normalized) {
            return `<span class="${className || "info-value"}">--</span>`;
        }
        const text = label || normalized;
        const cssClass = className || "info-link";
        return `<a class="${cssClass}" href="${escapeHTML(normalized)}" target="_blank" rel="noreferrer noopener">${escapeHTML(text)}</a>`;
    }

    function directionClass(value) {
        const number = toNumber(value);
        if (number === null || number === 0) {
            return "";
        }
        return number > 0 ? "up" : "down";
    }

    function annualizedBasisTone(value) {
        const number = toNumber(value);
        if (number === null || number === 0) {
            return number;
        }
        return -number;
    }

    function clampPercent(value) {
        const number = toNumber(value);
        if (number === null) {
            return 0;
        }
        return Math.max(0, Math.min(number, 100));
    }

    function parseTimestamp(value, endOfDay) {
        if (!value) {
            return null;
        }
        const source = String(value).trim();
        const parts = source.split(" ");
        const datePart = parts[0];
        const timePart = parts[1] || (endOfDay ? "15:00:00" : "00:00:00");
        const dateBits = datePart.split("-").map(Number);
        const timeBits = timePart.split(":").map(Number);
        if (dateBits.length !== 3 || dateBits.some(Number.isNaN)) {
            return null;
        }
        return new Date(
            dateBits[0],
            dateBits[1] - 1,
            dateBits[2],
            Number.isFinite(timeBits[0]) ? timeBits[0] : 0,
            Number.isFinite(timeBits[1]) ? timeBits[1] : 0,
            Number.isFinite(timeBits[2]) ? timeBits[2] : 0
        ).getTime();
    }

    function formatAxisTime(value, showDate) {
        const number = toNumber(value);
        if (number === null) {
            return "";
        }
        const date = new Date(number);
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        const hour = String(date.getHours()).padStart(2, "0");
        const minute = String(date.getMinutes()).padStart(2, "0");
        return showDate ? `${month}-${day} ${hour}:${minute}` : `${hour}:${minute}`;
    }

    function formatShortDate(value) {
        const number = toNumber(value);
        if (number === null) {
            return "";
        }
        const date = new Date(number);
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${month}-${day}`;
    }

    function setText(element, value) {
        if (!element) {
            return;
        }
        element.textContent = value;
    }

    function setClassName(element, value) {
        if (!element) {
            return;
        }
        element.className = value;
    }

    function flashElement(element) {
        if (!element) {
            return;
        }
        element.classList.remove("flash-update");
        void element.offsetWidth;
        element.classList.add("flash-update");
    }

    function flashChildren(container, selector) {
        if (!container) {
            return;
        }
        container.querySelectorAll(selector).forEach((node, index) => {
            window.setTimeout(() => flashElement(node), index * 50);
        });
    }

    function setChartOverlay(message, hidden) {
        if (!chartOverlay) {
            return;
        }
        chartOverlay.textContent = message;
        chartOverlay.hidden = Boolean(hidden);
    }

    function setTopProgress(active) {
        if (!topProgress) {
            return;
        }
        if (active) {
            if (topProgressHideTimer) {
                window.clearTimeout(topProgressHideTimer);
                topProgressHideTimer = null;
            }
            topProgressStartedAt = Date.now();
            topProgress.classList.add("is-active");
            return;
        }
        const elapsed = Date.now() - topProgressStartedAt;
        const delay = Math.max(0, 900 - elapsed);
        if (topProgressHideTimer) {
            window.clearTimeout(topProgressHideTimer);
        }
        topProgressHideTimer = window.setTimeout(() => {
            topProgress.classList.remove("is-active");
            topProgressHideTimer = null;
        }, delay);
    }

    function resetRefreshCountdown() {
        state.nextRefreshAt = Date.now() + REFRESH_INTERVAL_MS;
        updateRefreshCountdown();
    }

    function updateRefreshCountdown() {
        if (!refreshCountdownLabel || !refreshCountdownBar) {
            return;
        }
        if (!state.nextRefreshAt) {
            state.nextRefreshAt = Date.now() + REFRESH_INTERVAL_MS;
        }
        const remaining = Math.max(0, state.nextRefreshAt - Date.now());
        const elapsed = Math.max(0, REFRESH_INTERVAL_MS - remaining);
        const percent = Math.max(0, Math.min(100, elapsed / REFRESH_INTERVAL_MS * 100));
        refreshCountdownBar.style.width = `${percent}%`;
        refreshCountdownLabel.textContent = `下次刷新 ${Math.ceil(remaining / 1000)} 秒`;
    }

    function startRefreshCountdown() {
        if (countdownTimer) {
            window.clearInterval(countdownTimer);
        }
        resetRefreshCountdown();
        countdownTimer = window.setInterval(updateRefreshCountdown, 250);
    }

    function applyThresholds(thresholds) {
        const normalized = thresholds || null;
        state.thresholds = normalized;
        if (!normalized || !normalized.popup_enabled) {
            closeThresholdModal();
        }
    }

    function setAlertConfigStatus() {}

    function applyAlertConfig(config) {
        const normalized = config || {};
        applyThresholds({
            trigger: normalized.trigger_threshold,
            popup_enabled: normalized.popup_enabled,
        });
        return normalized;

        if (triggerThresholdInput) {
            triggerThresholdInput.value = toNumber(normalized.trigger_threshold) == null ? "2.0" : String(normalized.trigger_threshold);
        }
        if (cooldownMinutesInput) {
            cooldownMinutesInput.value = toNumber(normalized.cooldown_minutes) == null ? "10" : String(normalized.cooldown_minutes);
        }
        if (popupEnabledInput) {
            popupEnabledInput.checked = Boolean(normalized.popup_enabled);
        }
        if (!normalized.popup_enabled) {
            closeThresholdModal();
        }

        const email = normalized.email || {};
        if (emailEnabledInput) {
            emailEnabledInput.checked = Boolean(email.enabled);
        }
        if (emailHostInput) {
            emailHostInput.value = email.smtp_host || "";
        }
        if (emailPortInput) {
            emailPortInput.value = email.smtp_port == null ? "465" : String(email.smtp_port);
        }
        if (emailSecurityInput) {
            emailSecurityInput.value = email.security || "ssl";
        }
        if (emailSenderInput) {
            emailSenderInput.value = email.sender || "";
        }
        if (emailRecipientsInput) {
            emailRecipientsInput.value = email.recipients || "";
        }
        if (emailUsernameInput) {
            emailUsernameInput.value = email.username || "";
        }
        if (emailPasswordInput) {
            emailPasswordInput.value = email.password || "";
        }
        if (emailSubjectPrefixInput) {
            emailSubjectPrefixInput.value = email.subject_prefix || "[升贴水提醒]";
        }

        const feishu = normalized.feishu || {};
        if (feishuEnabledInput) {
            feishuEnabledInput.checked = Boolean(feishu.enabled);
        }
        if (feishuWebhookInput) {
            feishuWebhookInput.value = feishu.webhook_url || "";
        }
        if (feishuSecretInput) {
            feishuSecretInput.value = feishu.secret || "";
        }

        const wecom = normalized.wecom || {};
        if (wecomEnabledInput) {
            wecomEnabledInput.checked = Boolean(wecom.enabled);
        }
        if (wecomWebhookInput) {
            wecomWebhookInput.value = wecom.webhook_url || "";
        }
    }

    function summarizeAlertTest(results) {
        if (!Array.isArray(results) || !results.length) {
            return "没有可用的通知渠道";
        }
        return results.map(item => `${item.channel}: ${item.status}`).join(" / ");
    }

    function buildThresholdPromptKey(mainContract, threshold) {
        if (!mainContract) {
            return "";
        }
        return [
            state.selectedSymbol,
            mainContract.contract_code || "",
            mainContract.quote_time || "",
            String(threshold || ""),
        ].join("|");
    }

    function openThresholdModal(mainContract, threshold) {
        if (!thresholdModal || !thresholdModalBody || !mainContract) {
            return;
        }
        thresholdModalBody.innerHTML = `
            <div class="threshold-modal-highlight">
                <strong>${escapeHTML(mainContract.contract_code || state.selectedSymbol)}</strong>
                <div class="threshold-modal-rate ${directionClass(mainContract.premium_rate)}">${escapeHTML(formatBasisRate(mainContract.premium_rate, 3))}</div>
            </div>
            <div class="threshold-modal-meta">
                <div class="threshold-modal-meta-row">
                    <span>触发阈值</span>
                    <strong>±${escapeHTML(formatNumber(threshold, 3))}%</strong>
                </div>
                <div class="threshold-modal-meta-row">
                    <span>升贴水点数</span>
                    <strong class="${directionClass(mainContract.premium_points)}">${escapeHTML(formatBasisPoints(mainContract.premium_points, 2))}</strong>
                </div>
                <div class="threshold-modal-meta-row">
                    <span>数据时间</span>
                    <strong>${escapeHTML(mainContract.quote_time || "--")}</strong>
                </div>
                <div class="threshold-modal-meta-row">
                    <span>数据质量</span>
                    <strong>${escapeHTML(qualityText(mainContract.data_quality))}</strong>
                </div>
            </div>
        `;
        thresholdModal.hidden = false;
    }

    function closeThresholdModal() {
        if (!thresholdModal) {
            return;
        }
        thresholdModal.hidden = true;
    }

    function handleThresholdPrompt(selected) {
        state.lastSelectedSnapshot = selected || null;
        const config = state.thresholds || {};
        const mainContract = selected && selected.main_contract ? selected.main_contract : null;
        const threshold = Math.abs(toNumber(config.trigger) || 0);
        if (!config.popup_enabled || !mainContract || threshold <= 0) {
            return;
        }
        const premiumRate = Math.abs(toNumber(mainContract.premium_rate) || 0);
        if (premiumRate < threshold) {
            return;
        }
        const promptKey = buildThresholdPromptKey(mainContract, threshold);
        if (!promptKey || promptKey === state.lastThresholdPromptKey) {
            return;
        }
        state.lastThresholdPromptKey = promptKey;
        openThresholdModal(mainContract, threshold);
    }

    async function fetchAlertConfig() {
        return null;
        const payload = await fetchJSON("/api/alerts/config");
        applyAlertConfig(payload.config || {});
        setAlertConfigStatus("配置已加载", "success");
        if (state.lastSelectedSnapshot) {
            handleThresholdPrompt(state.lastSelectedSnapshot);
        }
        return payload.config || {};
    }

    async function saveAlertConfig() {
        return null;
        const payload = readAlertConfigForm();
        setAlertConfigStatus("正在保存...", "");
        if (saveAlertConfigButton) {
            saveAlertConfigButton.disabled = true;
        }
        try {
            const response = await fetch("/api/alerts/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || "save failed");
            }
            applyAlertConfig(data.config || {});
            setAlertConfigStatus("配置已保存", "success");
            if (state.lastSelectedSnapshot) {
                handleThresholdPrompt(state.lastSelectedSnapshot);
            }
        } catch (error) {
            setAlertConfigStatus(`保存失败: ${error.message || "未知错误"}`, "error");
        } finally {
            if (saveAlertConfigButton) {
                saveAlertConfigButton.disabled = false;
            }
        }
    }

    async function sendAlertTest() {
        setAlertConfigStatus("正在发送测试通知...", "");
        if (sendAlertTestButton) {
            sendAlertTestButton.disabled = true;
        }
        try {
            const response = await fetch("/api/alerts/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || "test failed");
            }
            setAlertConfigStatus(`测试结果: ${summarizeAlertTest(data.results)}`, "success");
        } catch (error) {
            setAlertConfigStatus(`测试失败: ${error.message || "未知错误"}`, "error");
        } finally {
            if (sendAlertTestButton) {
                sendAlertTestButton.disabled = false;
            }
        }
    }

    function ensureChartShell() {
        if (!chartWrap) {
            return;
        }
        if (chartMount && chartOverlay) {
            return;
        }

        chartWrap.innerHTML = "";

        chartMount = document.createElement("div");
        chartMount.id = "premiumChartMount";
        chartMount.className = "chart-stage";
        chartMount.setAttribute("aria-label", "升贴水率走势");
        chartWrap.appendChild(chartMount);

        chartOverlay = document.createElement("div");
        chartOverlay.id = "chartOverlay";
        chartOverlay.className = "chart-overlay";
        chartOverlay.hidden = true;
        chartOverlay.textContent = "正在准备图表数据...";
        chartWrap.appendChild(chartOverlay);
    }

    function renderSourceCatalog() {
        if (!sourceCatalogGrid) {
            return;
        }
        sourceCatalogGrid.innerHTML = SOURCE_CATALOG.map(item => `
            <article class="source-catalog-card" data-source-key="${escapeHTML(item.key)}">
                <div class="source-catalog-head">
                    <div class="source-catalog-name">${escapeHTML(item.name)}</div>
                    ${renderExternalLink(item.url, "打开", "source-catalog-link")}
                </div>
                <div class="source-catalog-url">${escapeHTML(item.url)}</div>
                <p class="source-catalog-desc">${escapeHTML(item.intro)}</p>
            </article>
        `).join("");
    }

    function highlightSourceCatalog(activeKeys) {
        if (!sourceCatalogGrid) {
            return;
        }
        const activeSet = new Set((activeKeys || []).filter(Boolean));
        sourceCatalogGrid.querySelectorAll(".source-catalog-card[data-source-key]").forEach(card => {
            const key = card.getAttribute("data-source-key");
            card.classList.toggle("is-active", activeSet.has(key));
        });
    }

    function getIntradayWindow(points) {
        if (!Array.isArray(points)) {
            return [];
        }
        return points.length > CHART_WINDOW_POINTS
            ? points.slice(-CHART_WINDOW_POINTS)
            : points.slice();
    }

    function getAxisBounds(points) {
        if (!Array.isArray(points) || points.length === 0) {
            return { min: undefined, max: undefined };
        }
        if (points.length === 1) {
            return {
                min: points[0].x - 5 * 60 * 1000,
                max: points[0].x + 5 * 60 * 1000,
            };
        }
        const min = points[0].x;
        const max = points[points.length - 1].x;
        const pad = Math.max((max - min) * 0.06, 90 * 1000);
        return {
            min: min - pad,
            max: max + pad,
        };
    }

    function buildChartPoint(point, useDailyTime) {
        const x = parseTimestamp(point.timestamp, useDailyTime);
        const y = toNumber(point.premium_rate);
        const futuresPrice = toNumber(point.futures_price);
        const indexPrice = toNumber(point.index_price);
        if (x === null || y === null) {
            return null;
        }
        return {
            x,
            y,
            futuresPrice,
            indexPrice,
            premiumPoints: toNumber(point.premium_points),
            label: point.timestamp,
            contractCode: point.contract_code || "",
        };
    }

    function createLinearScale(domainMin, domainMax, rangeMin, rangeMax) {
        if (!Number.isFinite(domainMin) || !Number.isFinite(domainMax) || domainMin === domainMax) {
            const center = (rangeMin + rangeMax) / 2;
            return () => center;
        }
        const factor = (rangeMax - rangeMin) / (domainMax - domainMin);
        return value => rangeMin + (value - domainMin) * factor;
    }

    function buildSvgPath(points, xMapper, yMapper) {
        if (!Array.isArray(points) || points.length === 0) {
            return "";
        }
        return points.map((point, index) => {
            const x = xMapper(point, index).toFixed(2);
            const y = yMapper(point, index).toFixed(2);
            return `${index === 0 ? "M" : "L"} ${x} ${y}`;
        }).join(" ");
    }

    function buildSvgArea(points, xMapper, yMapper, baselineY) {
        if (!Array.isArray(points) || points.length < 2) {
            return "";
        }
        const topPath = buildSvgPath(points, xMapper, yMapper);
        const lastIndex = points.length - 1;
        return `${topPath} L ${xMapper(points[lastIndex], lastIndex).toFixed(2)} ${baselineY.toFixed(2)} L ${xMapper(points[0], 0).toFixed(2)} ${baselineY.toFixed(2)} Z`;
    }

    function buildTickIndexes(length, count) {
        if (!Number.isFinite(length) || length <= 0) {
            return [];
        }
        if (length === 1) {
            return [0];
        }
        const finalCount = Math.min(count, length);
        const indexes = [];
        for (let i = 0; i < finalCount; i += 1) {
            const index = Math.round(i * (length - 1) / (finalCount - 1));
            if (indexes[indexes.length - 1] !== index) {
                indexes.push(index);
            }
        }
        return indexes;
    }

    function buildNumericTicks(minValue, maxValue, count) {
        if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
            return [0];
        }
        if (minValue === maxValue) {
            return [minValue];
        }
        const ticks = [];
        for (let i = 0; i < count; i += 1) {
            ticks.push(minValue + (maxValue - minValue) * (i / (count - 1)));
        }
        return ticks;
    }

    function niceNumber(value, round) {
        if (!Number.isFinite(value) || value <= 0) {
            return 1;
        }
        const exponent = Math.floor(Math.log10(value));
        const fraction = value / Math.pow(10, exponent);
        let niceFraction;
        if (round) {
            if (fraction < 1.5) {
                niceFraction = 1;
            } else if (fraction < 3) {
                niceFraction = 2;
            } else if (fraction < 7) {
                niceFraction = 5;
            } else {
                niceFraction = 10;
            }
        } else if (fraction <= 1) {
            niceFraction = 1;
        } else if (fraction <= 2) {
            niceFraction = 2;
        } else if (fraction <= 5) {
            niceFraction = 5;
        } else {
            niceFraction = 10;
        }
        return niceFraction * Math.pow(10, exponent);
    }

    function buildRateDomain(values, tickCount) {
        const validValues = values.filter(Number.isFinite);
        if (!validValues.length) {
            return { min: -1, max: 1, ticks: [-1, -0.5, 0, 0.5, 1] };
        }
        let minValue = Math.min(...validValues, 0);
        let maxValue = Math.max(...validValues, 0);
        if (minValue === maxValue) {
            const pad = Math.max(Math.abs(minValue) * 0.2, 0.25);
            minValue -= pad;
            maxValue += pad;
        }
        const span = maxValue - minValue;
        const step = niceNumber(span / Math.max((tickCount || 6) - 1, 1), true);
        const niceMin = Math.floor(minValue / step) * step;
        const niceMax = Math.ceil(maxValue / step) * step;
        const ticks = [];
        for (let value = niceMin; value <= niceMax + step * 0.5; value += step) {
            ticks.push(Number(value.toFixed(8)));
        }
        return { min: niceMin, max: niceMax, ticks };
    }

    function buildPriceDomain(values, tickCount) {
        const validValues = values.filter(Number.isFinite);
        if (!validValues.length) {
            return { min: 0, max: 1, ticks: [0, 1] };
        }
        let minValue = Math.min(...validValues);
        let maxValue = Math.max(...validValues);
        if (minValue === maxValue) {
            const pad = Math.max(Math.abs(minValue) * 0.002, 1);
            minValue -= pad;
            maxValue += pad;
        }
        const span = maxValue - minValue;
        const paddedMin = minValue - span * 0.18;
        const paddedMax = maxValue + span * 0.18;
        const step = niceNumber((paddedMax - paddedMin) / Math.max((tickCount || 6) - 1, 1), true);
        const niceMin = Math.floor(paddedMin / step) * step;
        const niceMax = Math.ceil(paddedMax / step) * step;
        const ticks = [];
        for (let value = niceMin; value <= niceMax + step * 0.5; value += step) {
            ticks.push(Number(value.toFixed(8)));
        }
        return { min: niceMin, max: niceMax, ticks };
    }

    function summarizeChartPoints(points) {
        const validPoints = (Array.isArray(points) ? points : []).filter(point => Number.isFinite(point.y));
        if (!validPoints.length) {
            return null;
        }
        const values = validPoints.map(point => point.y);
        const latest = validPoints[validPoints.length - 1];
        const minPoint = validPoints.reduce((best, point) => point.y < best.y ? point : best, validPoints[0]);
        const maxPoint = validPoints.reduce((best, point) => point.y > best.y ? point : best, validPoints[0]);
        const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
        return { latest, minPoint, maxPoint, avg, count: validPoints.length };
    }

    function renderOverview(overview) {
        if (!summaryGrid) {
            return;
        }

        const cards = Array.isArray(overview.cards) ? overview.cards : [];
        const selected = overview.selected || {};
        applyThresholds(overview.thresholds || null);

        setText(generatedAt, overview.generated_at || "--");
        setText(selectedSymbolLabel, overview.selected_symbol || state.selectedSymbol);
        setClassName(heroQuality, `quality-pill ${qualityClass(selected.main_contract && selected.main_contract.data_quality)}`);
        setText(heroQuality, qualityText(selected.main_contract && selected.main_contract.data_quality));

        summaryGrid.innerHTML = cards.map((card, index) => {
            const basisPercentile = card.basis_percentile_30d == null ? card.percentile_30d : card.basis_percentile_30d;
            const strength = clampPercent(
                basisPercentile == null
                    ? Math.min(Math.abs(toNumber(card.premium_rate) || 0) * 20, 100)
                    : basisPercentile
            );

            return `
                <article class="summary-card ${card.symbol === state.selectedSymbol ? "is-active" : ""}" data-symbol="${escapeHTML(card.symbol)}" style="animation-delay:${index * 60}ms">
                    <div class="summary-head">
                        <div>
                            <h3>${escapeHTML(card.symbol)} ${escapeHTML(card.symbol_name)}</h3>
                            <div class="summary-sub">${escapeHTML(card.contract_code || "--")} · ${escapeHTML(formatFreshness(card.freshness_seconds))}</div>
                        </div>
                        <span class="quality-pill ${qualityClass(card.data_quality)}">${escapeHTML(qualityText(card.data_quality))}</span>
                    </div>

                    <div class="summary-rate ${directionClass(card.premium_rate)}">${formatBasisRate(card.premium_rate, 3)}</div>
                    <div class="summary-points ${directionClass(card.premium_points)}">${formatBasisPoints(card.premium_points, 2)}</div>

                    <div class="summary-bar">
                        <div class="bar-track">
                            <span class="bar-fill ${directionClass(card.premium_rate)}" style="width:${strength}%"></span>
                        </div>
                    </div>

                    <div class="summary-foot">
                        <div class="mini-stat">
                            <span>幅度分位</span>
                            <strong>${basisPercentile == null ? "--" : `${formatNumber(basisPercentile, 1)}%`}</strong>
                        </div>
                        <div class="mini-stat">
                            <span>Z</span>
                            <strong class="${directionClass(card.z_score_30d)}">${card.z_score_30d == null ? "--" : formatSigned(card.z_score_30d, 2)}</strong>
                        </div>
                        <div class="mini-stat">
                            <span>期 / 指</span>
                            <strong>${formatNumber(card.futures_price, 1)} / ${formatNumber(card.index_price, 1)}</strong>
                        </div>
                        <div class="mini-stat">
                            <span>MA5</span>
                            <strong class="${directionClass(card.ma5)}">${card.ma5 == null ? "--" : formatBasisRate(card.ma5, 2)}</strong>
                        </div>
                    </div>
                </article>
            `;
        }).join("");

        flashChildren(summaryGrid, ".summary-card");
    }

    function renderDetails(details) {
        const metrics = details.metrics || {};
        const validation = details.validation || {};
        const sources = details.sources || {};
        const stats = details.stats_30d || {};
        const alerts = Array.isArray(details.alerts) ? details.alerts : [];
        const basisCurve = Array.isArray(details.basis_curve) ? details.basis_curve : [];
        const mostActiveContract = basisCurve.length
            ? basisCurve.reduce((best, item) => ((toNumber(item.volume) || 0) > (toNumber(best.volume) || 0) ? item : best), basisCurve[0])
            : null;
        const maGap = toNumber(metrics.premium_rate) !== null && toNumber(stats.ma5) !== null
            ? toNumber(metrics.premium_rate) - toNumber(stats.ma5)
            : null;
        const annualizedBasisRate = getAnnualizedBasisRate(metrics);
        const basisPercentile = metrics.basis_percentile_30d == null ? metrics.percentile_30d : metrics.basis_percentile_30d;
        const annualizedTone = annualizedBasisTone(annualizedBasisRate);

        setText(chartTitle, `${details.symbol || state.selectedSymbol} ${details.symbol_name || ""} 期货 vs 指数价格`);
        setClassName(chartQuality, `quality-pill ${qualityClass(validation.data_quality)}`);
        setText(chartQuality, qualityText(validation.data_quality));
        setText(detailSubtitle, `${metrics.contract_code || "--"} · ${formatQuoteClock(metrics.quote_time)}`);
        highlightSourceCatalog([sources.futures, sources.index, "cffex_daily", "index_daily"]);

        const headlineItems = [
            {
                label: "升贴水率",
                value: formatBasisRate(metrics.premium_rate, 3),
                meta: `较 MA5 ${formatBasisGap(maGap, 3)}`,
                tone: metrics.premium_rate,
            },
            {
                label: "升贴水点",
                value: formatBasisPoints(metrics.premium_points, 2),
                meta: `指数 ${formatNumber(metrics.index_price, 2)}`,
                tone: metrics.premium_points,
            },
            {
                label: "年化收敛",
                value: formatAnnualizedBasis(metrics, 2),
                meta: `到期 ${metrics.days_to_expiry == null ? "--" : `${metrics.days_to_expiry}天`}`,
                tone: annualizedTone,
            },
            {
                label: "幅度分位",
                value: basisPercentile == null ? "--" : `${formatNumber(basisPercentile, 1)}%`,
                meta: `Z ${metrics.z_score_30d == null ? "--" : formatSigned(metrics.z_score_30d, 2)}`,
                tone: metrics.z_score_30d,
            },
        ];

        if (headlineStrip) {
            headlineStrip.innerHTML = headlineItems.map((item, index) => `
                <div class="headline-item" style="animation-delay:${index * 50}ms">
                    <div class="headline-label">${escapeHTML(item.label)}</div>
                    <div class="headline-value ${directionClass(item.tone)}">${escapeHTML(item.value)}</div>
                    <div class="headline-meta">${escapeHTML(item.meta)}</div>
                </div>
            `).join("");
        }

        const signalItems = [
            {
                glyph: "偏",
                title: "相对 MA5",
                value: formatBasisGap(maGap, 3),
                note: `MA5 ${stats.ma5 == null ? "--" : formatBasisRate(stats.ma5, 3)}`,
                tone: maGap,
            },
            {
                glyph: "位",
                title: "幅度分位",
                value: basisPercentile == null ? "--" : `${formatNumber(basisPercentile, 1)}%`,
                note: `30日 Z ${metrics.z_score_30d == null ? "--" : formatSigned(metrics.z_score_30d, 2)}`,
                tone: metrics.z_score_30d,
            },
            {
                glyph: "年",
                title: "期限收敛",
                value: formatAnnualizedBasis(metrics, 2),
                note: `到期 ${metrics.days_to_expiry == null ? "--" : `${metrics.days_to_expiry}天`} · 活跃 ${mostActiveContract ? mostActiveContract.contract_code : "--"}`,
                tone: annualizedTone,
            },
            {
                glyph: "质",
                title: "数据质量",
                value: qualityText(validation.data_quality),
                note: `${sourceText(sources.futures)} / ${sourceText(sources.index)}`,
                tone: null,
            },
        ];

        if (signalStack) {
            signalStack.innerHTML = signalItems.map((item, index) => `
                <div class="signal-card" style="animation-delay:${index * 60}ms">
                    <div class="signal-glyph">${escapeHTML(item.glyph)}</div>
                    <div class="signal-copy">
                        <strong>${escapeHTML(item.title)}</strong>
                        <div class="signal-value ${directionClass(item.tone)}">${escapeHTML(item.value)}</div>
                        <p>${escapeHTML(item.note)}</p>
                    </div>
                </div>
            `).join("");
        }

        const metricRows = [
            { label: "主力合约", value: metrics.contract_code || "--" },
            { label: "期货价格", value: formatNumber(metrics.futures_price, 2), tone: metrics.futures_price },
            { label: "指数价格", value: formatNumber(metrics.index_price, 2), tone: metrics.index_price },
            { label: "指数涨跌", value: formatPercent(metrics.index_change_pct, 2), tone: metrics.index_change_pct },
            { label: "成交量", value: formatCount(metrics.volume) },
            { label: "持仓量", value: formatCount(metrics.open_interest) },
        ];

        if (metricGrid) {
            metricGrid.innerHTML = metricRows.map((item, index) => `
                <div class="metric-card" style="animation-delay:${index * 45}ms">
                    <div class="metric-label">${escapeHTML(item.label)}</div>
                    <div class="metric-value ${directionClass(item.tone)}">${escapeHTML(item.value)}</div>
                </div>
            `).join("");
        }

        if (sourceBox) {
            const futuresMeta = sourceMeta(sources.futures);
            const indexMeta = sourceMeta(sources.index);
            sourceBox.innerHTML = `
                <div class="info-box-title">当前来源</div>
                <div class="info-box-body">
                    <div class="info-row">
                        <span class="info-key">实时期货</span>
                        <strong class="info-value">${escapeHTML(futuresMeta.name)}</strong>
                    </div>
                    <div class="info-row">
                        <span class="info-key">实时指数</span>
                        <strong class="info-value">${escapeHTML(indexMeta.name)}</strong>
                    </div>
                    <div class="info-row">
                        <span class="info-key">30日背景</span>
                        <strong class="info-value">中金所日线 + 指数历史日线</strong>
                    </div>
                </div>
            `;
        }

        if (opsHeaderBadge) {
            opsHeaderBadge.innerHTML = `
                <span class="ops-badge-label">运行状态</span>
                <strong class="quality-pill ${qualityClass(validation.data_quality)}">${escapeHTML(qualityText(validation.data_quality))}</strong>
            `;
        }

        if (qualityBox) {
            qualityBox.innerHTML = `
                <div class="info-box-title">质量说明</div>
                <div class="info-box-body">
                    <div class="info-row">
                        <span class="info-key">状态</span>
                        <span class="quality-pill ${qualityClass(validation.data_quality)}">${escapeHTML(qualityText(validation.data_quality))}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-key">新鲜度</span>
                        <strong class="info-value">${escapeHTML(formatFreshnessPlain(validation.freshness_seconds))}</strong>
                    </div>
                    <div class="info-row">
                        <span class="info-key">告警数</span>
                        <strong class="info-value">${alerts.length}</strong>
                    </div>
                    <div class="info-row">
                        <span class="info-key">主备偏差</span>
                        <strong class="info-value">${validation.primary_backup_gap_pct == null ? "--" : `${formatNumber(validation.primary_backup_gap_pct, 3)}%`}</strong>
                    </div>
                    <div class="info-row">
                        <span class="info-key">说明</span>
                        <span class="info-note">${escapeHTML(validation.quality_reason || "当前未发现异常")}</span>
                    </div>
                </div>
            `;
        }

        if (statusPulseBox) {
            const thresholds = state.thresholds || {};
            const triggerValue = toNumber(thresholds.trigger);
            const warningValue = toNumber(thresholds.warning);
            const alertValue = toNumber(thresholds.alert);
            const popupText = thresholds.popup_enabled ? "开启" : "关闭";
            statusPulseBox.innerHTML = `
                <div class="info-box-title">状态摘要</div>
                <div class="status-pulse-head">
                    <div class="status-pulse-symbol">
                        <strong>${escapeHTML(details.symbol || state.selectedSymbol)}</strong>
                        <span>${escapeHTML((details.symbol_name || "").trim() || "主力跟踪")}</span>
                    </div>
                    <div class="status-pulse-contract">${escapeHTML(metrics.contract_code || "--")}</div>
                </div>
                <div class="status-pulse-grid">
                    <div class="status-pulse-stat">
                        <span>弹窗阈值</span>
                        <strong>${triggerValue == null ? "--" : `±${formatNumber(triggerValue, 2)}%`}</strong>
                    </div>
                    <div class="status-pulse-stat">
                        <span>预警阈值</span>
                        <strong>${warningValue == null ? "--" : `±${formatNumber(warningValue, 2)}%`}</strong>
                    </div>
                    <div class="status-pulse-stat">
                        <span>严重阈值</span>
                        <strong>${alertValue == null ? "--" : `±${formatNumber(alertValue, 2)}%`}</strong>
                    </div>
                    <div class="status-pulse-stat">
                        <span>弹窗状态</span>
                        <strong>${escapeHTML(popupText)}</strong>
                    </div>
                </div>
                <div class="status-pulse-notes">
                    <span class="status-note">时间 ${escapeHTML(formatQuoteClock(metrics.quote_time))}</span>
                    <span class="status-note">鲜度 ${escapeHTML(formatFreshnessPlain(validation.freshness_seconds))}</span>
                    <span class="status-note">告警 ${alerts.length} 条</span>
                    <span class="status-note">偏差 ${validation.primary_backup_gap_pct == null ? "--" : `${formatNumber(validation.primary_backup_gap_pct, 3)}%`}</span>
                </div>
            `;
        }

        flashChildren(headlineStrip, ".headline-item");
        flashChildren(signalStack, ".signal-card");
        flashChildren(metricGrid, ".metric-card");
        flashElement(sourceBox);
        flashElement(qualityBox);
        flashElement(opsHeaderBadge);
        flashElement(statusPulseBox);
    }

    function renderContracts(contracts) {
        if (!contractTableBody) {
            return;
        }

        if (!Array.isArray(contracts) || contracts.length === 0) {
            contractTableBody.innerHTML = '<tr><td colspan="11" class="empty-row">当前没有可展示的合约。</td></tr>';
            return;
        }

        contractTableBody.innerHTML = contracts.map(contract => {
            const rateWidth = Math.min(Math.abs(toNumber(contract.premium_rate) || 0) / 5 * 100, 100);
            const annualizedBasisRate = getAnnualizedBasisRate(contract);
            const annualizedTone = annualizedBasisTone(annualizedBasisRate);
            const annualWidth = Math.min(Math.abs(annualizedBasisRate || 0) / 30 * 100, 100);
            const volumeValue = toNumber(contract.volume) || 0;
            const oiValue = toNumber(contract.open_interest) || 0;

            return `
                <tr class="${contract.is_main ? "is-main" : ""}">
                    <td>
                        <span class="contract-code">
                            ${contract.is_main ? '<span class="main-dot"></span>' : ""}
                            <strong>${escapeHTML(contract.contract_code || "--")}</strong>
                        </span>
                    </td>
                    <td><span class="chip">${escapeHTML(contract.position || "--")}</span></td>
                    <td>${formatNumber(contract.futures_price, 2)}</td>
                    <td>${formatNumber(contract.index_price, 2)}</td>
                    <td class="${directionClass(contract.premium_points)}">${formatBasisPoints(contract.premium_points, 2)}</td>
                    <td>
                        <div class="table-metric">
                            <strong class="${directionClass(contract.premium_rate)}">${formatBasisRate(contract.premium_rate, 3)}</strong>
                            <span class="metric-bar"><i class="${directionClass(contract.premium_rate)}" style="width:${rateWidth}%"></i></span>
                        </div>
                    </td>
                    <td>
                        <div class="table-metric">
                            <strong class="${directionClass(annualizedTone)}">${formatAnnualizedBasis(contract, 2)}</strong>
                            <span class="metric-bar"><i class="${directionClass(annualizedTone)}" style="width:${annualWidth}%"></i></span>
                        </div>
                    </td>
                    <td>${formatCount(volumeValue)}</td>
                    <td>${formatCount(oiValue)}</td>
                    <td>${contract.days_to_expiry == null ? "--" : escapeHTML(contract.days_to_expiry)}</td>
                    <td><span class="status-chip ${qualityClass(contract.data_quality)}">${escapeHTML(qualityText(contract.data_quality))}</span></td>
                </tr>
            `;
        }).join("");
    }

    function renderAlerts(alerts, qualitySummary) {
        if (!alertList) {
            return;
        }

        const counts = qualitySummary && qualitySummary.counts ? qualitySummary.counts : {};
        const countText = Object.keys(counts).length
            ? Object.entries(counts).map(([key, value]) => `${qualityText(key)} ${value}`).join(" / ")
            : "无分布数据";
        const triggerThreshold = state.thresholds && toNumber(state.thresholds.trigger);
        const summaryText = qualitySummary
            ? `主状态 ${qualityText(qualitySummary.main_quality)} · 新鲜度 ${formatFreshnessPlain(qualitySummary.freshness_seconds)} · ${countText}${triggerThreshold == null ? "" : ` · 弹窗/通知阈值 ±${formatNumber(triggerThreshold, 2)}%`}`
            : "暂无质量摘要";

        const items = [
            `
                <div class="alert-item ok">
                    <strong>质量摘要</strong>
                    <span>${escapeHTML(summaryText)}</span>
                </div>
            `,
        ];

        if (Array.isArray(alerts) && alerts.length > 0) {
            alerts.forEach(item => {
                items.push(`
                    <div class="alert-item ${escapeHTML(item.level || "warning")}">
                        <strong>${escapeHTML(item.message || "--")}</strong>
                        <span>${escapeHTML(item.timestamp || "--")}</span>
                    </div>
                `);
            });
        } else {
            items.push('<div class="empty-alert">当前没有超过阈值的告警。</div>');
        }

        alertList.innerHTML = items.join("");
        flashChildren(alertList, ".alert-item");
    }

    function renderChart(intraday, daily, selected) {
        ensureChartShell();
        if (!chartMount) {
            return;
        }

        const intradayAllPoints = Array.isArray(intraday.points)
            ? intraday.points.map(point => buildChartPoint(point, false)).filter(Boolean)
            : [];
        const intradayPoints = getIntradayWindow(intradayAllPoints);
        const dailyRaw = Array.isArray(daily.raw)
            ? daily.raw.map(point => buildChartPoint(point, true)).filter(Boolean)
            : [];
        const dailySmooth = Array.isArray(daily.smoothed)
            ? daily.smoothed.map(point => buildChartPoint(point, true)).filter(Boolean)
            : [];
        const chartSymbol = selected.symbol || state.selectedSymbol;
        const showDailySeries = intradayPoints.length === 0;
        const allPoints = showDailySeries ? [...dailyRaw, ...dailySmooth] : intradayPoints;

        if (!allPoints.length) {
            chartMount.innerHTML = '<div class="chart-empty">当前没有可绘制的走势数据。</div>';
            setChartOverlay("", true);
            return;
        }

        setChartOverlay("", true);

        const width = 1100;
        const height = 400;
        const margin = { top: 42, right: 28, bottom: 58, left: 92 };
        const plotWidth = width - margin.left - margin.right;
        const plotHeight = height - margin.top - margin.bottom;

        const yValues = allPoints.map(point => point.y).filter(Number.isFinite);
        let yMin = Math.min(...yValues);
        let yMax = Math.max(...yValues);
        if (yMin === yMax) {
            const pad = Math.max(Math.abs(yMin) * 0.2, 0.2);
            yMin -= pad;
            yMax += pad;
        } else {
            const pad = Math.max((yMax - yMin) * 0.14, 0.12);
            yMin -= pad;
            yMax += pad;
        }

        const intradayBounds = getAxisBounds(intradayPoints);
        const intradayMin = Number.isFinite(intradayBounds.min)
            ? intradayBounds.min
            : (intradayPoints[0] ? intradayPoints[0].x - 5 * 60 * 1000 : 0);
        const intradayMax = Number.isFinite(intradayBounds.max)
            ? intradayBounds.max
            : (intradayPoints[0] ? intradayPoints[0].x + 5 * 60 * 1000 : 1);

        const xIntraday = createLinearScale(intradayMin, intradayMax, margin.left, margin.left + plotWidth);
        const dailyLength = Math.max(dailyRaw.length, dailySmooth.length, 1);
        const xDaily = dailyLength <= 1
            ? () => margin.left + plotWidth / 2
            : createLinearScale(0, dailyLength - 1, margin.left, margin.left + plotWidth);
        const yScale = createLinearScale(yMin, yMax, margin.top + plotHeight, margin.top);
        const yTicks = buildNumericTicks(yMin, yMax, 6);
        const xTickIndexes = intradayPoints.length
            ? buildTickIndexes(intradayPoints.length, 6)
            : buildTickIndexes(Math.max(dailyRaw.length, dailySmooth.length), 6);
        const showDate = intradayPoints.length > 18;
        const plotBottom = margin.top + plotHeight;
        const zeroLine = yMin < 0 && yMax > 0 ? yScale(0) : null;

        const rawPath = showDailySeries ? buildSvgPath(dailyRaw, (_point, index) => xDaily(index), point => yScale(point.y)) : "";
        const smoothPath = showDailySeries ? buildSvgPath(dailySmooth, (_point, index) => xDaily(index), point => yScale(point.y)) : "";
        const smoothArea = showDailySeries ? buildSvgArea(dailySmooth, (_point, index) => xDaily(index), point => yScale(point.y), plotBottom) : "";
        const intradayGlowPath = buildSvgPath(intradayPoints, point => xIntraday(point.x), point => yScale(point.y));
        const intradayPath = intradayGlowPath;
        const lastIntraday = intradayPoints[intradayPoints.length - 1] || null;
        const tonePoint = lastIntraday || allPoints[allPoints.length - 1] || null;
        const realtimeColor = tonePoint && tonePoint.y > 0 ? CHART_COLORS.up : CHART_COLORS.down;
        const realtimeGlowColor = tonePoint && tonePoint.y > 0 ? CHART_COLORS.upGlow : CHART_COLORS.downGlow;

        const xTicksMarkup = xTickIndexes.map(index => {
            const point = intradayPoints.length
                ? intradayPoints[index]
                : (dailySmooth[index] || dailyRaw[index]);
            if (!point) {
                return "";
            }
            const x = intradayPoints.length ? xIntraday(point.x) : xDaily(index);
            const label = intradayPoints.length
                ? formatAxisTime(point.x, showDate)
                : formatShortDate(point.x);
            return `
                <line class="chart-grid-line" x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${plotBottom}" />
                <text class="chart-tick-label" x="${x.toFixed(2)}" y="${height - 18}" text-anchor="middle">${escapeHTML(label)}</text>
            `;
        }).join("");

        const yTicksMarkup = yTicks.map(value => {
            const y = yScale(value);
            return `
                <line class="chart-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${margin.left + plotWidth}" y2="${y.toFixed(2)}" />
                <text class="chart-tick-label" x="${margin.left - 10}" y="${(y + 4).toFixed(2)}" text-anchor="end">${escapeHTML(formatBasisAxis(value))}</text>
            `;
        }).join("");

        const lastPointMarkup = lastIntraday ? `
            <circle cx="${xIntraday(lastIntraday.x).toFixed(2)}" cy="${yScale(lastIntraday.y).toFixed(2)}" r="8" fill="${realtimeGlowColor}"></circle>
            <circle cx="${xIntraday(lastIntraday.x).toFixed(2)}" cy="${yScale(lastIntraday.y).toFixed(2)}" r="4.2" fill="${realtimeColor}" stroke="${CHART_COLORS.realtimePoint}" stroke-width="2"></circle>
        ` : "";

        chartMount.innerHTML = `
            <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHTML(chartSymbol)} 升贴水率走势">
                <defs>
                    <linearGradient id="smoothAreaFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="${CHART_COLORS.smoothFill}" />
                        <stop offset="100%" stop-color="rgba(15, 139, 123, 0.00)" />
                    </linearGradient>
                </defs>

                <rect x="0" y="0" width="${width}" height="${height}" rx="16" fill="${CHART_COLORS.bg}"></rect>

                <g transform="translate(${margin.left}, 18)">
                    ${showDailySeries ? `
                        <circle cx="0" cy="0" r="5" fill="none" stroke="${CHART_COLORS.raw}" stroke-width="2"></circle>
                        <text class="chart-legend-label" x="12" y="4">30日原始</text>

                        <circle cx="92" cy="0" r="5" fill="none" stroke="${CHART_COLORS.smooth}" stroke-width="3"></circle>
                        <text class="chart-legend-label" x="104" y="4">30日平滑</text>
                    ` : `
                        <circle cx="0" cy="0" r="5" fill="${realtimeColor}" stroke="${realtimeColor}" stroke-width="2"></circle>
                        <text class="chart-legend-label" x="12" y="4">${escapeHTML(chartSymbol)} 当日主力</text>
                    `}
                </g>

                <g>
                    ${yTicksMarkup}
                    ${xTicksMarkup}
                    ${zeroLine == null ? "" : `<line x1="${margin.left}" y1="${zeroLine.toFixed(2)}" x2="${margin.left + plotWidth}" y2="${zeroLine.toFixed(2)}" stroke="${CHART_COLORS.axis}" stroke-dasharray="4 4" />`}
                    <line class="chart-axis-line" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${plotBottom}"></line>
                    <line class="chart-axis-line" x1="${margin.left}" y1="${plotBottom}" x2="${margin.left + plotWidth}" y2="${plotBottom}"></line>
                </g>

                <text class="chart-axis-title" x="26" y="${margin.top + plotHeight / 2}" text-anchor="middle" transform="rotate(-90 26 ${margin.top + plotHeight / 2})">升贴水率 (%)</text>
                <text class="chart-axis-title" x="${margin.left + plotWidth / 2}" y="${height - 2}" text-anchor="middle">${intradayPoints.length ? "日内时间" : "交易日期"}</text>

                <g fill="none">
                    ${rawPath ? `<path d="${rawPath}" stroke="${CHART_COLORS.raw}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="7 5" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${smoothPath ? `<path d="${smoothPath}" stroke="${CHART_COLORS.smooth}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${intradayGlowPath ? `<path d="${intradayGlowPath}" stroke="${realtimeGlowColor}" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${intradayPath ? `<path d="${intradayPath}" stroke="${realtimeColor}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                </g>

                ${lastPointMarkup}
            </svg>
        `;
    }

    function renderChartV2(intraday, daily, selected) {
        ensureChartShell();
        if (!chartMount) {
            return;
        }

        const intradayAllPoints = Array.isArray(intraday.points)
            ? intraday.points.map(point => buildChartPoint(point, false)).filter(Boolean)
            : [];
        const intradayPoints = getIntradayWindow(intradayAllPoints);
        const dailyRaw = Array.isArray(daily.raw)
            ? daily.raw.map(point => buildChartPoint(point, true)).filter(Boolean)
            : [];
        const dailySmooth = Array.isArray(daily.smoothed)
            ? daily.smoothed.map(point => buildChartPoint(point, true)).filter(Boolean)
            : [];
        const chartSymbol = selected.symbol || state.selectedSymbol;
        const showDailySeries = intradayPoints.length === 0;
        const allPoints = showDailySeries ? [...dailyRaw, ...dailySmooth] : intradayPoints;

        if (!allPoints.length) {
            chartMount.innerHTML = '<div class="chart-empty">当前没有可绘制的走势数据。</div>';
            setChartOverlay("", true);
            return;
        }

        setChartOverlay("", true);

        const width = 1100;
        const height = 460;
        const margin = { top: 92, right: 92, bottom: 72, left: 96 };
        const plotWidth = width - margin.left - margin.right;
        const plotHeight = height - margin.top - margin.bottom;
        const plotRight = margin.left + plotWidth;
        const plotBottom = margin.top + plotHeight;
        const displayPoints = intradayPoints.length ? intradayPoints : (dailySmooth.length ? dailySmooth : dailyRaw);
        const stats = summarizeChartPoints(displayPoints);
        const yValues = allPoints.map(point => point.y).filter(Number.isFinite);
        if (stats) {
            yValues.push(stats.avg, stats.latest.y, stats.minPoint.y, stats.maxPoint.y);
        }
        const yDomain = buildPriceDomain(yValues, 6);
        const yScale = createLinearScale(yDomain.min, yDomain.max, plotBottom, margin.top);
        const zeroLine = yScale(0);
        const avgLine = stats ? yScale(stats.avg) : null;

        const intradayBounds = getAxisBounds(intradayPoints);
        const intradayMin = Number.isFinite(intradayBounds.min)
            ? intradayBounds.min
            : (intradayPoints[0] ? intradayPoints[0].x - 5 * 60 * 1000 : 0);
        const intradayMax = Number.isFinite(intradayBounds.max)
            ? intradayBounds.max
            : (intradayPoints[0] ? intradayPoints[0].x + 5 * 60 * 1000 : 1);
        const xIntraday = createLinearScale(intradayMin, intradayMax, margin.left, plotRight);
        const dailyLength = Math.max(dailyRaw.length, dailySmooth.length, 1);
        const xDaily = dailyLength <= 1
            ? () => margin.left + plotWidth / 2
            : createLinearScale(0, dailyLength - 1, margin.left, plotRight);
        const xTickIndexes = buildTickIndexes(Math.max(dailyRaw.length, dailySmooth.length), 7);
        const showDate = intradayPoints.length > 48;

        const rawPath = showDailySeries ? buildSvgPath(dailyRaw, (_point, index) => xDaily(index), point => yScale(point.y)) : "";
        const smoothPath = showDailySeries ? buildSvgPath(dailySmooth, (_point, index) => xDaily(index), point => yScale(point.y)) : "";
        const smoothArea = showDailySeries ? buildSvgArea(dailySmooth, (_point, index) => xDaily(index), point => yScale(point.y), plotBottom) : "";
        const intradayGlowPath = buildSvgPath(intradayPoints, point => xIntraday(point.x), point => yScale(point.y));
        const intradayPath = intradayGlowPath;
        const lastIntraday = intradayPoints[intradayPoints.length - 1] || null;
        const tonePoint = (stats && stats.latest) || allPoints[allPoints.length - 1] || null;
        const realtimeColor = tonePoint && tonePoint.y > 0 ? CHART_COLORS.up : CHART_COLORS.down;
        const realtimeGlowColor = tonePoint && tonePoint.y > 0 ? CHART_COLORS.upGlow : CHART_COLORS.downGlow;
        const xForDisplayPoint = point => {
            if (!point) {
                return margin.left;
            }
            if (intradayPoints.length) {
                return xIntraday(point.x);
            }
            return xDaily(Math.max(displayPoints.indexOf(point), 0));
        };

        const xTicksMarkup = intradayPoints.length
            ? buildNumericTicks(intradayMin, intradayMax, 6).map(value => {
                const x = xIntraday(value);
                return `
                    <line class="chart-grid-line" x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${plotBottom}" />
                    <text class="chart-tick-label" x="${x.toFixed(2)}" y="${height - 26}" text-anchor="middle">${escapeHTML(formatAxisTime(value, showDate))}</text>
                `;
            }).join("")
            : xTickIndexes.map(index => {
                const point = dailySmooth[index] || dailyRaw[index];
                if (!point) {
                    return "";
                }
                const x = xDaily(index);
                return `
                    <line class="chart-grid-line" x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${plotBottom}" />
                    <text class="chart-tick-label" x="${x.toFixed(2)}" y="${height - 26}" text-anchor="middle">${escapeHTML(formatShortDate(point.x))}</text>
                `;
            }).join("");
        const yTicksMarkup = yDomain.ticks.map(value => {
            const y = yScale(value);
            return `
                <line class="chart-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${plotRight}" y2="${y.toFixed(2)}" />
                <text class="chart-tick-label" x="${margin.left - 10}" y="${(y + 4).toFixed(2)}" text-anchor="end">${escapeHTML(formatBasisAxis(value))}</text>
            `;
        }).join("");
        const allDiscount = displayPoints.length > 0 && displayPoints.every(point => point.y <= 0);
        const allPremium = displayPoints.length > 0 && displayPoints.every(point => point.y >= 0);
        const highLabel = allDiscount ? "最浅" : (allPremium ? "最高" : "高点");
        const lowLabel = allDiscount ? "最深" : (allPremium ? "最低" : "低点");
        const statItems = stats ? [
            ["最新", formatBasisRate(stats.latest.y, 3)],
            ["均值", formatBasisRate(stats.avg, 3)],
            [highLabel, formatBasisRate(stats.maxPoint.y, 3)],
            [lowLabel, formatBasisRate(stats.minPoint.y, 3)],
            ["样本", `${stats.count} 个点`],
        ] : [];
        const statMarkup = statItems.map((item, index) => {
            const chipWidth = index === 4 ? 86 : 130;
            return `
                <g class="chart-stat-chip" transform="translate(${margin.left + index * 142}, 28)">
                    <rect width="${chipWidth}" height="38" rx="8"></rect>
                    <text class="chart-stat-label" x="11" y="15">${escapeHTML(item[0])}</text>
                    <text class="chart-stat-value" x="11" y="30">${escapeHTML(item[1])}</text>
                </g>
            `;
        }).join("");
        const lastPointMarkup = lastIntraday ? `
            <circle cx="${xIntraday(lastIntraday.x).toFixed(2)}" cy="${yScale(lastIntraday.y).toFixed(2)}" r="8" fill="${realtimeGlowColor}"></circle>
            <circle cx="${xIntraday(lastIntraday.x).toFixed(2)}" cy="${yScale(lastIntraday.y).toFixed(2)}" r="4.2" fill="${realtimeColor}" stroke="${CHART_COLORS.realtimePoint}" stroke-width="2"></circle>
        ` : "";
        const latestLabelMarkup = stats ? `
            <g class="chart-value-callout" transform="translate(${Math.min(xForDisplayPoint(stats.latest) + 12, plotRight - 78).toFixed(2)}, ${Math.max(margin.top + 12, Math.min(yScale(stats.latest.y) - 18, plotBottom - 42)).toFixed(2)})">
                <rect width="76" height="34" rx="8" fill="${realtimeColor}"></rect>
                <text x="38" y="14" text-anchor="middle">当前</text>
                <text x="38" y="27" text-anchor="middle">${escapeHTML(formatPercent(stats.latest.y, 3))}</text>
            </g>
        ` : "";
        const extremaMarkup = stats ? `
            <circle class="chart-extreme-point" cx="${xForDisplayPoint(stats.maxPoint).toFixed(2)}" cy="${yScale(stats.maxPoint.y).toFixed(2)}" r="3.6"></circle>
            <circle class="chart-extreme-point" cx="${xForDisplayPoint(stats.minPoint).toFixed(2)}" cy="${yScale(stats.minPoint.y).toFixed(2)}" r="3.6"></circle>
        ` : "";

        chartMount.innerHTML = `
            <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHTML(chartSymbol)} 升贴水率走势">
                <defs>
                    <linearGradient id="smoothAreaFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="${CHART_COLORS.smoothFill}" />
                        <stop offset="100%" stop-color="rgba(15, 139, 123, 0.00)" />
                    </linearGradient>
                </defs>
                <rect x="0" y="0" width="${width}" height="${height}" rx="16" fill="${CHART_COLORS.bg}"></rect>
                ${statMarkup}
                <g transform="translate(${plotRight - 232}, 52)">
                    ${showDailySeries ? `
                        <circle cx="0" cy="0" r="5" fill="none" stroke="${CHART_COLORS.raw}" stroke-width="2"></circle>
                        <text class="chart-legend-label" x="12" y="4">30日原始</text>
                        <circle cx="92" cy="0" r="5" fill="none" stroke="${CHART_COLORS.smooth}" stroke-width="3"></circle>
                        <text class="chart-legend-label" x="104" y="4">30日平滑</text>
                    ` : `
                        <circle cx="0" cy="0" r="5" fill="${realtimeColor}" stroke="${realtimeColor}" stroke-width="2"></circle>
                        <text class="chart-legend-label" x="12" y="4">${escapeHTML(chartSymbol)} 当日主力</text>
                    `}
                </g>
                <g>
                    <rect class="chart-premium-zone" x="${margin.left}" y="${margin.top}" width="${plotWidth}" height="${Math.max(0, zeroLine - margin.top).toFixed(2)}"></rect>
                    <rect class="chart-discount-zone" x="${margin.left}" y="${zeroLine.toFixed(2)}" width="${plotWidth}" height="${Math.max(0, plotBottom - zeroLine).toFixed(2)}"></rect>
                    ${yTicksMarkup}
                    ${xTicksMarkup}
                    <line class="chart-zero-line" x1="${margin.left}" y1="${zeroLine.toFixed(2)}" x2="${plotRight}" y2="${zeroLine.toFixed(2)}" />
                    ${avgLine == null ? "" : `<line class="chart-avg-line" x1="${margin.left}" y1="${avgLine.toFixed(2)}" x2="${plotRight}" y2="${avgLine.toFixed(2)}" />`}
                    <line class="chart-axis-line" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${plotBottom}"></line>
                    <line class="chart-axis-line" x1="${margin.left}" y1="${plotBottom}" x2="${plotRight}" y2="${plotBottom}"></line>
                </g>
                <text class="chart-axis-title" x="26" y="${margin.top + plotHeight / 2}" text-anchor="middle" transform="rotate(-90 26 ${margin.top + plotHeight / 2})">升贴水率 (%)</text>
                <text class="chart-axis-title" x="${margin.left + plotWidth / 2}" y="${height - 10}" text-anchor="middle">${intradayPoints.length ? "日内时间" : "交易日期"}</text>
                <g fill="none">
                    ${smoothArea ? `<path d="${smoothArea}" fill="url(#smoothAreaFill)" stroke="none"></path>` : ""}
                    ${rawPath ? `<path d="${rawPath}" stroke="${CHART_COLORS.raw}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="7 5" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${smoothPath ? `<path d="${smoothPath}" stroke="${CHART_COLORS.smooth}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${intradayGlowPath ? `<path d="${intradayGlowPath}" stroke="${realtimeGlowColor}" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${intradayPath ? `<path d="${intradayPath}" stroke="${realtimeColor}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                </g>
                ${extremaMarkup}
                ${lastPointMarkup}
                ${latestLabelMarkup}
            </svg>
        `;
    }

    function renderPriceChartV2(intraday, daily, selected) {
        ensureChartShell();
        if (!chartMount) {
            return;
        }

        const intradayAllPoints = Array.isArray(intraday.points)
            ? intraday.points.map(point => buildChartPoint(point, false)).filter(Boolean)
            : [];
        const intradayPoints = getIntradayWindow(intradayAllPoints);
        const dailyRaw = Array.isArray(daily.raw)
            ? daily.raw.map(point => buildChartPoint(point, true)).filter(Boolean)
            : [];
        const displayPoints = (intradayPoints.length ? intradayPoints : dailyRaw)
            .filter(point => Number.isFinite(point.futuresPrice) && Number.isFinite(point.indexPrice));
        const chartSymbol = selected.symbol || state.selectedSymbol;
        const showIntradaySeries = intradayPoints.length > 0;

        if (!displayPoints.length) {
            chartMount.innerHTML = '<div class="chart-empty">当前没有可绘制的期货和指数价格数据。</div>';
            setChartOverlay("", true);
            return;
        }

        setChartOverlay("", true);

        const renderedWidth = chartMount.getBoundingClientRect ? Math.round(chartMount.getBoundingClientRect().width) : 0;
        const width = Math.max(renderedWidth || 760, 360);
        const height = 460;
        const compactChart = width < 720;
        const margin = {
            top: compactChart ? 132 : 92,
            right: compactChart ? 36 : 104,
            bottom: 72,
            left: compactChart ? 62 : 96,
        };
        const plotWidth = width - margin.left - margin.right;
        const plotHeight = height - margin.top - margin.bottom;
        const plotRight = margin.left + plotWidth;
        const plotBottom = margin.top + plotHeight;
        const yValues = displayPoints
            .flatMap(point => [point.futuresPrice, point.indexPrice])
            .filter(Number.isFinite);
        const yDomain = buildPriceDomain(yValues, 6);
        const yScale = createLinearScale(yDomain.min, yDomain.max, plotBottom, margin.top);
        const xBounds = getAxisBounds(displayPoints);
        const xMin = Number.isFinite(xBounds.min)
            ? xBounds.min
            : (displayPoints[0] ? displayPoints[0].x - 5 * 60 * 1000 : 0);
        const xMax = Number.isFinite(xBounds.max)
            ? xBounds.max
            : (displayPoints[0] ? displayPoints[0].x + 5 * 60 * 1000 : 1);
        const xScale = createLinearScale(xMin, xMax, margin.left, plotRight);
        const showDate = showIntradaySeries && displayPoints.length > 48;
        const futuresPath = buildSvgPath(displayPoints, point => xScale(point.x), point => yScale(point.futuresPrice));
        const indexPath = buildSvgPath(displayPoints, point => xScale(point.x), point => yScale(point.indexPrice));
        const lastPoint = displayPoints[displayPoints.length - 1] || null;
        const premiumPoints = lastPoint && Number.isFinite(lastPoint.premiumPoints)
            ? lastPoint.premiumPoints
            : (lastPoint ? lastPoint.futuresPrice - lastPoint.indexPrice : null);
        const premiumRate = lastPoint && Number.isFinite(lastPoint.y) ? lastPoint.y : null;
        const gapColor = premiumPoints && premiumPoints > 0 ? CHART_COLORS.up : CHART_COLORS.down;

        const xTicksMarkup = showIntradaySeries
            ? buildNumericTicks(xMin, xMax, 6).map(value => {
                const x = xScale(value);
                return `
                    <line class="chart-grid-line" x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${plotBottom}" />
                    <text class="chart-tick-label" x="${x.toFixed(2)}" y="${height - 26}" text-anchor="middle">${escapeHTML(formatAxisTime(value, showDate))}</text>
                `;
            }).join("")
            : buildTickIndexes(displayPoints.length, 7).map(index => {
                const point = displayPoints[index];
                if (!point) {
                    return "";
                }
                const x = xScale(point.x);
                return `
                    <line class="chart-grid-line" x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${plotBottom}" />
                    <text class="chart-tick-label" x="${x.toFixed(2)}" y="${height - 26}" text-anchor="middle">${escapeHTML(formatShortDate(point.x))}</text>
                `;
            }).join("");
        const yTicksMarkup = yDomain.ticks.map(value => {
            const y = yScale(value);
            return `
                <line class="chart-grid-line" x1="${margin.left}" y1="${y.toFixed(2)}" x2="${plotRight}" y2="${y.toFixed(2)}" />
                <text class="chart-tick-label" x="${margin.left - 10}" y="${(y + 4).toFixed(2)}" text-anchor="end">${escapeHTML(formatNumber(value, 0))}</text>
            `;
        }).join("");

        const statItems = lastPoint ? [
            ["期货", formatNumber(lastPoint.futuresPrice, 2)],
            ["指数", formatNumber(lastPoint.indexPrice, 2)],
            ["价差", formatBasisPoints(premiumPoints, 2)],
            ["贴水率", formatBasisRate(premiumRate, 3)],
            ["样本", `${displayPoints.length} 个点`],
        ] : [];
        const chipStep = compactChart ? Math.max((plotWidth - 8) / 3, 94) : 142;
        const statMarkup = statItems.map((item, index) => {
            const chipWidth = compactChart ? 94 : (index === 4 ? 92 : 130);
            const chipX = compactChart
                ? margin.left + (index % 3) * chipStep
                : margin.left + index * chipStep;
            const chipY = compactChart
                ? 20 + Math.floor(index / 3) * 42
                : 28;
            return `
                <g class="chart-stat-chip" transform="translate(${chipX}, ${chipY})">
                    <rect width="${chipWidth}" height="38" rx="8"></rect>
                    <text class="chart-stat-label" x="11" y="15">${escapeHTML(item[0])}</text>
                    <text class="chart-stat-value" x="11" y="30">${escapeHTML(item[1])}</text>
                </g>
            `;
        }).join("");
        const lastPointMarkup = lastPoint ? `
            <circle cx="${xScale(lastPoint.x).toFixed(2)}" cy="${yScale(lastPoint.futuresPrice).toFixed(2)}" r="7" fill="${CHART_COLORS.futuresGlow}"></circle>
            <circle cx="${xScale(lastPoint.x).toFixed(2)}" cy="${yScale(lastPoint.futuresPrice).toFixed(2)}" r="4" fill="${CHART_COLORS.futures}" stroke="${CHART_COLORS.realtimePoint}" stroke-width="2"></circle>
            <circle cx="${xScale(lastPoint.x).toFixed(2)}" cy="${yScale(lastPoint.indexPrice).toFixed(2)}" r="7" fill="${CHART_COLORS.indexGlow}"></circle>
            <circle cx="${xScale(lastPoint.x).toFixed(2)}" cy="${yScale(lastPoint.indexPrice).toFixed(2)}" r="4" fill="${CHART_COLORS.index}" stroke="${CHART_COLORS.realtimePoint}" stroke-width="2"></circle>
        ` : "";
        const gapMarkup = lastPoint ? `
            <line x1="${xScale(lastPoint.x).toFixed(2)}" y1="${yScale(lastPoint.futuresPrice).toFixed(2)}" x2="${xScale(lastPoint.x).toFixed(2)}" y2="${yScale(lastPoint.indexPrice).toFixed(2)}" stroke="${gapColor}" stroke-width="2.4" stroke-dasharray="5 4"></line>
        ` : "";
        const latestLabelMarkup = lastPoint ? `
            <g class="chart-value-callout" transform="translate(${Math.max(margin.left + 4, Math.min(xScale(lastPoint.x) - 98, plotRight - 88)).toFixed(2)}, ${Math.max(margin.top + 12, Math.min((yScale(lastPoint.futuresPrice) + yScale(lastPoint.indexPrice)) / 2 - 19, plotBottom - 46)).toFixed(2)})">
                <rect width="86" height="38" rx="8" fill="${gapColor}"></rect>
                <text x="43" y="15" text-anchor="middle">当前价差</text>
                <text x="43" y="30" text-anchor="middle">${escapeHTML(formatBasisPoints(premiumPoints, 2))}</text>
            </g>
        ` : "";
        const endLabelX = compactChart
            ? Math.max(margin.left + 4, Math.min(xScale(lastPoint.x) - 82, plotRight - 78))
            : Math.min(xScale(lastPoint.x) + 10, plotRight - 78);
        const priceLabelsMarkup = lastPoint ? `
            <g class="chart-value-callout" transform="translate(${endLabelX.toFixed(2)}, ${Math.max(margin.top + 4, Math.min(yScale(lastPoint.futuresPrice) - 11, plotBottom - 24)).toFixed(2)})">
                <rect width="78" height="24" rx="7" fill="${CHART_COLORS.futures}"></rect>
                <text x="39" y="16" text-anchor="middle">期 ${escapeHTML(formatNumber(lastPoint.futuresPrice, 2))}</text>
            </g>
            <g class="chart-value-callout" transform="translate(${endLabelX.toFixed(2)}, ${Math.max(margin.top + 4, Math.min(yScale(lastPoint.indexPrice) - 11, plotBottom - 24)).toFixed(2)})">
                <rect width="78" height="24" rx="7" fill="${CHART_COLORS.index}"></rect>
                <text x="39" y="16" text-anchor="middle">指 ${escapeHTML(formatNumber(lastPoint.indexPrice, 2))}</text>
            </g>
        ` : "";

        chartMount.innerHTML = `
            <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHTML(chartSymbol)} 期货与指数价格走势">
                <rect x="0" y="0" width="${width}" height="${height}" rx="16" fill="${CHART_COLORS.bg}"></rect>
                ${statMarkup}
                <g transform="translate(${compactChart ? margin.left : plotRight - 246}, ${compactChart ? 110 : 52})">
                    <circle cx="0" cy="0" r="5" fill="${CHART_COLORS.futures}" stroke="${CHART_COLORS.futures}" stroke-width="2"></circle>
                    <text class="chart-legend-label" x="12" y="4">期货主力</text>
                    <circle cx="94" cy="0" r="5" fill="${CHART_COLORS.index}" stroke="${CHART_COLORS.index}" stroke-width="2"></circle>
                    <text class="chart-legend-label" x="106" y="4">指数现货</text>
                </g>
                <g>
                    ${yTicksMarkup}
                    ${xTicksMarkup}
                    <line class="chart-axis-line" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${plotBottom}"></line>
                    <line class="chart-axis-line" x1="${margin.left}" y1="${plotBottom}" x2="${plotRight}" y2="${plotBottom}"></line>
                </g>
                <text class="chart-axis-title" x="26" y="${margin.top + plotHeight / 2}" text-anchor="middle" transform="rotate(-90 26 ${margin.top + plotHeight / 2})">价格</text>
                <text class="chart-axis-title" x="${margin.left + plotWidth / 2}" y="${height - 10}" text-anchor="middle">${showIntradaySeries ? "日内时间" : "交易日期"}</text>
                <g fill="none">
                    ${futuresPath ? `<path d="${futuresPath}" stroke="${CHART_COLORS.futures}" stroke-width="5.6" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                    ${indexPath ? `<path d="${indexPath}" stroke="${CHART_COLORS.index}" stroke-width="5.6" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>` : ""}
                </g>
                ${gapMarkup}
                ${lastPointMarkup}
                ${priceLabelsMarkup}
                ${latestLabelMarkup}
            </svg>
        `;
    }

    function highlightSelectedSummaryCard() {
        if (!summaryGrid) {
            return;
        }
        summaryGrid.querySelectorAll(".summary-card[data-symbol]").forEach(node => {
            const isActive = node.getAttribute("data-symbol") === state.selectedSymbol;
            node.classList.toggle("is-active", isActive);
        });
        setText(selectedSymbolLabel, state.selectedSymbol);
    }

    async function fetchJSON(url) {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || "request failed");
        }
        return data;
    }

    function requestDashboardLoad(forceRefresh) {
        if (state.loading) {
            state.queuedLoad = true;
            state.queuedForceRefresh = state.queuedForceRefresh || Boolean(forceRefresh);
            return;
        }
        loadDashboard(forceRefresh);
    }

    async function loadDashboard(forceRefresh) {
        if (state.loading) {
            state.queuedLoad = true;
            state.queuedForceRefresh = state.queuedForceRefresh || Boolean(forceRefresh);
            return;
        }

        const requestSymbol = state.selectedSymbol;
        state.loading = true;
        setTopProgress(true);
        if (refreshButton) {
            refreshButton.disabled = true;
        }
        setChartOverlay(forceRefresh ? "正在刷新..." : "正在加载...", false);

        try {
            const refreshSuffix = forceRefresh ? "&refresh=1" : "";
            const [overview, details, intraday, daily] = await Promise.all([
                fetchJSON(`/api/dashboard/overview?symbol=${requestSymbol}${refreshSuffix}`),
                fetchJSON(`/api/dashboard/details?symbol=${requestSymbol}`),
                fetchJSON(`/api/dashboard/timeseries?symbol=${requestSymbol}&range=intraday`),
                fetchJSON(`/api/dashboard/timeseries?symbol=${requestSymbol}&range=30d`),
            ]);

            renderOverview(overview);
            renderDetails(details);
            renderContracts(overview.selected && Array.isArray(overview.selected.contracts) ? overview.selected.contracts : []);
            renderAlerts(
                overview.selected && Array.isArray(overview.selected.alerts) ? overview.selected.alerts : [],
                overview.selected ? overview.selected.quality_summary : null
            );
            renderPriceChartV2(intraday, daily, {
                symbol: details.symbol || requestSymbol,
                symbol_name: details.symbol_name || "",
            });
            resetRefreshCountdown();
            handleThresholdPrompt(overview.selected || null);
            highlightSelectedSummaryCard();
        } catch (error) {
            const message = error && error.message ? error.message : "未知错误";
            setChartOverlay(`加载失败：${message}`, false);
            if (alertList) {
                alertList.innerHTML = `
                    <div class="alert-item alert flash-update">
                        <strong>页面数据加载失败</strong>
                        <span>${escapeHTML(message)}</span>
                    </div>
                `;
            }
        } finally {
            state.loading = false;
            setTopProgress(false);
            if (refreshButton) {
                refreshButton.disabled = false;
            }
            if (state.queuedLoad || requestSymbol !== state.selectedSymbol) {
                const nextForceRefresh = state.queuedForceRefresh;
                state.queuedLoad = false;
                state.queuedForceRefresh = false;
                window.setTimeout(() => loadDashboard(nextForceRefresh), 0);
            }
        }
    }

    function startRefreshLoop() {
        if (state.refreshTimer) {
            window.clearInterval(state.refreshTimer);
        }
        startRefreshCountdown();
        state.refreshTimer = window.setInterval(() => {
            loadDashboard(false);
        }, REFRESH_INTERVAL_MS);
    }

    if (summaryGrid) {
        summaryGrid.addEventListener("click", event => {
            const card = event.target.closest(".summary-card[data-symbol]");
            if (!card) {
                return;
            }
            const nextSymbol = card.getAttribute("data-symbol");
            if (!nextSymbol || nextSymbol === state.selectedSymbol) {
                return;
            }
            state.selectedSymbol = nextSymbol;
            highlightSelectedSummaryCard();
            requestDashboardLoad(false);
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener("click", () => {
            requestDashboardLoad(true);
        });
    }

    if (thresholdModalClose) {
        thresholdModalClose.addEventListener("click", () => {
            closeThresholdModal();
        });
    }

    if (thresholdModalAcknowledge) {
        thresholdModalAcknowledge.addEventListener("click", () => {
            closeThresholdModal();
        });
    }

    if (thresholdModal) {
        thresholdModal.addEventListener("click", event => {
            if (event.target && event.target.hasAttribute("data-close-threshold-modal")) {
                closeThresholdModal();
            }
        });
    }

    document.addEventListener("keydown", event => {
        if (event.key === "Escape") {
            closeThresholdModal();
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            if (state.refreshTimer) {
                window.clearInterval(state.refreshTimer);
                state.refreshTimer = null;
            }
            if (countdownTimer) {
                window.clearInterval(countdownTimer);
                countdownTimer = null;
            }
            return;
        }
        startRefreshLoop();
        requestDashboardLoad(false);
    });

    ensureChartShell();
    renderSourceCatalog();
    requestDashboardLoad(false);
    startRefreshLoop();
}());
