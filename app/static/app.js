let currentImageData = null;
let pollTimer = null;
let lastGenerations = [];

const PAGE_SIZE = 15;
let loadedCount = 0;
let totalCount = 0;
let loadingMore = false;

// === DOM Elements ===
const dropZone = document.getElementById("dropZone");
const imageInput = document.getElementById("imageInput");
const imagePreview = document.getElementById("imagePreview");
const uploadPlaceholder = document.getElementById("uploadPlaceholder");
const clearImageBtn = document.getElementById("clearImage");
const promptInput = document.getElementById("promptInput");
const durationSlider = document.getElementById("duration");
const durationValue = document.getElementById("durationValue");
const goButton = document.getElementById("goButton");
const historyPanel = document.getElementById("historyPanel");
const historyEmpty = document.getElementById("historyEmpty");

// === Image Upload ===
dropZone.addEventListener("click", () => imageInput.click());

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});

imageInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

function handleFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        currentImageData = e.target.result;
        imagePreview.src = currentImageData;
        imagePreview.hidden = false;
        uploadPlaceholder.hidden = true;
        clearImageBtn.hidden = false;
    };
    reader.readAsDataURL(file);
}

clearImageBtn.addEventListener("click", () => {
    currentImageData = null;
    imagePreview.src = "";
    imagePreview.hidden = true;
    uploadPlaceholder.hidden = false;
    clearImageBtn.hidden = true;
    imageInput.value = "";
});

// === Duration Slider ===
durationSlider.addEventListener("input", () => {
    durationValue.textContent = durationSlider.value + "s";
});

// === Submit Generation ===
goButton.addEventListener("click", async () => {
    const prompt = promptInput.value.trim();
    if (!prompt) {
        promptInput.focus();
        return;
    }

    goButton.disabled = true;
    goButton.textContent = "Submitting...";

    try {
        const body = {
            prompt,
            image_data: currentImageData,
            duration: parseInt(durationSlider.value),
            aspect_ratio: document.getElementById("aspectRatio").value,
            resolution: document.getElementById("resolution").value,
        };

        const resp = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || "Request failed");
        }

        await refreshHistory();
        startPolling();
    } catch (err) {
        alert("Error: " + err.message);
    } finally {
        goButton.disabled = false;
        goButton.textContent = "Go";
    }
});

// === History ===

// Refresh only the first page (for polling status updates)
async function refreshHistory() {
    try {
        const resp = await fetch(`/api/generations?limit=${PAGE_SIZE}&offset=0`);
        const data = await resp.json();
        totalCount = data.total;
        const generations = data.items;
        // On first load, set loadedCount; on subsequent polls, keep existing loadedCount
        // so infinite scroll position is preserved
        if (loadedCount < PAGE_SIZE) {
            loadedCount = generations.length;
        }
        renderHistory(generations);
    } catch (err) {
        console.error("Failed to refresh history:", err);
    }
}

// Load the next page and append
async function loadMore() {
    if (loadingMore || loadedCount >= totalCount) return;
    loadingMore = true;
    showLoadingIndicator(true);
    try {
        const resp = await fetch(`/api/generations?limit=${PAGE_SIZE}&offset=${loadedCount}`);
        const data = await resp.json();
        totalCount = data.total;
        const newItems = data.items;
        if (newItems.length === 0) return;

        // Append new cards
        for (const gen of newItems) {
            const card = document.createElement("div");
            card.className = "history-card";
            card.dataset.status = gen.status;
            card.dataset.id = String(gen.id);
            card.innerHTML = buildCardHtml(gen);
            historyPanel.appendChild(card);
        }

        lastGenerations = lastGenerations.concat(newItems);
        loadedCount = lastGenerations.length;
    } catch (err) {
        console.error("Failed to load more:", err);
    } finally {
        loadingMore = false;
        showLoadingIndicator(false);
    }
}

function showLoadingIndicator(show) {
    let el = document.getElementById("loadMoreSpinner");
    if (show) {
        if (!el) {
            el = document.createElement("div");
            el.id = "loadMoreSpinner";
            el.className = "load-more-spinner";
            el.innerHTML = '<div class="spinner"></div>';
            historyPanel.appendChild(el);
        }
    } else if (el) {
        el.remove();
    }
}

function buildCardHtml(gen) {
    let mainContent = "";

    if (gen.status === "pending") {
        mainContent = `
            <div class="spinner-container">
                <div class="spinner"></div>
                <span class="spinner-text">Generating video...</span>
            </div>`;
    } else if (gen.status === "done" && gen.video_filename) {
        const videoUrl = `/api/videos/${escapeAttr(gen.video_filename)}`;
        mainContent = `
            <div class="card-video">
                <video controls preload="metadata" src="${videoUrl}"></video>
            </div>
            <div class="card-actions">
                <a href="${videoUrl}" download class="download-btn">Download</a>
            </div>`;
    } else if (gen.status === "rejected") {
        mainContent = `<div class="card-rejected">Rejected by content moderation</div>`;
    } else if (gen.status === "failed" || gen.status === "expired") {
        mainContent = `<div class="card-error">${escapeHtml(gen.error_message || gen.status)}</div>`;
    }

    const thumbHtml = gen.has_source_image
        ? `<img src="/api/generations/${gen.id}/image" class="card-thumb" data-gen-id="${gen.id}" title="Click to use this image" loading="lazy">`
        : "";

    return `<div class="card-content">
                ${mainContent}
                <div class="card-prompt" data-prompt="${escapeAttr(gen.prompt)}" title="Click to use this prompt">${escapeHtml(gen.prompt)}</div>
                <div class="card-meta">${gen.duration}s &middot; ${gen.aspect_ratio} &middot; ${gen.resolution}</div>
            </div>
            ${thumbHtml}`;
}

function renderHistory(generations) {
    if (generations.length === 0 && totalCount === 0) {
        historyEmpty.hidden = false;
        return;
    }
    historyEmpty.hidden = true;

    const existingCards = historyPanel.querySelectorAll(".history-card");
    const existingById = new Map();
    existingCards.forEach((card) => {
        existingById.set(card.dataset.id, card);
    });

    const prevById = new Map();
    lastGenerations.forEach((g) => prevById.set(String(g.id), g));

    // Update in-place: walk the new list and ensure each card is at the right position
    let refNode = historyEmpty.nextSibling; // first card slot

    for (const gen of generations) {
        const genId = String(gen.id);
        const existing = existingById.get(genId);
        const prev = prevById.get(genId);

        let card;
        if (existing && prev && prev.status === gen.status) {
            // No change — reuse as-is
            card = existing;
            existingById.delete(genId);
        } else if (existing) {
            // Status changed — update content
            existing.dataset.status = gen.status;
            existing.innerHTML = buildCardHtml(gen);
            card = existing;
            existingById.delete(genId);
        } else {
            // New card
            card = document.createElement("div");
            card.className = "history-card";
            card.dataset.status = gen.status;
            card.dataset.id = genId;
            card.innerHTML = buildCardHtml(gen);
        }

        // Ensure card is at the correct position without moving unchanged nodes
        if (card !== refNode) {
            historyPanel.insertBefore(card, refNode);
        } else {
            refNode = refNode.nextSibling;
        }
    }

    // Remove cards that are no longer in the set
    existingById.forEach((card) => card.remove());

    lastGenerations = generations;
}

// === Infinite scroll ===
function setupInfiniteScroll() {
    // Desktop: history-panel scrolls independently
    historyPanel.addEventListener("scroll", () => {
        if (loadedCount >= totalCount) return;
        if (historyPanel.scrollTop + historyPanel.clientHeight >= historyPanel.scrollHeight - 300) {
            loadMore();
        }
    });
    // Mobile: the whole page scrolls
    window.addEventListener("scroll", () => {
        if (loadedCount >= totalCount) return;
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 300) {
            loadMore();
        }
    });
}

// === Click handlers (event delegation) ===
historyPanel.addEventListener("click", (e) => {
    const promptEl = e.target.closest(".card-prompt");
    if (promptEl) {
        promptInput.value = promptEl.dataset.prompt;
        promptInput.focus();
        return;
    }

    const thumbEl = e.target.closest(".card-thumb");
    if (thumbEl) {
        fillImageFromGeneration(parseInt(thumbEl.dataset.genId));
    }
});

async function fillImageFromGeneration(genId) {
    try {
        const resp = await fetch(`/api/generations/${genId}/image`);
        if (!resp.ok) return;
        const blob = await resp.blob();
        const reader = new FileReader();
        reader.onload = (e) => {
            currentImageData = e.target.result;
            imagePreview.src = currentImageData;
            imagePreview.hidden = false;
            uploadPlaceholder.hidden = true;
            clearImageBtn.hidden = false;
        };
        reader.readAsDataURL(blob);
    } catch (err) {
        console.error("Failed to load image:", err);
    }
}

// === Polling ===
function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(async () => {
        await refreshHistory();
        const pending = historyPanel.querySelectorAll('.history-card[data-status="pending"]');
        if (pending.length === 0) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }, 3000);
}

// === Utilities ===
function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

// === Balance ===
const balanceEl = document.getElementById("balance");

async function refreshBalance() {
    try {
        const resp = await fetch("/api/balance");
        const data = await resp.json();
        if (data.error) {
            balanceEl.textContent = "";
            return;
        }
        const parts = [];
        if (data.remaining > 0) {
            parts.push(`Credit: <span class="amount">$${(data.remaining / 100).toFixed(2)}</span>`);
        }
        if (data.invoice > 0) {
            parts.push(`Invoice: <span class="amount invoice">$${(data.invoice / 100).toFixed(2)}</span>`);
        }
        balanceEl.innerHTML = parts.join(" &middot; ");
    } catch (err) {
        console.error("Failed to fetch balance:", err);
    }
}

// === Init ===
refreshHistory().then(() => {
    const pending = historyPanel.querySelectorAll('.history-card[data-status="pending"]');
    if (pending.length > 0) startPolling();
});
setupInfiniteScroll();
refreshBalance();
setInterval(refreshBalance, 15000);
