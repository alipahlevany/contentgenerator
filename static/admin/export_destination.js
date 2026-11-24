(() => {
  'use strict';
  const select = document.getElementById('id_export_client');
  const input = document.getElementById('id_export_destination');
  const section = document.getElementById('new-export-destination');
  if (!select || !input || !section) return;
  if (!select.value && input.value) select.value = '__new__';
  const sync = () => {
    const creating = select.value === '__new__';
    section.hidden = !creating;
    input.disabled = !creating;
    input.required = creating;
  };
  select.addEventListener('change', () => { sync(); if (!section.hidden) input.focus(); });
  sync();
})();
