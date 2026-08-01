(function () {
    "use strict";

    const root = document.documentElement;
    const themeButton = document.getElementById("theme-toggle");
    const backToTop = document.getElementById("back-to-top");

    function preferredTheme() {
        const saved = localStorage.getItem("cg-api-docs-theme");

        if (saved) {
            return saved;
        }

        if (
            window.matchMedia &&
            window.matchMedia("(prefers-color-scheme: dark)").matches
        ) {
            return "dark";
        }

        return "light";
    }

    function setTheme(theme) {
        root.setAttribute("data-theme", theme);
        localStorage.setItem("cg-api-docs-theme", theme);
    }

    setTheme(preferredTheme());

    if (themeButton) {
        themeButton.addEventListener("click", function () {
            const current = root.getAttribute("data-theme");

            setTheme(
                current === "dark"
                    ? "light"
                    : "dark"
            );
        });
    }

    function updateBackToTop() {
        if (!backToTop) {
            return;
        }

        backToTop.classList.toggle(
            "is-visible",
            window.scrollY > 700
        );
    }

    window.addEventListener(
        "scroll",
        updateBackToTop,
        { passive: true }
    );

    if (backToTop) {
        backToTop.addEventListener("click", function () {
            window.scrollTo({
                top: 0,
                behavior: "smooth"
            });
        });
    }

    document.addEventListener("keydown", function (event) {
        if (
            event.key !== "/" ||
            event.metaKey ||
            event.ctrlKey ||
            event.altKey
        ) {
            return;
        }

        const active = document.activeElement;

        if (
            active &&
            (
                active.tagName === "INPUT" ||
                active.tagName === "TEXTAREA"
            )
        ) {
            return;
        }

        const search = document.querySelector(
            ".swagger-ui .filter-container input"
        );

        if (search) {
            event.preventDefault();
            search.focus();
        }
    });

    function installCopyButtons() {
        document
            .querySelectorAll(".swagger-ui pre")
            .forEach(function (block) {
                if (block.dataset.copyReady === "1") {
                    return;
                }

                block.dataset.copyReady = "1";
                block.classList.add("swagger-copy-host");

                const button = document.createElement("button");

                button.type = "button";
                button.className = "swagger-copy-button";
                button.textContent = "COPY";

                button.addEventListener(
                    "click",
                    async function () {
                        const text = block.innerText.replace(
                            /COPY$|COPIED$|FAILED$/,
                            ""
                        );

                        try {
                            await navigator.clipboard.writeText(text);

                            button.textContent = "COPIED";

                            setTimeout(function () {
                                button.textContent = "COPY";
                            }, 1200);
                        } catch (error) {
                            button.textContent = "FAILED";

                            setTimeout(function () {
                                button.textContent = "COPY";
                            }, 1200);
                        }
                    }
                );

                block.appendChild(button);
            });
    }

    const swagger = document.getElementById("swagger-ui");

    if (swagger) {
        const observer = new MutationObserver(
            installCopyButtons
        );

        observer.observe(
            swagger,
            {
                childList: true,
                subtree: true
            }
        );

        installCopyButtons();
    }
})();
