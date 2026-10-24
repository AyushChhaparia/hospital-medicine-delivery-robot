/**
 * Hospital Medicine Delivery System - Medicine Room Manager Actions & Telemetry
 */

function openOrderModal(orderId) {
  fetch(`/manager/order/${orderId}/details`)
    .then(res => res.json())
    .then(order => {
      document.getElementById("modal-order-number").textContent = order.order_number;
      document.getElementById("modal-order-room").textContent = order.room_name;
      document.getElementById("modal-order-priority").textContent = `Priority ${order.priority}`;
      document.getElementById("modal-order-status").textContent = order.status;
      document.getElementById("modal-order-robot").textContent = order.robot_name || "Unassigned";
      document.getElementById("modal-order-created").textContent = order.created_at || "-";
      document.getElementById("modal-order-notes").textContent = order.manager_notes || "None";

      const itemsBody = document.getElementById("modal-items-table-body");
      if (itemsBody) {
        let html = "";
        order.items.forEach(item => {
          html += `
            <tr>
              <td><strong>${escapeHtml(item.medicine_name)}</strong></td>
              <td>${item.quantity} ${escapeHtml(item.unit)}</td>
            </tr>
          `;
        });
        itemsBody.innerHTML = html;
      }

      const modal = document.getElementById("orderDetailsModal");
      if (modal) modal.classList.add("active");
    })
    .catch(err => {
      alert("Failed to load order details.");
    });
}

function closeOrderModal() {
  const modal = document.getElementById("orderDetailsModal");
  if (modal) modal.classList.remove("active");
}

function confirmDispatchAction(orderNumber, robotName) {
  return confirm(
    `CONFIRM DISPATCH & STOCK DEDUCTION:\n\n` +
    `Are you sure you want to dispatch Order ${orderNumber} using ${robotName}?\n` +
    `This will lock the cargo box and deduct physical inventory from the pharmacy database.`
  );
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
