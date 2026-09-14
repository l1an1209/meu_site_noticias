(function () {
    const shell = document.getElementById('appShell');
    document.getElementById('appNavToggle')?.addEventListener('click', () => {
        shell?.classList.toggle('nav-open');
    });
    document.getElementById('appNavBackdrop')?.addEventListener('click', () => {
        shell?.classList.remove('nav-open');
    });
    document.querySelectorAll('.js-loading-form').forEach((form) => {
        form.addEventListener('submit', () => {
            const btn = form.querySelector('[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.dataset.label = btn.textContent;
                btn.textContent = 'Salvando…';
            }
        });
    });
    document.querySelectorAll('input[type="file"][accept*="image"]').forEach((input) => {
        input.addEventListener('change', () => {
            const file = input.files && input.files[0];
            if (!file) return;
            const box = input.closest('.d-flex')?.querySelector('.preview-box');
            if (!box) return;
            const url = URL.createObjectURL(file);
            box.innerHTML = `<img src="${url}" alt="">`;
        });
    });
})();
