// Runs after the page has finished loading
document.addEventListener("DOMContentLoaded", function () {

    // ---------- 1. Mobile menu (hamburger button) ----------
    const menuToggle = document.getElementById("menu-toggle");
    const navMenu = document.getElementById("nav-menu");

    menuToggle.addEventListener("click", function () {
        const isOpen = navMenu.classList.toggle("open");
        menuToggle.setAttribute("aria-expanded", isOpen);
    });

    // ---------- 2. Notifications: auto-hide after 4 seconds, or close manually ----------
    function hideToast(toast) {
        toast.classList.add("hide");
        setTimeout(function () { toast.remove(); }, 300);
    }

    document.querySelectorAll(".toast").forEach(function (toast) {
        setTimeout(function () { hideToast(toast); }, 4000);
        toast.querySelector(".toast-close").addEventListener("click", function () {
            hideToast(toast);
        });
    });

    // ---------- 3. Confirmation popup ----------
    // Any form with a data-confirm="message" attribute asks before submitting.
    const modal = document.getElementById("confirm-modal");
    const modalMessage = document.getElementById("confirm-message");
    let pendingForm = null;

    function closeModal() {
        modal.hidden = true;
        pendingForm = null;
    }

    document.getElementById("confirm-cancel").addEventListener("click", closeModal);

    document.getElementById("confirm-ok").addEventListener("click", function () {
        if (pendingForm) {
            pendingForm.submit();   // submit() skips the submit event, so no loop
        }
        closeModal();
    });

    modal.addEventListener("click", function (event) {
        if (event.target === modal) { closeModal(); }   // click outside the box
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") { closeModal(); }
    });

    // ---------- 4. Form submit handling ----------
    document.querySelectorAll("form").forEach(function (form) {
        form.addEventListener("submit", function (event) {

            // Ask for confirmation first (used by delete buttons)
            if (form.dataset.confirm) {
                event.preventDefault();
                pendingForm = form;
                modalMessage.textContent = form.dataset.confirm;
                modal.hidden = false;
                return;
            }

            // Loading state (used by upload forms): data-loading="Uploading..."
            if (form.dataset.loading) {
                const button = form.querySelector("button[type='submit']");
                if (button) {
                    button.disabled = true;
                    button.textContent = form.dataset.loading;
                }
            }
        });
    });
    
    // ---------- 5. Wishlist heart button ----------
    document.querySelectorAll(".wishlist-btn").forEach(function (button) {
        button.addEventListener("click", function () {

            // Not logged in: go to the login page
            if (button.dataset.loggedIn !== "true") {
                window.location.href = "/login";
                return;
            }

            button.disabled = true;
            fetch("/wishlist/toggle/" + button.dataset.bookId, { method: "POST" })
                .then(function (response) {
                    if (response.status === 401) {
                        window.location.href = "/login";
                        return null;
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (!data) { return; }

                    // Change the heart
                    button.textContent = data.wishlisted ? "❤️" : "🤍";
                    button.classList.toggle("active", data.wishlisted);

                    // Update the number in the navbar
                    const counter = document.getElementById("wishlist-count");
                    if (counter) {
                        const change = data.wishlisted ? 1 : -1;
                        counter.textContent = Math.max(0, Number(counter.textContent) + change);
                    }

                    // On the Wishlist page, remove the card when un-hearted
                    if (!data.wishlisted && document.querySelector("[data-wishlist-page]")) {
                        button.closest(".book-card").remove();
                        if (!document.querySelector(".book-card")) {
                            window.location.reload();   // show the empty state
                        }
                    }
                })
                .catch(function () {
                    alert("Something went wrong. Please try again.");
                })
                .finally(function () {
                    button.disabled = false;
                });
        });
    });

    
    // ---------- 6. Profile photo: click to view full size ----------
    const lightboxTrigger = document.getElementById("photo-viewer-trigger");
    const lightbox = document.getElementById("photo-lightbox");

    if (lightboxTrigger && lightbox) {
        const lightboxImg = document.getElementById("lightbox-img");
        const profileImg = document.getElementById("profile-photo-img");
        const lightboxClose = document.getElementById("lightbox-close");

        lightboxTrigger.addEventListener("click", function () {
            if (!profileImg) { return; }   // no photo uploaded, nothing to enlarge
            lightboxImg.src = profileImg.src;
            lightbox.hidden = false;
        });

        function closePhotoLightbox() {
            lightbox.hidden = true;
            lightboxImg.src = "";
        }

        lightboxClose.addEventListener("click", closePhotoLightbox);
        lightbox.addEventListener("click", function (event) {
            if (event.target === lightbox) { closePhotoLightbox(); }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !lightbox.hidden) { closePhotoLightbox(); }
        });
    }
    
    // ---------- 7. Dark mode toggle (slider switch) ----------
    const themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) {
        // Sync the switch position with the theme already applied by the anti-flicker script
        themeToggle.checked = document.documentElement.getAttribute("data-theme") === "dark";

        themeToggle.addEventListener("change", function () {
            if (themeToggle.checked) {
                document.documentElement.setAttribute("data-theme", "dark");
                localStorage.setItem("theme", "dark");
            } else {
                document.documentElement.removeAttribute("data-theme");
                localStorage.setItem("theme", "light");
            }
        });
    }

    
    // ---------- 8. Delete account confirmation modal (Settings page) ----------
    const openDeleteModal = document.getElementById("open-delete-modal");
    const deleteModal = document.getElementById("delete-account-modal");
    const cancelDeleteModal = document.getElementById("cancel-delete-modal");

    if (openDeleteModal && deleteModal) {
        openDeleteModal.addEventListener("click", function () { deleteModal.hidden = false; });
        cancelDeleteModal.addEventListener("click", function () { deleteModal.hidden = true; });
        deleteModal.addEventListener("click", function (event) {
            if (event.target === deleteModal) { deleteModal.hidden = true; }
        });
    }

    
    // ---------- 9. Search autocomplete ----------
    function setupAutocomplete(inputId, dropdownId) {
        const input = document.getElementById(inputId);
        const dropdown = document.getElementById(dropdownId);
        if (!input || !dropdown) { return; }

        let debounceTimer = null;

        function closeDropdown() {
            dropdown.hidden = true;
            dropdown.innerHTML = "";
        }

        function renderResults(results, query) {
            dropdown.innerHTML = "";
            if (results.length === 0) {
                dropdown.hidden = true;
                return;
            }
            results.forEach(function (book) {
                const item = document.createElement("a");
                item.href = "/books/" + book.id;
                item.className = "autocomplete-item";
                item.innerHTML = "<strong>" + escapeHtml(book.title) + "</strong>" +
                                  "<span>by " + escapeHtml(book.author) + "</span>";
                dropdown.appendChild(item);
            });
            dropdown.hidden = false;
        }

        function escapeHtml(text) {
            const div = document.createElement("div");
            div.textContent = text;
            return div.innerHTML;
        }

        input.addEventListener("input", function () {
            const query = input.value.trim();
            clearTimeout(debounceTimer);

            if (query.length < 2) {
                closeDropdown();
                return;
            }

            debounceTimer = setTimeout(function () {
                fetch("/api/search-suggestions?q=" + encodeURIComponent(query))
                    .then(function (response) { return response.json(); })
                    .then(function (results) { renderResults(results, query); })
                    .catch(function () { closeDropdown(); });
            }, 250);
        });

        // Close the dropdown when clicking outside it
        document.addEventListener("click", function (event) {
            if (!input.contains(event.target) && !dropdown.contains(event.target)) {
                closeDropdown();
            }
        });

        // Close on Escape
        input.addEventListener("keydown", function (event) {
            if (event.key === "Escape") { closeDropdown(); }
        });
    }

    setupAutocomplete("hero-search-input", "hero-search-dropdown");
    setupAutocomplete("books-search-input", "books-search-dropdown");

    
    // ---------- 10. Profile page: Instagram-style tabs ----------
    const profileTabs = document.querySelectorAll(".insta-tab");
    if (profileTabs.length > 0) {
        profileTabs.forEach(function (tab) {
            tab.addEventListener("click", function () {
                profileTabs.forEach(function (t) { t.classList.remove("active"); });
                tab.classList.add("active");

                document.querySelectorAll(".insta-tab-panel").forEach(function (panel) {
                    panel.hidden = true;
                });
                document.getElementById("tab-" + tab.dataset.tab).hidden = false;
            });
        });
    }

        // ---------- 11. Password show/hide toggle (single morphing eye icon) ----------
    document.querySelectorAll(".password-toggle-btn").forEach(function (button) {
        button.addEventListener("click", function () {
            const input = document.getElementById(button.dataset.target);
            const isCurrentlyHidden = input.type === "password";

            input.type = isCurrentlyHidden ? "text" : "password";
            button.classList.toggle("is-visible", isCurrentlyHidden);
            button.setAttribute("aria-label", isCurrentlyHidden ? "Hide password" : "Show password");
        });
    });
    
    // ---------- 12. Share book button ----------
    const shareBtn = document.getElementById("share-book-btn");
    if (shareBtn) {
        shareBtn.addEventListener("click", function () {
            const url = shareBtn.dataset.url;
            const title = shareBtn.dataset.title;

            if (navigator.share) {
                navigator.share({ title: title, url: url }).catch(function () {});
            } else {
                navigator.clipboard.writeText(url).then(function () {
                    const originalText = shareBtn.textContent;
                    shareBtn.textContent = "✅ Link Copied!";
                    setTimeout(function () { shareBtn.textContent = originalText; }, 2000);
                }).catch(function () {
                    alert("Copy this link: " + url);
                });
            }
        });
    }
    
    // ---------- 13. Admin bulk select & delete ----------
    const selectAllCheckbox = document.getElementById("select-all-books");
    const bulkBar = document.getElementById("bulk-actions-bar");
    const bulkCountLabel = document.getElementById("bulk-selected-count");

    if (selectAllCheckbox) {
        function getRowCheckboxes() {
            return document.querySelectorAll(".book-row-checkbox");
        }

        function updateBulkBar() {
            const checked = document.querySelectorAll(".book-row-checkbox:checked").length;
            bulkBar.hidden = checked === 0;
            bulkCountLabel.textContent = checked + " selected";
        }

        selectAllCheckbox.addEventListener("change", function () {
            getRowCheckboxes().forEach(function (cb) { cb.checked = selectAllCheckbox.checked; });
            updateBulkBar();
        });

        getRowCheckboxes().forEach(function (cb) {
            cb.addEventListener("change", updateBulkBar);
        });
    }

    
    // ---------- 14. Fix: cached book cover images that never fire onload ----------
    document.querySelectorAll(".cover-img").forEach(function (img) {
        if (img.complete) {
            // Image was already loaded from browser cache before this script ran —
            // the onload event will never fire for it, so mark it visible immediately.
            img.classList.add("loaded");
        }
    });

});