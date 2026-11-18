(() => {
    "use strict";
    function start() {
        const root = document.querySelector("[data-warmup-generator]");
        if (!root) return;
        const form = root.querySelector("[data-generation-form]");
        const button = form?.querySelector("button");
        const originalLabel = button?.textContent.trim();
        const blocked = root.dataset.blocked === "true";
        const panel = root.querySelector("[data-run-panel]");
        const connection = root.querySelector("[data-connection-message]");
        let cooldownUntil = Date.now() + Number(root.dataset.cooldown) * 1000;
        let submitting = false;
        let timer = null;
        let current = null;
        let failures = 0;
        let resultSignature = null;

        function notice(text) {
            connection.textContent = text;
            connection.hidden = !text;
        }
        function updateButton() {
            const seconds = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
            const remaining = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
            if (button) {
                button.disabled = blocked || submitting || seconds > 0;
                button.textContent = submitting ? "Starting generation…" : seconds ? `Create again in ${remaining}` : originalLabel;
            }
            root.querySelector("[data-cooldown-label]").textContent = seconds
                ? "Prevents duplicate batches. Your results are available below." : "";
        }
        function paint(data) {
            current = data;
            panel.hidden = false;
            panel.dataset.state = data.state;
            panel.querySelector("[data-run-title]").textContent = {
                queued: "Queued", generating: "Generating", delayed: "Still working",
                complete: "Your templates are ready", partial: "Some templates are ready", failed: "Generation failed",
            }[data.state] || "Batch progress";
            panel.querySelector("[data-run-message]").textContent = data.message;
            panel.querySelector("[data-run-count]").textContent = `${data.ready} / ${data.total} ready`;
            const progress = panel.querySelector("progress");
            progress.max = data.total;
            progress.value = data.ready + data.failed;
            const signature = JSON.stringify([data.results, data.errors]);
            if (signature !== resultSignature) {
                resultSignature = signature;
                const errors = panel.querySelector("[data-run-errors]");
                errors.replaceChildren(...data.errors.map(message => {
                    const item = document.createElement("li"); item.textContent = message; return item;
                }));
                const results = panel.querySelector("[data-run-results]");
                results.replaceChildren(...data.results.map(result => {
                    const item = document.createElement("li");
                    const title = document.createElement("span");
                    title.textContent = `Template ${result.number} `;
                    const id = document.createElement("small"); id.textContent = `#${result.id}`; title.append(id);
                    item.append(title);
                    for (const [label, url] of [["Preview template →", result.preview_url], ["Download HTML", result.download_url]]) {
                        const link = document.createElement("a"); link.textContent = label; link.href = url; item.append(link);
                    }
                    return item;
                }));
            }
            cooldownUntil = Date.now() + data.cooldown_seconds * 1000;
            if (data.summary) {
                const count = document.querySelector("[data-template-today]");
                if (count) count.textContent = data.summary.today_count;
                const latest = document.querySelector("[data-template-latest]");
                if (latest && data.summary.latest_url) {
                    latest.href = data.summary.latest_url; latest.hidden = false;
                    document.querySelector("[data-template-latest-empty]").hidden = true;
                }
            }
            updateButton();
        }
        async function jsonRequest(url, options = {}) {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 15000);
            try {
                const response = await fetch(url, {...options, credentials: "same-origin", cache: "no-store",
                    headers: {Accept: "application/json"}, signal: controller.signal});
                if (!response.headers.get("Content-Type")?.includes("application/json")) {
                    throw new Error("Your session or connection needs attention. Reload this page to continue.");
                }
                return {response, data: await response.json()};
            } finally { clearTimeout(timeout); }
        }
        function schedule() {
            clearTimeout(timer);
            if (current && !current.terminal && !document.hidden) {
                timer = setTimeout(poll, failures ? Math.min(15000, failures * 3000) : current.state === "delayed" ? 15000 : 2500);
            }
        }
        async function poll() {
            if (!current || submitting || document.hidden) return;
            const batch = current.batch_key;
            try {
                const {response, data} = await jsonRequest(current.status_url);
                if (current.batch_key !== batch || submitting) return;
                if (response.status === 404 || response.status === 403) {
                    notice(data.message || "Progress is unavailable. Check Saved templates or reload this page.");
                    return;
                }
                if (!response.ok) throw new Error("Progress updates are temporarily unavailable. Retrying automatically.");
                failures = 0; notice(""); paint(data);
            } catch (error) {
                failures += 1;
                notice(failures >= 12 ? "Connection interrupted. Reload this page to recover progress; do not submit the batch again." : "Connection interrupted. Retrying progress updates; your batch continues on the server.");
                if (failures >= 12) return;
            }
            schedule();
        }
        form?.addEventListener("submit", async event => {
            event.preventDefault();
            if (button.disabled || submitting) return;
            clearTimeout(timer); submitting = true; updateButton(); notice("");
            try {
                const {response, data} = await jsonRequest(form.action, {method: "POST", body: new FormData(form)});
                if (response.ok) {
                    failures = 0; paint(data);
                    const location = new URL(window.location.href);
                    location.searchParams.set("batch", data.batch_key);
                    location.hash = "template-generation";
                    window.history.replaceState(null, "", location);
                } else {
                    if (data.progress) paint(data.progress);
                    notice(data.message || "The request could not be queued. Please reload and try again.");
                }
            } catch (error) {
                notice("The response was interrupted. Reload this page to check whether the batch was queued before trying again.");
            } finally { submitting = false; updateButton(); schedule(); }
        });
        document.addEventListener("visibilitychange", () => {
            clearTimeout(timer);
            if (!document.hidden && current && !current.terminal) poll();
        });
        setInterval(updateButton, 1000);
        const initial = JSON.parse(document.getElementById("warmup-generation-initial").textContent);
        if (initial) paint(initial);
        updateButton(); schedule();
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
})();
