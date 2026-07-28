(function () {
  var revealItems = Array.prototype.slice.call(document.querySelectorAll('main > section, .problem-card, .flow-card, .value__grid article'));
  revealItems.forEach(function (item) { item.classList.add('reveal'); });
  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) { entry.target.classList.toggle('is-visible', entry.isIntersecting); });
    }, { threshold: 0.12, rootMargin: '0px 0px -7% 0px' });
    revealItems.forEach(function (item) { observer.observe(item); });
  } else { revealItems.forEach(function (item) { item.classList.add('is-visible'); }); }
})();
