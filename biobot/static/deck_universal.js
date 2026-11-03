/**
 * deck_universal.js — LLM-powered deck visualization
 *
 * Architecture:
 * - The deck panel contains a sandboxed iframe (the "blank paper")
 * - The LLM generates complete HTML/CSS/JS that renders inside it
 * - User interactions in the iframe send postMessage to the parent
 * - The parent sends changes to the LLM to update code + visualization
 *
 * This works for ANY liquid handler — the LLM draws whatever is appropriate.
 */

// ============================================================
// State
// ============================================================

let currentCode = null;
let currentVisualizationHtml = null;

// ============================================================
// Generate visualization from code
// ============================================================

async function generateDeckVisualization(code) {
  currentCode = code;

  const container = document.getElementById("deck-svg-container");
  if (!container) return;

  // Show loading
  container.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:200px;gap:12px;">
      <div style="width:24px;height:24px;border:3px solid #333;border-top-color:#00ff99;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
      <span style="color:#888;font-size:0.85rem;">Generating deck visualization...</span>
    </div>
    <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
  `;

  // Open the panel
  const panel = document.getElementById("deck-panel");
  const chatPanel = document.getElementById("chat-panel");
  const toggleBtn = document.getElementById("deck-toggle-btn");
  if (panel) panel.classList.remove("hidden");
  if (chatPanel) chatPanel.classList.add("with-deck");
  if (toggleBtn) toggleBtn.classList.add("active");

  try {
    const res = await fetch("/deck/visualize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    if (!res.ok) {
      container.innerHTML = '<p class="deck-empty-message">Failed to generate visualization</p>';
      return;
    }

    const data = await res.json();
    if (data.error) {
      container.innerHTML = `<p class="deck-empty-message">${data.error}</p>`;
      return;
    }

    currentVisualizationHtml = data.html;
    renderVisualization(data.html);

  } catch (e) {
    console.error("Visualization error:", e);
    container.innerHTML = '<p class="deck-empty-message">Error generating visualization</p>';
  }
}

// ============================================================
// Render HTML in iframe
// ============================================================

function renderVisualization(html) {
  const container = document.getElementById("deck-svg-container");
  if (!container) return;

  container.innerHTML = "";

  const iframe = document.createElement("iframe");
  iframe.id = "deck-iframe";
  iframe.className = "deck-iframe";
  iframe.sandbox = "allow-scripts allow-same-origin";
  iframe.setAttribute("frameborder", "0");

  container.appendChild(iframe);

  // Write HTML into iframe
  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(html);
  doc.close();

  // Auto-resize iframe to content height
  iframe.onload = () => {
    try {
      const body = iframe.contentDocument.body;
      if (body) {
        const resizeObserver = new ResizeObserver(() => {
          iframe.style.height = body.scrollHeight + "px";
        });
        resizeObserver.observe(body);
        iframe.style.height = body.scrollHeight + "px";
      }
    } catch (e) {
      // Fallback height
      iframe.style.height = "600px";
    }
  };
}

// ============================================================
// PostMessage Bridge — listen for changes from the iframe
// ============================================================

window.addEventListener("message", async (event) => {
  // Only handle messages with our protocol
  if (!event.data || event.data.type !== "deck_change") return;
  if (!currentCode || !currentVisualizationHtml) return;

  const change = event.data.change;
  if (!change) return;

  console.log("Deck change received:", change);

  // Show updating indicator
  const info = document.getElementById("deck-info");
  if (info) {
    info.innerHTML = `<div style="color:var(--accent);font-size:0.8rem;padding:8px;">Updating code...</div>`;
  }

  try {
    const res = await fetch("/deck/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: currentCode,
        html: currentVisualizationHtml,
        change: change,
      }),
    });

    if (!res.ok) return;

    const data = await res.json();

    if (data.code) {
      currentCode = data.code;
      window._deckOriginalCode = data.code;
      // Update the code block in chat
      updateCodeInChat(data.code);
    }

    if (data.html) {
      currentVisualizationHtml = data.html;
      renderVisualization(data.html);
    }

    if (info) info.innerHTML = "";

  } catch (e) {
    console.error("Deck update error:", e);
    if (info) info.innerHTML = `<div style="color:#ff4d4d;font-size:0.8rem;padding:8px;">Update failed</div>`;
  }
});

// ============================================================
// Update code in chat
// ============================================================

function updateCodeInChat(newCode) {
  const codeBlocks = document.querySelectorAll(".code-block-pre code");
  if (codeBlocks.length === 0) return;
  const lastBlock = codeBlocks[codeBlocks.length - 1];
  lastBlock.textContent = newCode;
  const wrapper = lastBlock.closest(".code-block-wrapper");
  if (wrapper) {
    wrapper.classList.add("code-updated");
    setTimeout(() => wrapper.classList.remove("code-updated"), 1500);
  }
}

// ============================================================
// Panel controls
// ============================================================

function toggleDeckPanel() {
  const panel = document.getElementById("deck-panel");
  const chat = document.getElementById("chat-panel");
  const btn = document.getElementById("deck-toggle-btn");
  if (!panel || !chat) return;
  const hidden = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !hidden);
  chat.classList.toggle("with-deck", hidden);
  if (btn) btn.classList.toggle("active", hidden);
}

function closeDeckPanel() {
  const panel = document.getElementById("deck-panel");
  const chat = document.getElementById("chat-panel");
  const btn = document.getElementById("deck-toggle-btn");
  if (panel) panel.classList.add("hidden");
  if (chat) chat.classList.remove("with-deck");
  if (btn) btn.classList.remove("active");
}

function clearDeckPanel() {
  closeDeckPanel();
  currentCode = null;
  currentVisualizationHtml = null;
  const c = document.getElementById("deck-svg-container");
  if (c) c.innerHTML = '<p class="deck-empty-message">Generate a protocol to see the deck layout</p>';
  const i = document.getElementById("deck-info");
  if (i) i.innerHTML = "";
}

// ============================================================
// Entry point — called by script.js
// ============================================================

async function parseDeckFromCode(code) {
  return generateDeckVisualization(code);
}

// ============================================================
// Init
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("deck-toggle-btn");
  const closeBtn = document.getElementById("deck-close-btn");
  if (toggleBtn) toggleBtn.addEventListener("click", toggleDeckPanel);
  if (closeBtn) closeBtn.addEventListener("click", closeDeckPanel);
});

// Expose
window.parseDeckFromCode = parseDeckFromCode;
window.clearDeckPanel = clearDeckPanel;
window.toggleDeckPanel = toggleDeckPanel;
window.updateCodeInChat = updateCodeInChat;