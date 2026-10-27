(() => {
    "use strict";
    const root = document.documentElement;
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    let saved = "auto";
    try { saved = localStorage.getItem("theme") || "auto"; } catch (_) { /* Storage may be disabled. */ }
    if (!root.dataset.theme) root.dataset.theme = ["light", "dark", "auto"].includes(saved) ? saved : "auto";
    const sync = () => {
        const mode = root.dataset.theme;
        root.dataset.cgTheme = mode === "dark" || (mode !== "light" && system.matches) ? "dark" : "light";
    };
    sync();
    system.addEventListener("change", sync);
    new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    window.addEventListener("storage", (event) => {
        if (event.key === "theme") root.dataset.theme = ["light", "dark", "auto"].includes(event.newValue) ? event.newValue : "auto";
    });
})();
