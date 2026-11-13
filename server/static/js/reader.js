import { load, save } from "./common.js";

(function () {
  var d = document.documentElement,
    KEY = "reader";
  var state = load(KEY);
  var size = state.size || parseInt(getComputedStyle(d).getPropertyValue("--read-size"), 10) || 18;

  var bar = document.getElementById("bar"),
    nav = document.getElementById("nav"),
    prog = document.getElementById("progress"),
    aa = document.getElementById("aa"),
    panel = document.getElementById("settings");

  const chapterId = bar.dataset.chapterId;
  var lastY = state[`lastY-${chapterId}`] || 0;
  if (lastY > 0) {
    window.scrollTo(0, lastY);
  }

  save(`book_${bar.dataset.bookId}`, { lastChapterIndex: bar.dataset.chapterIndex });

  // Expose the function globally to the window object so HTML inline click handlers can find it
  window.handleChapterTranslation = async function (btnElement) {
    if (!btnElement) return;

    // 1. UI Feedback: Disable button and show loading text
    btnElement.disabled = true;
    const originalText = btnElement.textContent;
    btnElement.textContent = "Đang dịch...";

    try {
      var response = await fetch("/api/v1/translate/chapter/" + encodeURIComponent(chapterId), {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Không thể dịch chương (HTTP " + response.status + ").");
      }
      window.location.reload();
    } catch (error) {
      alert("Có lỗi xảy ra khi dịch: " + error.message);

      // 3. Fallback: Re-enable the button on failure so user can try again
      btnElement.disabled = false;
      btnElement.textContent = originalText;
    }
  };

  /* Settings panel */
  function setPanel(open) {
    panel.hidden = !open;
    aa.setAttribute("aria-expanded", open);
  }
  aa.addEventListener("click", function (e) {
    e.stopPropagation();
    setPanel(panel.hidden);
  });
  document.addEventListener("click", function (e) {
    if (!panel.contains(e.target)) setPanel(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setPanel(false);
    var a = e.key === "ArrowLeft" ? "a[rel=prev]" : e.key === "ArrowRight" ? "a[rel=next]" : null;
    if (a && !/input|textarea/i.test(e.target.tagName)) {
      var l = nav.querySelector(a);
      if (l) location.href = l.href;
    }
  });

  function markTheme() {
    var t = d.dataset.theme || "light";
    panel.querySelectorAll("[data-theme-set]").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.themeSet === t);
    });
  }
  panel.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.size) {
      size = Math.min(30, Math.max(14, size + 2 * Number(b.dataset.size)));
      d.style.setProperty("--read-size", size + "px");
      state.size = size;
    }
    if (b.dataset.themeSet) {
      d.dataset.theme = b.dataset.themeSet;
      state.theme = b.dataset.themeSet;
      markTheme();
    }
    save(KEY, state);
  });
  markTheme();

  /* Reading progress + hide bars while scrolling down, show when scrolling up */
  var lastY = window.scrollY,
    ticking = false;
  function onScroll() {
    var y = window.scrollY,
      max = Math.max(0, d.scrollHeight - window.innerHeight);
    prog.style.width = (max > 0 ? Math.max(0, Math.min(100, (y / max) * 100)) : 0) + "%";
    var atStart = y <= 2,
      atEnd = max > 0 && y >= max - 2;
    var hide = !atStart && !atEnd && y > lastY && y > 120 && panel.hidden;
    if (Math.abs(y - lastY) > 8 || atStart || atEnd) {
      bar.classList.toggle("is-hidden", hide);
      nav.classList.toggle("is-hidden", hide);
      lastY = y;
    }
    ticking = false;
  }
  window.addEventListener(
    "scroll",
    function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(onScroll);
      }
      state[`lastY-${chapterId}`] = window.scrollY;
      save(KEY, state);
    },
    { passive: true },
  );
  onScroll();
})();
