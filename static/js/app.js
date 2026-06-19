document.addEventListener("DOMContentLoaded", () => {
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

  document.querySelectorAll(".card, .kpi-card, .stat-card").forEach((el, i) => {
    el.style.animationDelay = `${Math.min(i * 40, 400)}ms`;
    el.classList.add("reveal-item");
  });
});
