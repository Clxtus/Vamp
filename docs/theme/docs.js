(function () {
  const root = document.documentElement;
  const entries = window.VAMP_SEARCH || [];

  document.querySelector(".theme").addEventListener("click", () => {
    const dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("vamp-theme", root.dataset.theme); } catch (ignored) {}
  });

  document.querySelector(".mobile-bar .menu").addEventListener("click", () => {
    document.body.classList.toggle("menu-open");
  });
  document.querySelector(".page").addEventListener("click", () => document.body.classList.remove("menu-open"));

  const current = document.querySelector(".sidebar-nav a.current");
  if (current) current.scrollIntoView({ block: "center" });

  for (const button of document.querySelectorAll(".code .copy")) {
    button.addEventListener("click", async () => {
      const text = button.parentElement.querySelector("pre").innerText;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
      } catch (ignored) {
        button.textContent = "Press Ctrl+C";
      }
      setTimeout(() => { button.textContent = "Copy"; }, 1500);
    });
  }

  function escape(text) {
    return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  }

  function search(query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    const results = [];
    for (const entry of entries) {
      const title = entry.title.toLowerCase();
      const page = entry.page.toLowerCase();
      const text = entry.text.toLowerCase();
      let score = 0;
      let found = true;
      for (const word of words) {
        let points = 0;
        if (title === word) points += 60;
        if (title.includes(word)) points += 25;
        if (page.includes(word)) points += 8;
        const count = text.split(word).length - 1;
        points += Math.min(count, 10);
        if (!points) { found = false; break; }
        score += points;
      }
      if (found) results.push({ entry, score });
    }
    return results.sort((a, b) => b.score - a.score).map((result) => result.entry);
  }

  function snippet(text, query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const lower = text.toLowerCase();
    let start = 0;
    for (const word of words) {
      const at = lower.indexOf(word);
      if (at >= 0) { start = Math.max(0, at - 60); break; }
    }
    let piece = escape(text.slice(start, start + 220));
    for (const word of words) {
      const pattern = new RegExp(word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      piece = piece.replace(pattern, (match) => `<mark>${match}</mark>`);
    }
    return (start > 0 ? "… " : "") + piece + (start + 220 < text.length ? " …" : "");
  }

  const input = document.querySelector(".search input");
  const box = document.querySelector(".search-results");
  let active = -1;

  function show() {
    const query = input.value.trim();
    active = -1;
    if (!query) { box.hidden = true; return; }
    const found = search(query).slice(0, 8);
    box.innerHTML = found.length
      ? found.map((entry) => `<a href="${entry.url}">${escape(entry.title)}` +
          (entry.title !== entry.page ? `<small>${escape(entry.page)}</small>` : "") + "</a>").join("")
      : '<div class="empty">No results</div>';
    box.hidden = false;
  }

  input.addEventListener("input", show);
  input.addEventListener("focus", show);
  input.addEventListener("keydown", (event) => {
    const links = [...box.querySelectorAll("a")];
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!links.length) return;
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
      links.forEach((link, index) => link.classList.toggle("active", index === active));
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      location.href = links[active].href;
    } else if (event.key === "Escape") {
      box.hidden = true;
      input.blur();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".search")) box.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && document.activeElement !== input) {
      event.preventDefault();
      input.focus();
    }
  });

  const list = document.querySelector(".search-page-results");
  if (list) {
    const query = new URLSearchParams(location.search).get("q") || "";
    input.value = query;
    const found = search(query);
    document.querySelector(".search-summary").textContent = query
      ? `${found.length} result${found.length === 1 ? "" : "s"} for “${query}”`
      : "Type in the search box to search the documentation.";
    list.innerHTML = found.slice(0, 60).map((entry) =>
      `<li><a href="${entry.url}">${escape(entry.title)}</a>` +
      `<small>${escape(entry.page)}</small><p>${snippet(entry.text, query)}</p></li>`).join("");
  }

  const toc = [...document.querySelectorAll(".toc a")];
  if (toc.length && "IntersectionObserver" in window) {
    const targets = toc.map((link) => document.getElementById(decodeURIComponent(link.hash.slice(1)))).filter(Boolean);
    const observer = new IntersectionObserver((seen) => {
      for (const item of seen) {
        if (item.isIntersecting) {
          toc.forEach((link) => link.classList.toggle("active", link.hash === "#" + item.target.id));
          break;
        }
      }
    }, { rootMargin: "-70px 0px -70% 0px" });
    targets.forEach((target) => observer.observe(target));
  }
})();
