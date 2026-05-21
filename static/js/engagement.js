function compartilharNativo(titulo) {
    const url = window.location.href;
    if (navigator.share) {
        navigator.share({ title: titulo, url }).catch(() => {});
    } else {
        navigator.clipboard?.writeText(url).then(() => {
            alert('Link copiado!');
        }).catch(() => {
            prompt('Copie o link:', url);
        });
    }
}

document.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', () => {
        const url = btn.dataset.copy;
        navigator.clipboard?.writeText(url).then(() => {
            const span = btn.querySelector('span');
            const old = span?.textContent;
            if (span) span.textContent = 'Copiado!';
            setTimeout(() => { if (span && old) span.textContent = old; }, 2000);
        }).catch(() => prompt('Copie:', url));
    });
});

function setupCurtirAjax(form) {
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        try {
            const res = await fetch(form.action, {
                method: 'POST',
                body: fd,
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            const data = await res.json();
            document.querySelectorAll('[data-curtidas-count]').forEach((el) => {
                el.textContent = data.total;
            });
            document.querySelectorAll('[data-curtir-btn]').forEach((btn) => {
                btn.classList.toggle('active', data.curtiu);
                const icon = btn.querySelector('i');
                if (icon) {
                    icon.classList.toggle('far', !data.curtiu);
                    icon.classList.toggle('fas', data.curtiu);
                }
            });
        } catch {
            form.submit();
        }
    });
}

setupCurtirAjax(document.getElementById('formCurtir'));
setupCurtirAjax(document.getElementById('formCurtirMobile'));
