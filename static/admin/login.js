(() => {
    const password = document.querySelector('#id_password');
    const toggle = document.querySelector('.password-toggle');

    if (!password || !toggle) return;

    toggle.addEventListener('click', () => {
        const reveal = password.type === 'password';
        password.type = reveal ? 'text' : 'password';
        toggle.setAttribute('aria-pressed', String(reveal));
        toggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
        password.focus();
    });
})();
