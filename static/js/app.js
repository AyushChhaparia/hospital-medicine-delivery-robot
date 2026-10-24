/**
 * Hospital Medicine Delivery System - Ward Ordering & Interactions
 */

// In-memory cart for current session
let cart = [];

function addToCart(medId, medName, unit, maxAvailable) {
  const inputEl = document.getElementById(`qty-${medId}`);
  const qty = parseInt(inputEl ? inputEl.value : 1, 10);

  if (isNaN(qty) || qty <= 0) {
    alert("Please enter a valid quantity greater than zero.");
    return;
  }

  const existing = cart.find(item => item.medicine_id === medId);
  const currentInCart = existing ? existing.quantity : 0;
  const newTotal = currentInCart + qty;

  if (newTotal > maxAvailable) {
    alert(`Cannot add ${qty} ${unit}. Available stock is ${maxAvailable} (You already have ${currentInCart} in cart).`);
    return;
  }

  if (existing) {
    existing.quantity = newTotal;
  } else {
    cart.push({
      medicine_id: medId,
      name: medName,
      unit: unit,
      quantity: qty,
      max_available: maxAvailable
    });
  }

  renderCart();
}

function updateCartQty(medId, newQty) {
  const qty = parseInt(newQty, 10);
  const item = cart.find(i => i.medicine_id === medId);
  if (!item) return;

  if (isNaN(qty) || qty <= 0) {
    removeFromCart(medId);
    return;
  }

  if (qty > item.max_available) {
    alert(`Requested quantity exceeds available stock (${item.max_available} ${item.unit}).`);
    item.quantity = item.max_available;
  } else {
    item.quantity = qty;
  }

  renderCart();
}

function removeFromCart(medId) {
  cart = cart.filter(item => item.medicine_id !== medId);
  renderCart();
}

function clearCart() {
  cart = [];
  renderCart();
}

function renderCart() {
  const container = document.getElementById("cart-items-container");
  const emptyMsg = document.getElementById("cart-empty-message");
  const totalCountEl = document.getElementById("cart-total-count");
  const submitBtn = document.getElementById("submit-order-btn");

  if (!container) return;

  if (cart.length === 0) {
    container.innerHTML = "";
    if (emptyMsg) emptyMsg.style.display = "block";
    if (totalCountEl) totalCountEl.textContent = "0";
    if (submitBtn) submitBtn.disabled = true;
    return;
  }

  if (emptyMsg) emptyMsg.style.display = "none";
  if (submitBtn) submitBtn.disabled = false;

  let totalItems = 0;
  let html = "";

  cart.forEach(item => {
    totalItems += item.quantity;
    html += `
      <tr>
        <td><strong>${escapeHtml(item.name)}</strong></td>
        <td>
          <input type="number" class="qty-input" min="1" max="${item.max_available}" 
                 value="${item.quantity}" onchange="updateCartQty(${item.medicine_id}, this.value)">
          <span style="font-size: 0.8rem; color: #64748b;">${escapeHtml(item.unit)}</span>
        </td>
        <td>
          <button type="button" class="btn btn-danger btn-sm" onclick="removeFromCart(${item.medicine_id})">
            &times;
          </button>
        </td>
      </tr>
    `;
  });

  container.innerHTML = html;
  if (totalCountEl) totalCountEl.textContent = totalItems;
}

function filterMedicines() {
  const searchInput = document.getElementById("medicine-search");
  const categorySelect = document.getElementById("category-filter");
  const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : "";
  const selectedCat = categorySelect ? categorySelect.value : "";

  const items = document.querySelectorAll(".medicine-item-card");

  items.forEach(card => {
    const name = card.getAttribute("data-name") || "";
    const cat = card.getAttribute("data-category") || "";

    const matchesSearch = !searchTerm || name.includes(searchTerm);
    const matchesCat = !selectedCat || cat === selectedCat;

    if (matchesSearch && matchesCat) {
      card.style.display = "flex";
    } else {
      card.style.display = "none";
    }
  });
}

function submitOrderWithConfirmation(wardCode, csrfToken) {
  if (cart.length === 0) {
    alert("Please add medicines to your cart before submitting.");
    return;
  }

  const itemsSummary = cart.map(i => `${i.name} (${i.quantity} ${i.unit})`).join("\n");
  const confirmMsg = `Please confirm your medicine delivery order:\n\n${itemsSummary}\n\nSubmit this order now?`;

  if (!confirm(confirmMsg)) {
    return;
  }

  const notesInput = document.getElementById("order-notes");
  const notes = notesInput ? notesInput.value.trim() : "";

  const submitBtn = document.getElementById("submit-order-btn");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting Order...";
  }

  fetch(`/ward/${wardCode}/order`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({
      items: cart.map(i => ({ medicine_id: i.medicine_id, quantity: i.quantity })),
      notes: notes,
    }),
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        alert(data.message || "Order placed successfully!");
        cart = [];
        window.location.reload();
      } else {
        alert("Order failed: " + (data.error || "Unknown error"));
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Place Medicine Order";
        }
      }
    })
    .catch(err => {
      alert("Network error while submitting order. Please check connection.");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Place Medicine Order";
      }
    });
}

function escapeHtml(text) {
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}
