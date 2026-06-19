document.addEventListener("DOMContentLoaded", () => {
  function getToastStack() {
    return document.getElementById("appToastStack");
  }

  function bindToastClose(toast, duration = 5500) {
    const close = () => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 320);
    };

    toast.querySelector(".app-toast__close")?.addEventListener("click", close);
    if (duration > 0) {
      setTimeout(close, duration);
    }
  }

  function showToast(message, type = "success", detail = "", duration = 5500) {
    const container = getToastStack();
    if (!container || !message) return;

    const toast = document.createElement("div");
    toast.className = `app-toast app-toast--${type}`;
    toast.setAttribute("role", "alert");

    const icon =
      type === "success"
        ? "bi-check-circle-fill"
        : type === "error"
          ? "bi-exclamation-circle-fill"
          : "bi-info-circle-fill";

    const detailHtml = detail
      ? `<span class="app-toast__detail">${detail.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</span>`
      : "";

    toast.innerHTML = `
      <div class="app-toast__body">
        <i class="bi ${icon}"></i>
        <div class="app-toast__text">
          <strong>${message.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</strong>
          ${detailHtml}
        </div>
      </div>
      <button type="button" class="app-toast__close" aria-label="Fechar">
        <i class="bi bi-x-lg"></i>
      </button>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("show"));
    bindToastClose(toast, duration);
  }

  window.showToast = showToast;

  document.querySelectorAll("#appToastStack [data-app-toast]").forEach((toast) => {
    bindToastClose(toast, 5500);
  });

  const params = new URLSearchParams(window.location.search);
  if (params.has("toast") && params.has("msg") && !document.querySelector("#appToastStack [data-app-toast]")) {
    showToast(
      decodeURIComponent(params.get("msg")),
      params.get("toast") || "info",
      params.get("detalhe") ? decodeURIComponent(params.get("detalhe")) : ""
    );
  }

  if (params.has("toast") || params.has("msg") || params.has("detalhe")) {
    params.delete("toast");
    params.delete("msg");
    params.delete("detalhe");
    const query = params.toString();
    window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }

  const sidebar = document.getElementById("appSidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  const toggle = document.getElementById("sidebarToggle");

  function openSidebar() {
    sidebar?.classList.add("open");
    backdrop?.classList.add("visible");
    toggle?.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
  }

  function closeSidebar() {
    sidebar?.classList.remove("open");
    backdrop?.classList.remove("visible");
    toggle?.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
  }

  toggle?.addEventListener("click", () => {
    if (sidebar?.classList.contains("open")) closeSidebar();
    else openSidebar();
  });

  backdrop?.addEventListener("click", closeSidebar);

  document.querySelectorAll(".sidebar-link").forEach((link) => {
    link.addEventListener("click", () => {
      if (window.innerWidth < 992) closeSidebar();
    });
  });

  document.querySelectorAll("details.edit-details").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (!details.open) return;
      document.querySelectorAll("details.edit-details[open]").forEach((other) => {
        if (other !== details) other.open = false;
      });
    });
  });

  document.querySelectorAll(".alert-app").forEach((alert) => {
    const closeBtn = document.createElement("button");
    closeBtn.className = "alert-close";
    closeBtn.setAttribute("aria-label", "Fechar");
    closeBtn.innerHTML = '<i class="bi bi-x-lg"></i>';
    closeBtn.addEventListener("click", () => {
      alert.style.opacity = "0";
      alert.style.transform = "translateY(-8px)";
      setTimeout(() => alert.remove(), 250);
    });
    alert.appendChild(closeBtn);
  });

  const sectionNav = document.querySelector(".section-nav");
  if (sectionNav) {
    const links = [...sectionNav.querySelectorAll("a[href^='#']")];
    const sections = links
      .map((a) => document.querySelector(a.getAttribute("href")))
      .filter(Boolean);

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const id = entry.target.id;
          links.forEach((a) => {
            a.classList.toggle("active", a.getAttribute("href") === `#${id}`);
          });
        });
      },
      { rootMargin: "-30% 0px -60% 0px", threshold: 0 }
    );

    sections.forEach((s) => observer.observe(s));
  }

  document.querySelectorAll(".lista-expansivel__toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const container = btn.closest(".lista-expansivel");
      if (!container) return;

      const expanded = container.classList.toggle("is-expanded");
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");

      const labelMore = btn.querySelector(".lista-expansivel__label-more");
      const labelLess = btn.querySelector(".lista-expansivel__label-less");
      if (labelMore) labelMore.hidden = expanded;
      if (labelLess) labelLess.hidden = !expanded;
    });
  });

  document.querySelectorAll(".card, .kpi-card, .stat-card").forEach((el, i) => {
    el.style.animationDelay = `${Math.min(i * 40, 400)}ms`;
    el.classList.add("reveal-item");
  });
});
