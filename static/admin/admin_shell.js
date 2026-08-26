(() => {
    "use strict";

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nav = document.getElementById("nav-sidebar");
    const activeItem = nav?.querySelector("tr.current-model a");

    if (activeItem && !reduceMotion) {
        window.requestAnimationFrame(() => {
            activeItem.scrollIntoView({ block: "center", behavior: "smooth" });
        });
    }

    nav?.querySelectorAll("th a, .cg-nav-quick a").forEach((link) => {
        link.addEventListener("pointerdown", (event) => {
            if (reduceMotion) return;
            const rect = link.getBoundingClientRect();
            const ripple = document.createElement("i");
            ripple.className = "cg-nav-ripple";
            ripple.style.left = `${event.clientX - rect.left}px`;
            ripple.style.top = `${event.clientY - rect.top}px`;
            link.append(ripple);
            ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
        });
    });

    if (!reduceMotion) {
        document.documentElement.classList.add("cg-js-motion");
        window.requestAnimationFrame(() => document.body.classList.add("cg-page-ready"));
    }
})();
