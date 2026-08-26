(() => {
    "use strict";

    const palette = ["#4d85bd", "#72afd8", "#16a978", "#e9a23b", "#7d6bb2", "#7c91a6"];
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const readJson = (id) => {
        const element = document.getElementById(id);
        return element ? JSON.parse(element.textContent || "[]") : [];
    };
    const types = readJson("dashboard-content-types");
    const jobs = readJson("dashboard-job-statuses");
    const deliveries = readJson("dashboard-delivery-statuses");
    const labels = readJson("dashboard-daily-labels");
    const daily = readJson("dashboard-daily-counts");
    const dailyGreetings = readJson("dashboard-daily-greeting-counts");

    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebar-overlay");
    const menuButton = document.getElementById("menu-toggle");

    const setSidebar = (open) => {
        sidebar?.classList.toggle("is-open", open);
        overlay?.classList.toggle("is-visible", open);
        menuButton?.setAttribute("aria-expanded", String(open));
        document.body.style.overflow = open ? "hidden" : "";
    };

    menuButton?.addEventListener("click", () => setSidebar(!sidebar.classList.contains("is-open")));
    overlay?.addEventListener("click", () => setSidebar(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setSidebar(false);
    });

    const currentPath = window.location.pathname.replace(/\/$/, "") || "/";
    document.querySelectorAll(".nav-link[href]").forEach((link) => {
        const linkPath = new URL(link.href, window.location.origin).pathname.replace(/\/$/, "") || "/";
        const matches = link.dataset.match === "exact"
            ? currentPath === linkPath
            : currentPath === linkPath || currentPath.startsWith(`${linkPath}/`);
        link.classList.toggle("is-active", matches);
        if (matches) link.setAttribute("aria-current", "page");
    });

    const renderBars = (id, items) => {
        const root = document.getElementById(id);
        if (!root) return;
        if (!items.length) {
            root.innerHTML = '<div class="empty-state">No operational data yet.</div>';
            return;
        }
        const total = items.reduce((sum, item) => sum + item.count, 0) || 1;
        root.replaceChildren(...items.map((item, index) => {
            const row = document.createElement("div");
            row.className = "health-row";
            const label = document.createElement("strong");
            label.textContent = item.status || item.content_type || "Unknown";
            const track = document.createElement("div");
            track.className = "bar-track";
            const fill = document.createElement("div");
            fill.className = "bar-fill";
            fill.style.setProperty("--bar", palette[index % palette.length]);
            fill.style.setProperty("--bar-width", `${Math.max(3, Math.round((item.count / total) * 100))}%`);
            fill.style.width = reduceMotion ? "var(--bar-width)" : "0";
            track.append(fill);
            const value = document.createElement("b");
            value.textContent = item.count;
            row.append(label, track, value);
            return row;
        }));
    };

    renderBars("job-health", jobs);
    renderBars("delivery-health", deliveries);

    if (!reduceMotion) {
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                document.querySelectorAll(".bar-fill").forEach((bar) => {
                    bar.style.width = "var(--bar-width)";
                });
            });
        });
    }

    const setupCanvas = (canvas) => {
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const rect = canvas.getBoundingClientRect();
        canvas.width = Math.max(1, Math.floor(rect.width * ratio));
        canvas.height = Math.max(1, Math.floor(rect.height * ratio));
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, rect.width, rect.height);
        return { context, width: rect.width, height: rect.height };
    };

    const roundedRect = (context, x, y, width, height, radius) => {
        context.beginPath();
        context.roundRect(x, y, width, height, radius);
    };

    const drawTrend = () => {
        const canvas = document.getElementById("production-trend");
        if (!canvas) return;
        const { context, width, height } = setupCanvas(canvas);
        const pad = { top: 21, right: 15, bottom: 30, left: 28 };
        const plotWidth = width - pad.left - pad.right;
        const plotHeight = height - pad.top - pad.bottom;
        const max = Math.max(...daily, ...dailyGreetings, 1);
        const ceiling = Math.max(4, Math.ceil(max / 4) * 4);
        const step = plotWidth / Math.max(daily.length - 1, 1);

        context.font = "9px ui-sans-serif, system-ui";
        context.textBaseline = "middle";
        for (let index = 0; index <= 4; index += 1) {
            const y = pad.top + (plotHeight * index) / 4;
            const value = Math.round(ceiling - (ceiling * index) / 4);
            context.strokeStyle = "#e9edf4";
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(pad.left, y);
            context.lineTo(width - pad.right, y);
            context.stroke();
            context.fillStyle = "#9aa4b3";
            context.textAlign = "right";
            context.fillText(String(value), pad.left - 8, y);
        }

        const points = daily.map((value, index) => ({
            x: pad.left + index * step,
            y: pad.top + plotHeight - (value / ceiling) * plotHeight,
            value,
        }));
        const greetingPoints = dailyGreetings.map((value, index) => ({
            x: pad.left + index * step,
            y: pad.top + plotHeight - (value / ceiling) * plotHeight,
            value,
        }));
        const tracePath = (series) => {
            context.beginPath();
            series.forEach((point, index) => {
                if (!index) context.moveTo(point.x, point.y);
                else {
                    const previous = series[index - 1];
                    const midpoint = (previous.x + point.x) / 2;
                    context.bezierCurveTo(
                        midpoint,
                        previous.y,
                        midpoint,
                        point.y,
                        point.x,
                        point.y,
                    );
                }
            });
        };
        const gradient = context.createLinearGradient(0, pad.top, 0, height - pad.bottom);
        gradient.addColorStop(0, "rgba(77, 133, 189, .24)");
        gradient.addColorStop(1, "rgba(77, 133, 189, 0)");

        tracePath(points);
        context.lineTo(points.at(-1)?.x || pad.left, height - pad.bottom);
        context.lineTo(points[0]?.x || pad.left, height - pad.bottom);
        context.closePath();
        context.fillStyle = gradient;
        context.fill();

        tracePath(points);
        context.strokeStyle = "#4d85bd";
        context.lineWidth = 2.5;
        context.lineCap = "round";
        context.lineJoin = "round";
        context.stroke();

        points.forEach((point, index) => {
            context.fillStyle = "#fff";
            context.beginPath();
            context.arc(point.x, point.y, 4, 0, Math.PI * 2);
            context.fill();
            context.strokeStyle = "#4d85bd";
            context.lineWidth = 2;
            context.stroke();
            context.fillStyle = "#8591a4";
            context.font = "9px ui-sans-serif, system-ui";
            context.textAlign = "center";
            context.textBaseline = "alphabetic";
            const rawLabel = labels[index] || "";
            context.fillText(rawLabel.slice(5), point.x, height - 8);
        });

        if (greetingPoints.length) {
            tracePath(greetingPoints);
            context.strokeStyle = "#18a77a";
            context.lineWidth = 2.5;
            context.lineCap = "round";
            context.lineJoin = "round";
            context.stroke();

            greetingPoints.forEach((point) => {
                context.fillStyle = "#fff";
                context.beginPath();
                context.arc(point.x, point.y, 3.5, 0, Math.PI * 2);
                context.fill();
                context.strokeStyle = "#18a77a";
                context.lineWidth = 2;
                context.stroke();
            });
        }
    };

    const drawMix = () => {
        const canvas = document.getElementById("content-mix");
        if (!canvas) return;
        const { context, width, height } = setupCanvas(canvas);
        const total = types.reduce((sum, item) => sum + item.count, 0);
        const centerX = Math.min(width * .42, 135);
        const centerY = height * .47;
        const radius = Math.min(width, height) * .27;
        const lineWidth = Math.max(18, radius * .28);
        let start = -Math.PI / 2;

        if (!total) {
            context.strokeStyle = "#edf1f6";
            context.lineWidth = lineWidth;
            context.beginPath();
            context.arc(centerX, centerY, radius, 0, Math.PI * 2);
            context.stroke();
        }

        types.forEach((item, index) => {
            const angle = total ? (item.count / total) * Math.PI * 2 : 0;
            context.beginPath();
            context.strokeStyle = palette[index % palette.length];
            context.lineWidth = lineWidth;
            context.lineCap = "round";
            context.arc(centerX, centerY, radius, start + .025, start + angle - .025);
            context.stroke();
            start += angle;
        });

        context.fillStyle = "#18243a";
        context.textAlign = "center";
        context.font = "800 24px ui-sans-serif, system-ui";
        context.fillText(String(total), centerX, centerY + 5);
        context.fillStyle = "#8a95a6";
        context.font = "9px ui-sans-serif, system-ui";
        context.fillText("TOTAL ITEMS", centerX, centerY + 22);

        const legendX = Math.min(width * .66, centerX + radius + 40);
        types.slice(0, 5).forEach((item, index) => {
            const y = 40 + index * 31;
            context.fillStyle = palette[index % palette.length];
            roundedRect(context, legendX, y - 7, 9, 9, 3);
            context.fill();
            context.textAlign = "left";
            context.fillStyle = "#59677c";
            context.font = "700 9px ui-sans-serif, system-ui";
            context.fillText(String(item.content_type || "Unknown").toUpperCase(), legendX + 16, y);
            context.fillStyle = "#1f2d43";
            context.font = "800 10px ui-sans-serif, system-ui";
            context.fillText(String(item.count), legendX + 16, y + 13);
        });
    };

    let resizeFrame;
    const renderCharts = () => {
        window.cancelAnimationFrame(resizeFrame);
        resizeFrame = window.requestAnimationFrame(() => {
            drawTrend();
            drawMix();
        });
    };

    renderCharts();
    window.addEventListener("resize", renderCharts, { passive: true });

    const animateNumber = (element) => {
        const raw = element.textContent.trim();
        const match = raw.match(/^([\d,]+(?:\.\d+)?)(.*)$/);
        if (!match) return;
        const target = Number(match[1].replaceAll(",", ""));
        if (!Number.isFinite(target)) return;
        const suffix = match[2];
        const decimals = (match[1].split(".")[1] || "").length;
        const duration = Math.min(1200, 550 + target * 4);
        const started = performance.now();
        const tick = (now) => {
            const progress = Math.min(1, (now - started) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            const value = target * eased;
            element.textContent = `${value.toLocaleString(undefined, {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals,
            })}${suffix}`;
            if (progress < 1) window.requestAnimationFrame(tick);
        };
        window.requestAnimationFrame(tick);
    };

    const revealTargets = document.querySelectorAll(".hero, .kpi-card, .panel, .page-footer");
    if (reduceMotion) {
        revealTargets.forEach((element) => element.classList.add("is-visible"));
    } else {
        document.documentElement.classList.add("motion-ready");
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                const index = Number(entry.target.dataset.revealIndex || 0);
                window.setTimeout(() => entry.target.classList.add("is-visible"), Math.min(index * 55, 260));
                observer.unobserve(entry.target);
            });
        }, { threshold: .08 });
        revealTargets.forEach((element, index) => {
            element.dataset.revealIndex = String(index);
            observer.observe(element);
        });

        document.querySelectorAll(".kpi-value, .hero-stat b, .recipient-card b").forEach(animateNumber);

        document.querySelectorAll(".kpi-card, .recipient-card").forEach((card) => {
            card.classList.add("motion-card");
            card.addEventListener("pointermove", (event) => {
                if (event.pointerType === "touch") return;
                const rect = card.getBoundingClientRect();
                const x = (event.clientX - rect.left) / rect.width - .5;
                const y = (event.clientY - rect.top) / rect.height - .5;
                card.style.setProperty("--tilt-x", `${(-y * 2.3).toFixed(2)}deg`);
                card.style.setProperty("--tilt-y", `${(x * 2.3).toFixed(2)}deg`);
                card.style.setProperty("--glow-x", `${((x + .5) * 100).toFixed(0)}%`);
                card.style.setProperty("--glow-y", `${((y + .5) * 100).toFixed(0)}%`);
            });
            card.addEventListener("pointerleave", () => {
                card.style.removeProperty("--tilt-x");
                card.style.removeProperty("--tilt-y");
            });
        });
    }
})();
