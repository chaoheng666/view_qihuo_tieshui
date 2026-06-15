(function () {
    const REFRESH_INTERVAL_MS = 5000;
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
        { key: "sina_index", name: "新浪指数实时", url: "http://hq.sinajs.cn/list=sh000300,sh000905,sh000016,sh000852", intro: "沪深300、中证500、上证50和中证1000实时指数主源。" },
        { key: "eastmoney_index", name: "东方财富指数", url: "http://quote.eastmoney.com/center/hszs.html", intro: "指数备用链路，主源异常时回退使用。" },
        { key: "akshare_realtime", name: "AkShare 期货实时", url: "https://akshare.akfamily.xyz/data/futures/futures.html", intro: "IF、IC、IH 主力期货实时主源。" },
        { key: "sina_futures", name: "新浪期货实时", url: "http://hq.sinajs.cn/list=", intro: "IM 主力实时主源，同时作为股指期货备用源。" },
        { key: "cffex_daily", name: "中金所日线", url: "https://www.cffex.com.cn/lssjxz/", intro: "期货历史数据来源。" },
        { key: "index_daily", name: "指数历史日线", url: "https://akshare.akfamily.xyz/data/index/index.html", intro: "指数历史数据来源。" },
    ];

    const state = {
        selectedSymbol: "IF",
        loading: false,
        refreshTimer: null,
        countdownTimer: null,
        nextRefreshAt: 0,
        thresholds: null,
        lastThresholdPromptKey: "",
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
    const refreshButton = document.getElementById("refreshButton");
    const topProgress = document.getElementById("topProgress");
    const refreshCountdownLabel = document.getElementById("refreshCountdownLabel");
    const refreshCountdownBar = document.getElementById("refreshCountdownBar");
    const signalStack = document.getElementById("signalStack");
    const thresholdModal = document.getElementById("thresholdModal");
    const thresholdModalBody = document.getElementById("thresholdModalBody");
    const thresholdModalClose = document.getElementById("thresholdModalClose");
    const thresholdModalAcknowledge = document.getElementById("thresholdModalAcknowledge");
    const intradayChart = document.getElementById("intradayChart");

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
        return `${number > 0 ? "+" : ""}${number.toFixed(digits == null ? 2 : digits)}`;
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

    function formatAnnualized(item, digits) {
        if (!item) {
            return "--";
        }
        const basisRate = toNumber(item.annualized_basis_rate);
        if (basisRate !== null) {
            return `${basisRate > 0 ? "年化贴水" : basisRate < 0 ? "年化升水" : "年化平水"} ${Math.abs(basisRate).toFixed(digits == null ? 2 : digits)}%`;
        }
        const number = toNumber(item.annualized_rate);
        if (number === null) {
            return "--";
        }
        const premiumRate = toNumber(item.premium_rate);
        const label = premiumRate === null
            ? (number > 0 ? "年化升水" : number < 0 ? "年化贴水" : "年化平水")
            : (premiumRate > 0 ? "年化升水" : premiumRate < 0 ? "年化贴水" : "年化平水");
        return `${label} ${Math.abs(number).toFixed(digits == null ? 2 : digits)}%`;
    }

    function formatCount(value) {
        const number = toNumber(value);
        return number === null ? "--" : Math.round(number).toLocaleString("zh-CN");
    }

    function formatClock(value) {
        const text = String(value || "").trim();
        if (!text) {
            return "--";
        }
        const parts = text.split(" ");
        return parts.length > 1 ? parts[1] : text;
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

    function escapeHTML(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function directionClass(value) {
        const number = toNumber(value);
        if (number === null || number === 0) {
            return "";
        }
        return number > 0 ? "up" : "down";
    }

    function qualityClass(value) {
        return `quality-${String(value || "ok").replace(/[^a-z_]/gi, "_").toLowerCase()}`;
    }

    function qualityText(value) {
        return QUALITY_LABELS[value] || String(value || "--");
    }

    function sourceText(value) {
        const key = String(value || "").trim();
        return key ? (SOURCE_LABELS[key] || key.replace(/_/g, " ")) : "--";
    }

    function setText(element, value) {
        if (element) {
            element.textContent = value;
        }
    }

    function setTopProgress(active) {
        if (!topProgress) {
            return;
        }
        topProgress.classList.toggle("is-active", Boolean(active));
    }

    function resetRefreshCountdown() {
        state.nextRefreshAt = Date.now() + REFRESH_INTERVAL_MS;
        updateRefreshCountdown();
    }

    function updateRefreshCountdown() {
        if (!refreshCountdownLabel || !refreshCountdownBar) {
            return;
        }
        const remaining = Math.max(0, state.nextRefreshAt - Date.now());
        const elapsed = Math.max(0, REFRESH_INTERVAL_MS - remaining);
        refreshCountdownLabel.textContent = `下次刷新 ${Math.ceil(remaining / 1000)} 秒`;
        refreshCountdownBar.style.width = `${Math.min(100, elapsed / REFRESH_INTERVAL_MS * 100)}%`;
    }

    function startRefreshCountdown() {
        if (state.countdownTimer) {
            window.clearInterval(state.countdownTimer);
        }
        resetRefreshCountdown();
        state.countdownTimer = window.setInterval(updateRefreshCountdown, 250);
    }

    function renderSourceCatalog(activeKeys) {
        if (!sourceCatalogGrid) {
            return;
        }
        const activeSet = new Set((activeKeys || []).filter(Boolean));
        sourceCatalogGrid.innerHTML = SOURCE_CATALOG.map(item => `
            <article class="source-catalog-card ${activeSet.has(item.key) ? "is-active" : ""}" data-source-key="${escapeHTML(item.key)}">
                <div class="source-catalog-head">
                    <div class="source-catalog-name">${escapeHTML(item.name)}</div>
                    <a class="source-catalog-link" href="${escapeHTML(item.url)}" target="_blank" rel="noreferrer noopener">打开</a>
                </div>
                <div class="source-catalog-url">${escapeHTML(item.url)}</div>
                <p class="source-catalog-desc">${escapeHTML(item.intro)}</p>
            </article>
        `).join("");
    }

    function renderOverview(overview) {
        const cards = Array.isArray(overview.cards) ? overview.cards : [];
        setText(generatedAt, overview.generated_at || "--");
        state.thresholds = overview.thresholds || null;

        if (!summaryGrid) {
            return;
        }

        summaryGrid.innerHTML = cards.map(card => {
            const active = card.symbol === state.selectedSymbol;
            return `
                <article class="summary-card ${active ? "is-active" : ""}" data-symbol="${escapeHTML(card.symbol)}">
                    <div class="summary-head">
                        <div>
                            <h3>${escapeHTML(card.symbol || "--")}</h3>
                            <div class="summary-sub">${escapeHTML(card.symbol_name || card.index_name || "")}</div>
                        </div>
                        <span class="quality-pill ${qualityClass(card.data_quality)}">${escapeHTML(qualityText(card.data_quality))}</span>
                    </div>
                    <div class="summary-rate ${directionClass(card.premium_rate)}">${escapeHTML(formatBasisRate(card.premium_rate, 3))}</div>
                    <div class="summary-points">${escapeHTML(formatBasisPoints(card.premium_points, 2))}</div>
                    <div class="summary-foot">
                        <div class="mini-stat"><span>主力</span><strong>${escapeHTML(card.contract_code || "--")}</strong></div>
                        <div class="mini-stat"><span>年化</span><strong>${escapeHTML(formatAnnualized(card, 2))}</strong></div>
                        <div class="mini-stat"><span>期 / 指</span><strong>${escapeHTML(formatNumber(card.futures_price, 1))} / ${escapeHTML(formatNumber(card.index_price, 1))}</strong></div>
                        <div class="mini-stat"><span>Z</span><strong class="${directionClass(card.z_score_30d)}">${escapeHTML(formatSigned(card.z_score_30d, 2))}</strong></div>
                    </div>
                </article>
            `;
        }).join("");
    }

    function renderDetails(details) {
        const metrics = details.metrics || {};
        const validation = details.validation || {};
        const sources = details.sources || {};
        const stats = details.stats_30d || {};
        const quality = validation.data_quality || metrics.data_quality || "ok";
        const activeSources = [sources.futures, sources.index, metrics.source_futures, metrics.source_index, "cffex_daily", "index_daily"];

        setText(selectedSymbolLabel, details.symbol || state.selectedSymbol);
        if (heroQuality) {
            heroQuality.className = `quality-pill ${qualityClass(quality)}`;
            heroQuality.textContent = qualityText(quality);
        }

        if (signalStack) {
            signalStack.innerHTML = [
                ["基差", formatBasisPoints(metrics.premium_points, 2), `指数 ${formatNumber(metrics.index_price, 2)}`, metrics.premium_points],
                ["贴水率", formatBasisRate(metrics.premium_rate, 3), `MA5 ${formatBasisRate(stats.ma5, 3)}`, metrics.premium_rate],
                ["年化", formatAnnualized(metrics, 2), `到期 ${metrics.days_to_expiry == null ? "--" : `${metrics.days_to_expiry}天`}`, metrics.annualized_rate],
                ["活跃", metrics.contract_code || "--", `报价 ${formatClock(metrics.quote_time)}`, null],
            ].map(item => `
                <div class="signal-card">
                    <div class="signal-glyph">${escapeHTML(item[0].slice(0, 1))}</div>
                    <div class="signal-copy">
                        <strong>${escapeHTML(item[0])}</strong>
                        <div class="signal-value ${directionClass(item[3])}">${escapeHTML(item[1])}</div>
                        <p>${escapeHTML(item[2])}</p>
                    </div>
                </div>
            `).join("");
        }

        if (metricGrid) {
            metricGrid.innerHTML = [
                ["期货价", formatNumber(metrics.futures_price, 2)],
                ["指数价", formatNumber(metrics.index_price, 2)],
                ["成交量", formatCount(metrics.volume)],
                ["持仓量", formatCount(metrics.open_interest)],
                ["30日均值", formatBasisRate(stats.mean_30d, 3)],
                ["分位数", stats.percentile_30d == null ? "--" : `${formatNumber(stats.percentile_30d, 1)}%`],
            ].map(item => `
                <div class="metric-card">
                    <div class="metric-label">${escapeHTML(item[0])}</div>
                    <div class="metric-value">${escapeHTML(item[1])}</div>
                </div>
            `).join("");
        }

        if (sourceBox) {
            sourceBox.innerHTML = `
                <div class="info-box-title">数据来源</div>
                <div class="info-box-body">
                    <div class="info-row"><span class="info-key">期货</span><span class="info-value">${escapeHTML(sourceText(sources.futures || metrics.source_futures))}</span></div>
                    <div class="info-row"><span class="info-key">指数</span><span class="info-value">${escapeHTML(sourceText(sources.index || metrics.source_index))}</span></div>
                    <div class="info-row"><span class="info-key">报价时间</span><span class="info-value">${escapeHTML(metrics.quote_time || "--")}</span></div>
                </div>
            `;
        }

        if (qualityBox) {
            qualityBox.innerHTML = `
                <div class="info-box-title">质量状态</div>
                <div class="info-box-body">
                    <div class="info-row"><span class="info-key">状态</span><span class="info-value">${escapeHTML(qualityText(quality))}</span></div>
                    <div class="info-row"><span class="info-key">新鲜度</span><span class="info-value">${escapeHTML(formatFreshness(validation.freshness_seconds || metrics.freshness_seconds))}</span></div>
                    <div class="info-row"><span class="info-key">说明</span><span class="info-note">${escapeHTML(validation.reason || metrics.quality_reason || "无异常")}</span></div>
                </div>
            `;
        }

        if (statusPulseBox) {
            statusPulseBox.innerHTML = `
                <div class="status-pulse-head">
                    <div class="status-pulse-symbol">
                        <strong>${escapeHTML(details.symbol || state.selectedSymbol)}</strong>
                        <span>${escapeHTML(details.symbol_name || "")}</span>
                    </div>
                    <span class="status-pulse-contract">${escapeHTML(metrics.contract_code || "--")}</span>
                </div>
                <div class="status-pulse-grid">
                    <div class="status-pulse-stat"><span>基差点</span><strong>${escapeHTML(formatBasisPoints(metrics.premium_points, 2))}</strong></div>
                    <div class="status-pulse-stat"><span>基差率</span><strong>${escapeHTML(formatBasisRate(metrics.premium_rate, 3))}</strong></div>
                    <div class="status-pulse-stat"><span>年化</span><strong>${escapeHTML(formatAnnualized(metrics, 2))}</strong></div>
                    <div class="status-pulse-stat"><span>新鲜度</span><strong>${escapeHTML(formatFreshness(validation.freshness_seconds || metrics.freshness_seconds))}</strong></div>
                </div>
            `;
        }

        if (opsHeaderBadge) {
            opsHeaderBadge.innerHTML = `
                <span class="ops-badge-label">QUALITY</span>
                <strong class="quality-pill ${qualityClass(quality)}">${escapeHTML(qualityText(quality))}</strong>
            `;
        }

        renderSourceCatalog(activeSources);
    }

    function renderContracts(contracts) {
        const rows = Array.isArray(contracts) ? contracts : [];
        if (!contractTableBody) {
            return;
        }
        if (!rows.length) {
            contractTableBody.innerHTML = '<tr><td colspan="11" class="empty-row">暂无合约数据</td></tr>';
            return;
        }
        contractTableBody.innerHTML = rows.map(item => `
            <tr class="${item.is_main || item.contract_code === item.main_contract ? "is-main" : ""}">
                <td><span class="contract-code">${item.is_main ? '<i class="main-dot"></i>' : ""}${escapeHTML(item.contract_code || "--")}</span></td>
                <td>${escapeHTML(item.position || "--")}</td>
                <td>${escapeHTML(formatNumber(item.futures_price, 2))}</td>
                <td>${escapeHTML(formatNumber(item.index_price, 2))}</td>
                <td class="${directionClass(item.premium_points)}">${escapeHTML(formatBasisPoints(item.premium_points, 2))}</td>
                <td class="${directionClass(item.premium_rate)}">${escapeHTML(formatBasisRate(item.premium_rate, 3))}</td>
                <td>${escapeHTML(formatAnnualized(item, 2))}</td>
                <td>${escapeHTML(formatCount(item.volume))}</td>
                <td>${escapeHTML(formatCount(item.open_interest))}</td>
                <td>${escapeHTML(item.days_to_expiry == null ? "--" : String(item.days_to_expiry))}</td>
                <td><span class="quality-pill ${qualityClass(item.data_quality)}">${escapeHTML(qualityText(item.data_quality))}</span></td>
            </tr>
        `).join("");
    }

    function renderAlerts(alerts, qualitySummary) {
        const rows = Array.isArray(alerts) ? alerts : [];
        if (!alertList) {
            return;
        }
        if (!rows.length) {
            const quality = qualitySummary && qualitySummary.main_quality ? qualityText(qualitySummary.main_quality) : "正常";
            alertList.innerHTML = `<div class="empty-alert">暂无告警。当前质量：${escapeHTML(quality)}</div>`;
            return;
        }
        alertList.innerHTML = rows.map(item => `
            <div class="alert-item ${escapeHTML(item.level || "warning")}">
                <strong>${escapeHTML(item.title || item.type || "风险提示")}</strong>
                <span>${escapeHTML(item.message || item.reason || "")}</span>
            </div>
        `).join("");
    }

    function intradayMinute(value) {
        const match = String(value || "").match(/(\d{1,2}):(\d{2})(?::(\d{2}))?/);
        if (!match) {
            return null;
        }
        const total = Number(match[1]) * 60 + Number(match[2]) + (Number(match[3] || 0) / 60);
        if (total < 9 * 60 + 30 || total > 15 * 60) {
            return null;
        }
        if (total <= 11 * 60 + 30) {
            return total - (9 * 60 + 30);
        }
        if (total >= 13 * 60) {
            return 120 + total - 13 * 60;
        }
        return null;
    }

    function percentCoords(points, getValue, basePrice, maxPct, width, top, height) {
        return points.map((item) => {
            const minute = intradayMinute(item.timestamp);
            if (minute === null) {
                return null;
            }
            const x = minute / 240 * width;
            const pct = (getValue(item) - basePrice) / basePrice * 100;
            const y = top + (maxPct - pct) / (maxPct * 2 || 1) * height;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).filter(Boolean);
    }

    function percentPath(points, getValue, basePrice, maxPct, width, top, height) {
        return percentCoords(points, getValue, basePrice, maxPct, width, top, height).join(" ");
    }

    function percentAreaPath(points, getValue, basePrice, maxPct, width, top, height) {
        const coords = percentCoords(points, getValue, basePrice, maxPct, width, top, height);
        if (!coords.length) {
            return "";
        }
        const firstX = coords[0].split(",")[0];
        const lastX = coords[coords.length - 1].split(",")[0];
        const bottom = top + height;
        return `M ${coords[0]} L ${coords.slice(1).join(" L ")} L ${lastX},${bottom.toFixed(1)} L ${firstX},${bottom.toFixed(1)} Z`;
    }

    function chartLabelClass(value) {
        if (value > 0) {
            return "up";
        }
        if (value < 0) {
            return "down";
        }
        return "";
    }

    function formatChartPct(value) {
        return value === 0 ? "0.00" : formatSigned(value, 2);
    }

    function renderIntradayChart(series) {
        if (!intradayChart) {
            return;
        }
        const points = (series && Array.isArray(series.points) ? series.points : [])
            .filter(item => (
                toNumber(item.futures_price) !== null
                && toNumber(item.index_price) !== null
                && intradayMinute(item.timestamp) !== null
            ));
        if (!points.length) {
            intradayChart.innerHTML = '<div class="empty-chart">暂无分时数据</div>';
            return;
        }

        const width = 760;
        const height = 238;
        const leftAxis = 58;
        const rightAxis = 58;
        const plotWidth = width - leftAxis - rightAxis;
        const priceTop = 8;
        const priceHeight = 190;
        const prices = points.flatMap(item => [toNumber(item.futures_price), toNumber(item.index_price)]).filter(value => value !== null);
        const basePrice = toNumber(points[0].index_price) || toNumber(points[0].futures_price) || prices[0] || 1;
        const maxMove = Math.max(...prices.map(value => Math.abs((value - basePrice) / basePrice * 100)), 0.6);
        const maxPct = Math.max(0.6, Math.ceil(maxMove / 0.6) * 0.6);
        const pctTicks = [maxPct, maxPct * 2 / 3, maxPct / 3, 0, -maxPct / 3, -maxPct * 2 / 3, -maxPct];
        const futuresLine = percentPath(points, item => toNumber(item.futures_price), basePrice, maxPct, plotWidth, priceTop, priceHeight);
        const futuresArea = percentAreaPath(points, item => toNumber(item.futures_price), basePrice, maxPct, plotWidth, priceTop, priceHeight);
        const indexLine = percentPath(points, item => toNumber(item.index_price), basePrice, maxPct, plotWidth, priceTop, priceHeight);
        const gridRows = pctTicks.map(value => {
            const y = priceTop + (maxPct - value) / (maxPct * 2 || 1) * priceHeight;
            const price = basePrice * (1 + value / 100);
            return `
                <line x1="${leftAxis}" y1="${y.toFixed(1)}" x2="${leftAxis + plotWidth}" y2="${y.toFixed(1)}" class="chart-grid" />
                <text x="${leftAxis - 8}" y="${(y + 4).toFixed(1)}" class="chart-label chart-price-label ${chartLabelClass(value)}">${escapeHTML(formatNumber(price, 2))}</text>
                <text x="${leftAxis + plotWidth + 8}" y="${(y + 4).toFixed(1)}" class="chart-label chart-pct-label ${chartLabelClass(value)}">${escapeHTML(formatChartPct(value))}%</text>
            `;
        }).join("");
        const gridColumns = [
            [0, "9:30"],
            [60, "10:30"],
            [120, "11:30/13:00"],
            [180, "14:00"],
            [240, "15:00"],
        ].map(item => {
            const x = leftAxis + item[0] / 240 * plotWidth;
            return `
                <line x1="${x.toFixed(1)}" y1="${priceTop}" x2="${x.toFixed(1)}" y2="${priceTop + priceHeight}" class="chart-grid chart-grid-vertical" />
                <text x="${x.toFixed(1)}" y="${(priceTop + priceHeight + 22).toFixed(1)}" class="chart-label chart-time-label">${item[1]}</text>
            `;
        }).join("");
        const last = points[points.length - 1] || {};
        const lastPremium = toNumber(last.premium_rate);

        intradayChart.innerHTML = `
            <div class="intraday-chart-meta">
                <span>${escapeHTML(last.contract_code || state.selectedSymbol)}</span>
                <span>期货 <b class="chart-futures">${escapeHTML(formatNumber(last.futures_price, 2))}</b></span>
                <span>指数 <b class="chart-index">${escapeHTML(formatNumber(last.index_price, 2))}</b></span>
                <span class="${directionClass(lastPremium)}">贴水率 ${escapeHTML(formatSigned(lastPremium, 3))}%</span>
            </div>
            <svg class="intraday-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="intraday chart">
                <defs>
                    <linearGradient id="intradayAreaFill" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stop-color="#79bdff" stop-opacity="0.62" />
                        <stop offset="100%" stop-color="#dff2ff" stop-opacity="0.24" />
                    </linearGradient>
                </defs>
                ${gridRows}
                ${gridColumns}
                <line x1="${leftAxis}" y1="${(priceTop + priceHeight / 2).toFixed(1)}" x2="${leftAxis + plotWidth}" y2="${(priceTop + priceHeight / 2).toFixed(1)}" class="chart-zero-line" />
                <g transform="translate(${leftAxis},0)">
                    <path d="${futuresArea}" class="chart-area-futures" />
                    <polyline points="${futuresLine}" class="chart-line chart-line-futures" />
                    <polyline points="${indexLine}" class="chart-line chart-line-index" />
                </g>
            </svg>
            <div class="intraday-chart-legend">
                <span><i class="legend-futures"></i>主力期货</span>
                <span><i class="legend-index"></i>指数</span>
            </div>
        `;
    }

    function closeThresholdModal() {
        if (thresholdModal) {
            thresholdModal.hidden = true;
        }
    }

    function handleThresholdPrompt(selected) {
        if (!thresholdModal || !thresholdModalBody || !state.thresholds || !state.thresholds.popup_enabled || !selected) {
            return;
        }
        const main = selected.main_contract || selected.metrics || {};
        const rate = Math.abs(toNumber(main.premium_rate) || 0);
        const trigger = Math.abs(toNumber(state.thresholds.trigger) || 0);
        if (!trigger || rate < trigger) {
            return;
        }
        const key = `${state.selectedSymbol}:${main.contract_code || ""}:${main.quote_time || ""}:${rate}`;
        if (key === state.lastThresholdPromptKey) {
            return;
        }
        state.lastThresholdPromptKey = key;
        thresholdModalBody.innerHTML = `
            <div class="threshold-modal-highlight">
                <strong>${escapeHTML(main.contract_code || state.selectedSymbol)}</strong>
                <div class="threshold-modal-rate">${escapeHTML(formatBasisRate(main.premium_rate, 3))}</div>
            </div>
            <div class="threshold-modal-meta">
                <div class="threshold-modal-meta-row"><span>触发阈值</span><strong>${escapeHTML(formatBasisRate(trigger, 3))}</strong></div>
                <div class="threshold-modal-meta-row"><span>报价时间</span><strong>${escapeHTML(main.quote_time || "--")}</strong></div>
            </div>
        `;
        thresholdModal.hidden = false;
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

    async function loadDashboard(forceRefresh) {
        if (state.loading) {
            return;
        }
        const requestSymbol = state.selectedSymbol;
        state.loading = true;
        setTopProgress(true);
        if (refreshButton) {
            refreshButton.disabled = true;
        }

        try {
            const refreshSuffix = forceRefresh ? "&refresh=1" : "";
            const [overview, details, intraday] = await Promise.all([
                fetchJSON(`/api/dashboard/overview?symbol=${requestSymbol}${refreshSuffix}`),
                fetchJSON(`/api/dashboard/details?symbol=${requestSymbol}`),
                fetchJSON(`/api/dashboard/timeseries?symbol=${requestSymbol}&range=intraday`),
            ]);
            const selected = overview.selected || {};
            renderOverview(overview);
            renderDetails(details);
            renderIntradayChart(intraday);
            renderContracts(Array.isArray(selected.contracts) ? selected.contracts : []);
            renderAlerts(Array.isArray(selected.alerts) ? selected.alerts : [], selected.quality_summary || null);
            handleThresholdPrompt(selected);
            resetRefreshCountdown();
        } catch (error) {
            if (alertList) {
                alertList.innerHTML = `
                    <div class="alert-item alert">
                        <strong>页面数据加载失败</strong>
                        <span>${escapeHTML(error && error.message ? error.message : "未知错误")}</span>
                    </div>
                `;
            }
        } finally {
            state.loading = false;
            setTopProgress(false);
            if (refreshButton) {
                refreshButton.disabled = false;
            }
        }
    }

    function startRefreshLoop() {
        if (state.refreshTimer) {
            window.clearInterval(state.refreshTimer);
        }
        startRefreshCountdown();
        state.refreshTimer = window.setInterval(() => loadDashboard(false), REFRESH_INTERVAL_MS);
    }

    if (summaryGrid) {
        summaryGrid.addEventListener("click", event => {
            const card = event.target.closest(".summary-card[data-symbol]");
            if (!card) {
                return;
            }
            const symbol = card.getAttribute("data-symbol");
            if (!symbol || symbol === state.selectedSymbol) {
                return;
            }
            state.selectedSymbol = symbol;
            setText(selectedSymbolLabel, symbol);
            loadDashboard(false);
        });
    }

    if (refreshButton) {
        refreshButton.addEventListener("click", () => loadDashboard(true));
    }

    if (thresholdModalClose) {
        thresholdModalClose.addEventListener("click", closeThresholdModal);
    }
    if (thresholdModalAcknowledge) {
        thresholdModalAcknowledge.addEventListener("click", closeThresholdModal);
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
            if (state.countdownTimer) {
                window.clearInterval(state.countdownTimer);
                state.countdownTimer = null;
            }
            return;
        }
        startRefreshLoop();
        loadDashboard(false);
    });

    renderSourceCatalog([]);
    loadDashboard(false);
    startRefreshLoop();
}());
