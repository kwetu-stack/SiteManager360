document.addEventListener("DOMContentLoaded", function () {

  const toggle = document.getElementById("menu-toggle");
  const nav = document.getElementById("nav-menu");

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      nav.classList.toggle("active");
    });

    // CLOSE MENU WHEN LINK CLICKED
    nav.querySelectorAll("a").forEach(link => {
      link.addEventListener("click", function () {
        nav.classList.remove("active");
      });
    });
  }

});
