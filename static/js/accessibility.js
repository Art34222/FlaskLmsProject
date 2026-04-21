document.addEventListener('DOMContentLoaded', () => {
    const KEY = 'eduonline_a11y';
    const body = document.body;
    const buttons = document.querySelectorAll('.a11y-toggle');

    if (localStorage.getItem(KEY) === '1') {
        body.classList.add('a11y');
    }

    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            body.classList.toggle('a11y');
            const isOn = body.classList.contains('a11y');
            localStorage.setItem(KEY, isOn ? '1' : '0');
        });
    });
});