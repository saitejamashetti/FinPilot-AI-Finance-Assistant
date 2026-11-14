const navToggle = document.getElementById('sidebarToggle');
const primaryNavigation = document.getElementById('primaryNavigation');

if (navToggle && primaryNavigation) {
    navToggle.addEventListener('click', () => {
        const isOpen = primaryNavigation.classList.toggle('is-open');
        navToggle.setAttribute('aria-expanded', String(isOpen));
    });
}

const printButton = document.getElementById('print-report');
if (printButton) {
    printButton.addEventListener('click', () => window.print());
}
