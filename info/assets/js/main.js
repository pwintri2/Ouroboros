const revealElements = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) {
          return;
        }

        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    {
      threshold: 0.14,
      rootMargin: "0px 0px -8% 0px",
    },
  );

  revealElements.forEach((element) => observer.observe(element));
} else {
  revealElements.forEach((element) => element.classList.add("is-visible"));
}

const header = document.querySelector(".site-header");

const updateHeader = () => {
  if (!header) {
    return;
  }

  header.classList.toggle("is-scrolled", window.scrollY > 12);
};

updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

document.querySelectorAll("[data-year]").forEach((element) => {
  element.textContent = new Date().getFullYear();
});

const introOverlay = document.querySelector("[data-intro-overlay]");
const introVideo = document.querySelector("[data-intro-video]");
const introClose = document.querySelector("[data-intro-close]");

if (introOverlay && introVideo && introClose) {
  const dismissIntro = () => {
    introOverlay.hidden = true;
    document.body.classList.remove("has-intro-open");
    introVideo.pause();
  };

  const showIntro = () => {
    introOverlay.hidden = false;
    document.body.classList.add("has-intro-open");

    const playPromise = introVideo.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(() => {
        introVideo.controls = true;
      });
    }
  };

  introClose.addEventListener("click", dismissIntro);
  introVideo.addEventListener("ended", dismissIntro);
  introOverlay.addEventListener("click", (event) => {
    if (event.target === introOverlay) {
      dismissIntro();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !introOverlay.hidden) {
      dismissIntro();
    }
  });

  showIntro();
}
