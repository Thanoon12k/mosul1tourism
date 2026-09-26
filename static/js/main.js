(() => {
    "use strict";

    const root = document.documentElement;
    const body = document.body;
    const languageToggle = document.querySelector("#language-toggle");
    const menuToggle = document.querySelector(".menu-toggle");
    const mainNav = document.querySelector("#main-nav");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let currentLanguage = "en";

    const languageMeta = {
        ar: {
            title: root.dataset.titleAr || document.title,
            description: root.dataset.descAr || "",
            switchLabel: "Switch to English",
        },
        en: {
            title: root.dataset.titleEn || document.title,
            description: root.dataset.descEn || "",
            switchLabel: "التبديل إلى العربية",
        },
    };

    function safeStoredLanguage() {
        try {
            return localStorage.getItem("harith-language-v2");
        } catch {
            return null;
        }
    }

    function storeLanguage(language) {
        try {
            localStorage.setItem("harith-language-v2", language);
        } catch {
            // The interface still works when browser storage is disabled.
        }
    }

    function applyLanguage(language) {
        currentLanguage = language === "en" ? "en" : "ar";
        root.lang = currentLanguage;
        root.dir = currentLanguage === "ar" ? "rtl" : "ltr";
        document.title = languageMeta[currentLanguage].title;

        const description = document.querySelector('meta[name="description"]');
        if (description) description.content = languageMeta[currentLanguage].description;
        if (languageToggle) languageToggle.setAttribute("aria-label", languageMeta[currentLanguage].switchLabel);

        document.querySelectorAll("[data-href-ar][data-href-en]").forEach((link) => {
            link.href = link.dataset[currentLanguage === "ar" ? "hrefAr" : "hrefEn"];
        });

        document.querySelectorAll("img[data-alt-ar][data-alt-en]").forEach((image) => {
            image.alt = image.dataset[currentLanguage === "ar" ? "altAr" : "altEn"];
        });

        document.querySelectorAll(".gallery-item[data-alt-ar][data-alt-en], .lb-thumb[data-alt-ar][data-alt-en]").forEach((item) => {
            item.setAttribute("aria-label", item.dataset[currentLanguage === "ar" ? "altAr" : "altEn"]);
        });

        storeLanguage(currentLanguage);
        document.dispatchEvent(new CustomEvent("site:language", { detail: currentLanguage }));
    }

    if (languageToggle) {
        languageToggle.addEventListener("click", () => {
            applyLanguage(currentLanguage === "ar" ? "en" : "ar");
        });
    }

    applyLanguage(safeStoredLanguage() || root.dataset.defaultLang || "en");

    function closeMenu() {
        if (!menuToggle || !mainNav) return;
        menuToggle.setAttribute("aria-expanded", "false");
        mainNav.classList.remove("is-open");
        body.classList.remove("menu-open");
    }

    if (menuToggle && mainNav) {
        menuToggle.addEventListener("click", () => {
            const opening = menuToggle.getAttribute("aria-expanded") !== "true";
            menuToggle.setAttribute("aria-expanded", String(opening));
            mainNav.classList.toggle("is-open", opening);
            body.classList.toggle("menu-open", opening);
        });

        mainNav.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
        window.addEventListener("resize", () => {
            if (window.innerWidth > 860) closeMenu();
        });
    }

    const revealItems = [...document.querySelectorAll(".reveal")];
    if (reducedMotion || !("IntersectionObserver" in window)) {
        revealItems.forEach((item) => item.classList.add("is-visible"));
    } else {
        const revealObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.08, rootMargin: "0px 0px -40px" });
        revealItems.forEach((item) => revealObserver.observe(item));
    }

    const filters = [...document.querySelectorAll("[data-filter]")];
    const galleryItems = [...document.querySelectorAll(".gallery-item")];
    let activeFilter = "all";

    filters.forEach((button) => {
        button.addEventListener("click", () => {
            activeFilter = button.dataset.filter;
            filters.forEach((item) => item.classList.toggle("is-active", item === button));
            galleryItems.forEach((item) => {
                item.hidden = activeFilter !== "all" && !item.dataset.category.split(" ").includes(activeFilter);
            });
        });
    });

    const lightbox = document.querySelector(".lightbox");
    const lightboxImage = lightbox?.querySelector("img");
    const lightboxCaption = lightbox?.querySelector("figcaption");
    const lightboxClose = lightbox?.querySelector(".lightbox-close");
    const lightboxPrev = lightbox?.querySelector(".lightbox-prev");
    const lightboxNext = lightbox?.querySelector(".lightbox-next");
    let lightboxIndex = 0;
    let lightboxItems = [];
    let lastFocused = null;

    function visibleGalleryItems() {
        return galleryItems.filter((item) => !item.hidden);
    }

    function groupItems(item) {
        if (item.classList.contains("gallery-item")) return visibleGalleryItems();
        return [...document.querySelectorAll(".lb-thumb")].filter((thumb) => thumb.dataset.group === item.dataset.group);
    }

    function updateLightbox(index) {
        const items = lightboxItems;
        if (!items.length || !lightboxImage || !lightboxCaption) return;
        lightboxIndex = (index + items.length) % items.length;
        const item = items[lightboxIndex];
        const source = item.querySelector("img");
        lightboxImage.src = source.src;
        lightboxImage.alt = item.dataset[currentLanguage === "ar" ? "altAr" : "altEn"];
        lightboxCaption.textContent = items.length > 1 ? `${lightboxImage.alt} · ${lightboxIndex + 1}/${items.length}` : lightboxImage.alt;
    }

    function openLightbox(item) {
        if (!lightbox) return;
        lightboxItems = groupItems(item);
        lastFocused = item;
        updateLightbox(lightboxItems.indexOf(item));
        lightbox.hidden = false;
        body.style.overflow = "hidden";
        lightboxClose?.focus();
    }

    function closeLightbox() {
        if (!lightbox || lightbox.hidden) return;
        lightbox.hidden = true;
        body.style.overflow = "";
        if (lightboxImage) lightboxImage.src = "";
        lastFocused?.focus();
    }

    galleryItems.forEach((item) => item.addEventListener("click", () => openLightbox(item)));
    document.querySelectorAll(".lb-thumb").forEach((item) => item.addEventListener("click", () => openLightbox(item)));
    lightboxClose?.addEventListener("click", closeLightbox);
    lightboxPrev?.addEventListener("click", () => updateLightbox(lightboxIndex - 1));
    lightboxNext?.addEventListener("click", () => updateLightbox(lightboxIndex + 1));
    lightbox?.addEventListener("click", (event) => {
        if (event.target === lightbox) closeLightbox();
    });

    document.addEventListener("keydown", (event) => {
        if (!lightbox || lightbox.hidden) return;
        if (event.key === "Escape") closeLightbox();
        if (event.key === "ArrowLeft") updateLightbox(lightboxIndex - 1);
        if (event.key === "ArrowRight") updateLightbox(lightboxIndex + 1);
    });

    document.addEventListener("site:language", () => {
        if (lightbox && !lightbox.hidden) updateLightbox(lightboxIndex);
    });

    const year = document.querySelector("#year");
    if (year) year.textContent = String(new Date().getFullYear());
})();
