/* Шапка: выпадашки («Возможности», «Форматы») и бургер на узком экране.
   Без скрипта ссылки всё равно доступны — на десктопе панели открываются наведением. */
(function () {
  var menu = document.getElementById("menu");
  var burger = document.getElementById("burger");
  var drops = Array.prototype.slice.call(document.querySelectorAll(".drop"));

  function setDrop(drop, open) {
    drop.classList.toggle("open", open);
    drop.querySelector(".drop-btn").setAttribute("aria-expanded", String(open));
  }
  function closeDrops(except) {
    drops.forEach(function (d) { if (d !== except) setDrop(d, false); });
  }
  function setMenu(open) {
    if (!menu || !burger) return;
    menu.classList.toggle("open", open);
    burger.setAttribute("aria-expanded", String(open));
    burger.setAttribute("aria-label", open ? "Закрыть меню" : "Открыть меню");
  }

  /* Открыта может быть только одна выпадашка */
  drops.forEach(function (drop) {
    drop.querySelector(".drop-btn").addEventListener("click", function (e) {
      e.stopPropagation();
      closeDrops(drop);
      setDrop(drop, !drop.classList.contains("open"));
    });
  });
  if (burger) burger.addEventListener("click", function (e) {
    e.stopPropagation();
    setMenu(!menu.classList.contains("open"));
  });

  /* Клик мимо, Esc или переход по ссылке закрывают всё открытое */
  document.addEventListener("click", function (e) {
    drops.forEach(function (d) { if (!d.contains(e.target)) setDrop(d, false); });
    if (menu && menu.classList.contains("open") && !menu.contains(e.target)) setMenu(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    drops.forEach(function (d) {
      if (d.classList.contains("open")) { setDrop(d, false); d.querySelector(".drop-btn").focus(); }
    });
    if (menu && menu.classList.contains("open")) { setMenu(false); burger.focus(); }
  });
  if (menu) menu.addEventListener("click", function (e) {
    if (e.target.closest("a")) { closeDrops(null); setMenu(false); }
  });
})();
