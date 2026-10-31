(function () {
    "use strict";

    var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---------- mobile navigation ---------- */
    var nav = document.getElementById("site-nav");
    var navToggle = document.querySelector(".nav-toggle");

    function setNav(open) {
        if (!nav || !navToggle) return;
        nav.classList.toggle("is-open", open);
        navToggle.classList.toggle("is-open", open);
        navToggle.setAttribute("aria-expanded", String(open));
        navToggle.setAttribute("aria-label", open ? "Закрыть меню" : "Открыть меню");
        document.body.classList.toggle(
            "nav-open",
            open && window.matchMedia("(max-width: 900px)").matches
        );
    }

    if (navToggle && nav) {
        navToggle.addEventListener("click", function () {
            setNav(!nav.classList.contains("is-open"));
        });

        nav.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                setNav(false);
            });
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") setNav(false);
        });

        var desktop = window.matchMedia("(min-width: 901px)");
        var handleDesktop = function (event) {
            if (event.matches) setNav(false);
        };
        if (typeof desktop.addEventListener === "function") {
            desktop.addEventListener("change", handleDesktop);
        }
    }

    /* ---------- reveal on scroll ---------- */
    var revealItems = document.querySelectorAll(".reveal");

    if (!("IntersectionObserver" in window) || reduceMotion) {
        revealItems.forEach(function (item) {
            item.classList.add("is-visible");
        });
    } else {
        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                });
            },
            { threshold: 0.12, rootMargin: "0px 0px -36px 0px" }
        );

        revealItems.forEach(function (item) {
            observer.observe(item);
        });
    }

    /* ---------- image preloading ---------- */
    document.querySelectorAll("[data-image]").forEach(function (item) {
        var preload = new Image();
        preload.src = item.getAttribute("data-image");
    });

    /* ---------- emotions ---------- */
    var emotionButtons = document.querySelectorAll(".emotion-btn");
    var emotionImage = document.getElementById("emotion-image");
    var emotionLabel = document.getElementById("emotion-label");
    var emotionQuote = document.getElementById("emotion-quote");
    var emotionTimer = null;

    emotionButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            if (button.getAttribute("aria-pressed") === "true") return;

            emotionButtons.forEach(function (item) {
                item.setAttribute("aria-pressed", "false");
            });
            button.setAttribute("aria-pressed", "true");

            window.clearTimeout(emotionTimer);
            emotionImage.classList.add("is-swapping");
            emotionTimer = window.setTimeout(function () {
                emotionImage.src = button.getAttribute("data-image");
                emotionImage.alt = button.getAttribute("data-alt");
                emotionLabel.textContent = button.getAttribute("data-label");
                emotionQuote.textContent = button.getAttribute("data-quote");
                emotionImage.classList.remove("is-swapping");
            }, 160);
        });
    });

    /* ---------- characters ---------- */
    var charButtons = document.querySelectorAll(".char-tab");
    var charImage = document.getElementById("char-image");
    var charName = document.getElementById("char-name");
    var charQuote = document.getElementById("char-quote");
    var charDesc = document.getElementById("char-desc");
    var charIndex = document.getElementById("char-index");
    var charGhost = document.getElementById("char-ghost");
    var charTimer = null;

    charButtons.forEach(function (button, index) {
        button.addEventListener("click", function () {
            if (button.getAttribute("aria-pressed") === "true") return;

            charButtons.forEach(function (item) {
                item.setAttribute("aria-pressed", "false");
            });
            button.setAttribute("aria-pressed", "true");

            window.clearTimeout(charTimer);
            charImage.classList.add("is-swapping");
            charTimer = window.setTimeout(function () {
                charName.textContent = button.getAttribute("data-name");
                charQuote.textContent = button.getAttribute("data-quote");
                charDesc.textContent = button.getAttribute("data-desc");
                charIndex.textContent =
                    String(index + 1).padStart(2, "0") + " / " + String(charButtons.length).padStart(2, "0");
                charGhost.textContent = String(index + 1).padStart(2, "0");
                charImage.src = button.getAttribute("data-image");
                charImage.alt = button.getAttribute("data-alt");
                charImage.classList.remove("is-swapping");
            }, 160);
        });
    });

    /* ---------- lightbox ---------- */
    var lightbox = document.getElementById("lightbox");
    var lightboxImage = lightbox ? lightbox.querySelector("img") : null;
    var lightboxClose = lightbox ? lightbox.querySelector(".lightbox-close") : null;

    function closeLightbox() {
        if (!lightbox || !lightbox.open) return;
        lightbox.close();
    }

    document.querySelectorAll("[data-lightbox]").forEach(function (trigger) {
        trigger.addEventListener("click", function () {
            if (!lightbox || !lightboxImage || typeof lightbox.showModal !== "function") {
                window.open(trigger.getAttribute("data-lightbox"), "_blank", "noopener");
                return;
            }

            lightboxImage.src = trigger.getAttribute("data-lightbox");
            lightboxImage.alt = trigger.getAttribute("data-alt") || "";
            lightbox.showModal();
            document.body.classList.add("modal-open");
        });
    });

    if (lightbox) {
        lightbox.addEventListener("close", function () {
            document.body.classList.remove("modal-open");
        });

        lightbox.addEventListener("click", function (event) {
            if (event.target === lightbox) closeLightbox();
        });
    }

    if (lightboxClose) {
        lightboxClose.addEventListener("click", closeLightbox);
    }

    /* ---------- current year ---------- */
    var year = document.getElementById("year");
    if (year) year.textContent = String(new Date().getFullYear());
})();
