(() => {
    "use strict";

    const $ = (selector, scope = document) => scope.querySelector(selector);
    const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
    const staticUrl = (path) => (/^https?:\/\//.test(path) ? path : window.STATIC_URL + path);

    // Mobile sidebar
    const toggle = $(".side-toggle");
    const sidebar = $("#sidebar");
    toggle?.addEventListener("click", () => {
        const open = !sidebar.classList.contains("open");
        sidebar.classList.toggle("open", open);
        toggle.setAttribute("aria-expanded", String(open));
    });

    // Confirm dangerous buttons
    document.addEventListener("click", (event) => {
        const button = event.target.closest("[data-confirm]");
        if (button && !window.confirm(button.dataset.confirm)) event.preventDefault();
    });

    // Warn about unsaved edits
    let dirty = false;
    $$("form.edit-form, form.gallery-edit").forEach((form) => {
        form.addEventListener("input", () => { dirty = true; });
        form.addEventListener("change", () => { dirty = true; });
        form.addEventListener("submit", () => { dirty = false; });
    });
    window.addEventListener("beforeunload", (event) => {
        if (dirty) { event.preventDefault(); event.returnValue = ""; }
    });

    // Select-all checkbox for gallery
    $("[data-select-all]")?.addEventListener("change", (event) => {
        $$('input[name="selected"]').forEach((box) => { box.checked = event.target.checked; });
    });

    // Drop-zone highlighting
    $$(".dropzone").forEach((zone) => {
        ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, () => zone.classList.add("is-over")));
        ["dragleave", "drop"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("is-over")));
    });

    // Previews for files chosen but not yet uploaded
    $$("[data-preview-multi]").forEach((input) => {
        input.addEventListener("change", () => {
            const holder = $("[data-pending]", input.closest(".images-field, form"));
            if (!holder) return;
            holder.innerHTML = "";
            [...input.files].forEach((file) => {
                const image = document.createElement("img");
                image.src = URL.createObjectURL(file);
                image.title = file.name;
                holder.appendChild(image);
            });
        });
    });

    $$("[data-preview-single]").forEach((input) => {
        input.addEventListener("change", () => {
            const field = input.closest("[data-image-field]");
            const file = input.files[0];
            if (!file) return;
            $(".image-preview", field).innerHTML = `<img src="${URL.createObjectURL(file)}" alt="">`;
        });
    });

    // Single image: clear
    $$("[data-clear-image]").forEach((button) => {
        button.addEventListener("click", () => {
            const field = button.closest("[data-image-field]");
            $(".path-input", field).value = "";
            $("input[type=file]", field).value = "";
            $(".image-preview", field).innerHTML = '<span class="muted">No image</span>';
            dirty = true;
        });
    });

    // Image path typed by hand -> refresh preview
    $$(".path-input").forEach((input) => {
        input.addEventListener("change", () => {
            const preview = $(".image-preview", input.closest("[data-image-field]"));
            preview.innerHTML = input.value ? `<img src="${staticUrl(input.value)}" alt="">` : '<span class="muted">No image</span>';
        });
    });

    // Multi-image list: remove / move / drag
    function refreshEmpty(field) {
        $(".empty-note", field).hidden = $$(".thumb", field).length > 0;
    }

    function makeThumb(field, path) {
        const thumb = document.createElement("div");
        thumb.className = "thumb";
        thumb.draggable = true;
        thumb.innerHTML = `<img src="${staticUrl(path)}" alt=""><input type="hidden"><div class="thumb-tools">
            <button type="button" data-move="-1" title="Move left">‹</button>
            <button type="button" data-move="1" title="Move right">›</button>
            <button type="button" data-remove title="Remove">×</button></div>`;
        const hidden = $("input", thumb);
        hidden.name = field.dataset.name;
        hidden.value = path;
        $("[data-thumb-list]", field).appendChild(thumb);
        refreshEmpty(field);
        dirty = true;
    }

    document.addEventListener("click", (event) => {
        const remove = event.target.closest("[data-remove]");
        const move = event.target.closest("[data-move]");
        if (!remove && !move) return;
        const thumb = event.target.closest(".thumb");
        const field = thumb.closest("[data-images-field]");
        if (remove) {
            thumb.remove();
        } else if (move.dataset.move === "-1" && thumb.previousElementSibling) {
            thumb.parentNode.insertBefore(thumb, thumb.previousElementSibling);
        } else if (move.dataset.move === "1" && thumb.nextElementSibling) {
            thumb.parentNode.insertBefore(thumb.nextElementSibling, thumb);
        }
        refreshEmpty(field);
        dirty = true;
    });

    let dragged = null;
    document.addEventListener("dragstart", (event) => {
        dragged = event.target.closest?.(".thumb") || null;
        dragged?.classList.add("dragging");
    });
    document.addEventListener("dragend", () => {
        dragged?.classList.remove("dragging");
        dragged = null;
    });
    document.addEventListener("dragover", (event) => {
        if (!dragged) return;
        const over = event.target.closest(".thumb");
        if (!over || over === dragged || over.parentNode !== dragged.parentNode) return;
        event.preventDefault();
        const rect = over.getBoundingClientRect();
        const after = event.clientX > rect.left + rect.width / 2;
        over.parentNode.insertBefore(dragged, after ? over.nextSibling : over);
        dirty = true;
    });

    // Media library picker
    const picker = $("#picker");
    const grid = $("#picker-grid");
    const search = $("#picker-search");
    let mediaCache = null;
    let onPick = null;

    async function openPicker(callback) {
        onPick = callback;
        picker.hidden = false;
        search.value = "";
        search.focus();
        if (!mediaCache) {
            try {
                const response = await fetch(window.MEDIA_URL, { credentials: "same-origin" });
                mediaCache = await response.json();
            } catch {
                grid.innerHTML = '<p class="muted">Could not load the media library.</p>';
                return;
            }
        }
        renderPicker();
    }

    function renderPicker() {
        const term = search.value.trim().toLowerCase();
        grid.innerHTML = "";
        mediaCache.filter((item) => item.path.toLowerCase().includes(term)).forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.innerHTML = `<img src="${item.url}" alt="" loading="lazy"><span></span>`;
            $("span", button).textContent = item.path;
            button.addEventListener("click", () => {
                onPick?.(item.path);
                closePicker();
            });
            grid.appendChild(button);
        });
        if (!grid.children.length) grid.innerHTML = '<p class="muted">No images match.</p>';
    }

    function closePicker() {
        picker.hidden = true;
        onPick = null;
    }

    search?.addEventListener("input", renderPicker);
    $$("[data-picker-close]").forEach((button) => button.addEventListener("click", closePicker));
    picker?.addEventListener("click", (event) => { if (event.target === picker) closePicker(); });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && picker && !picker.hidden) closePicker(); });

    $$("[data-pick-single]").forEach((button) => {
        button.addEventListener("click", () => {
            const field = button.closest("[data-image-field]");
            openPicker((path) => {
                $(".path-input", field).value = path;
                $("input[type=file]", field).value = "";
                $(".image-preview", field).innerHTML = `<img src="${staticUrl(path)}" alt="">`;
                dirty = true;
            });
        });
    });

    $$("[data-pick-multi]").forEach((button) => {
        button.addEventListener("click", () => {
            const field = button.closest("[data-images-field]");
            openPicker((path) => makeThumb(field, path));
        });
    });
})();
