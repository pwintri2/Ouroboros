const revealElements = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    {
      threshold: 0.18,
      rootMargin: "0px 0px -8% 0px",
    },
  );

  revealElements.forEach((element) => observer.observe(element));
} else {
  revealElements.forEach((element) => element.classList.add("is-visible"));
}

const header = document.querySelector(".site-header");

const syncHeaderState = () => {
  if (!header) {
    return;
  }

  header.classList.toggle("is-scrolled", window.scrollY > 16);
};

syncHeaderState();
window.addEventListener("scroll", syncHeaderState, { passive: true });

document.querySelectorAll("[data-year]").forEach((element) => {
  element.textContent = new Date().getFullYear();
});

const zoomableImages = document.querySelectorAll(
  "main img:not(.brand-logo), img[data-zoomable]",
);

if (zoomableImages.length > 0) {
  const labels = {
    de: {
      close: "Vergroesserte Abbildung schliessen",
      open: "Abbildung vergroessern",
      dialog: "Vergroesserte Abbildung",
    },
    es: {
      close: "Cerrar imagen ampliada",
      open: "Ampliar imagen",
      dialog: "Imagen ampliada",
    },
    fr: {
      close: "Fermer l'image agrandie",
      open: "Agrandir l'image",
      dialog: "Image agrandie",
    },
    nl: {
      close: "Vergrote afbeelding sluiten",
      open: "Afbeelding vergroten",
      dialog: "Vergrote afbeelding",
    },
  };
  const language = document.documentElement.lang || "en";
  const copy = labels[language] || {
    close: "Close enlarged image",
    open: "Enlarge image",
    dialog: "Enlarged image",
  };
  let activeImage = null;

  const lightbox = document.createElement("div");
  lightbox.className = "image-lightbox";
  lightbox.setAttribute("role", "dialog");
  lightbox.setAttribute("aria-modal", "true");
  lightbox.setAttribute("aria-label", copy.dialog);

  const closeButton = document.createElement("button");
  closeButton.className = "image-lightbox-close";
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", copy.close);

  const lightboxImage = document.createElement("img");
  lightboxImage.alt = "";

  lightbox.append(closeButton, lightboxImage);
  document.body.append(lightbox);

  const closeLightbox = () => {
    lightbox.classList.remove("is-open");
    document.body.classList.remove("has-lightbox");
    lightboxImage.removeAttribute("src");

    if (activeImage) {
      activeImage.focus();
      activeImage = null;
    }
  };

  const openLightbox = (image) => {
    activeImage = image;
    lightboxImage.src = image.currentSrc || image.src;
    lightboxImage.alt = image.alt || "";
    lightbox.classList.add("is-open");
    document.body.classList.add("has-lightbox");
    closeButton.focus();
  };

  zoomableImages.forEach((image) => {
    image.tabIndex = 0;
    image.setAttribute("role", "button");
    image.setAttribute("aria-label", `${image.alt}. ${copy.open}`);

    image.addEventListener("click", () => openLightbox(image));
    image.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openLightbox(image);
      }
    });
  });

  closeButton.addEventListener("click", closeLightbox);
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox || event.target === lightboxImage) {
      closeLightbox();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && lightbox.classList.contains("is-open")) {
      closeLightbox();
    }
  });
}
