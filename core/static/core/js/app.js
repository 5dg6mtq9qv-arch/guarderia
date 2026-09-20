document.querySelectorAll('[data-open]').forEach(button => {
  button.addEventListener('click', () => document.getElementById(button.dataset.open)?.showModal());
});
document.querySelectorAll('[data-close]').forEach(button => {
  button.addEventListener('click', () => button.closest('dialog')?.close());
});
document.querySelectorAll('dialog.has-errors').forEach(dialog => dialog.showModal());
document.querySelectorAll('.message button').forEach(button => button.addEventListener('click', () => button.parentElement.remove()));
document.querySelector('[data-menu]')?.addEventListener('click', () => document.getElementById('sidebar')?.classList.toggle('open'));
document.querySelectorAll('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const field = document.querySelector(button.dataset.copy);
    if (!field) return;
    await navigator.clipboard.writeText(field.value);
    const original = button.textContent;
    button.textContent = '¡Copiado!';
    setTimeout(() => button.textContent = original, 1600);
  });
});

document.querySelectorAll('[data-payment-tab]').forEach(button => {
  button.addEventListener('click', () => {
    const tab = button.dataset.paymentTab;
    document.querySelectorAll('[data-payment-tab]').forEach(item => item.classList.toggle('active', item === button));
    document.querySelectorAll('[data-payment-panel]').forEach(panel => panel.classList.toggle('active', panel.dataset.paymentPanel === tab));
  });
});

document.querySelectorAll('[data-mensualidad]').forEach(button => {
  button.addEventListener('click', () => {
    const select = document.getElementById('id_pago-mensualidad');
    if (select) {
      select.value = button.dataset.mensualidad;
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
});

document.querySelectorAll('.pay-more [data-open]').forEach(button => {
  button.addEventListener('click', () => button.closest('details')?.removeAttribute('open'));
});
