(() => {
    'use strict';
    // Keep Django's filter URLs and selected state; only change their presentation.
    document.querySelectorAll('.cg-catalog-filters details').forEach(details => {
        const list = details.querySelector('ul');
        if (!list) return;
        const title = details.dataset.filterTitle || 'Filter';
        const isStatus = title === 'is active';
        const group = document.createElement('div');
        group.className = 'cg-catalog-filter-group';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', isStatus ? 'Status' : title);
        const label = document.createElement('span');
        label.className = 'cg-catalog-filter-label';
        label.textContent = isStatus ? 'Status' : title;
        list.querySelectorAll('a').forEach(link => {
            if (isStatus) {
                const labels = {Yes:'Active', No:'Inactive'};
                link.textContent = labels[link.textContent.trim()] || link.textContent.trim();
            }
            if (link.parentElement.classList.contains('selected')) link.setAttribute('aria-current', 'true');
        });
        group.append(label, list);
        details.replaceWith(group);
    });
})();
