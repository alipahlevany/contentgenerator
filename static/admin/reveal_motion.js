(() => {
  'use strict';
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reveal = element => {
    if (element.hidden || reducedMotion.matches || typeof element.animate !== 'function') return;
    element.animate(
      [{opacity:0,transform:'translateY(10px) scale(.99)'},{opacity:1,transform:'translateY(0) scale(1)}],
      {duration:300,easing:'cubic-bezier(.16,1,.3,1)'}
    );
  };
  const observer = new MutationObserver(records => {
    records.forEach(record => {
      if (record.attributeName === 'hidden') reveal(record.target);
    });
  });
  observer.observe(document.documentElement,{subtree:true,attributes:true,attributeFilter:['hidden']});
})();
