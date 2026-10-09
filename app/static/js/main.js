/**
 * MediVault – Personal Health Record Manager
 * Main Client Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Theme Preference
    initTheme();

    // 2. Setup Auto-dismissing Alerts after 6 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 7000);
    });

    // 3. Password Match Validation in Forms
    const regForm = document.querySelector('form[data-validate-password="true"]');
    if (regForm) {
        regForm.addEventListener('submit', (e) => {
            const pwd = regForm.querySelector('input[name="password"]') || regForm.querySelector('input[name="new_password"]');
            const confirm = regForm.querySelector('input[name="confirm_password"]') || regForm.querySelector('input[name="confirm_new_password"]');
            if (pwd && confirm && pwd.value !== confirm.value) {
                e.preventDefault();
                alert("Passwords do not match. Please verify and try again.");
                confirm.focus();
            }
        });
    }

    // 4. Generic Delete Confirmation Modal / Prompt Handler
    const deleteBtns = document.querySelectorAll('.btn-confirm-delete');
    deleteBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const itemName = btn.getAttribute('data-item-name') || 'this item';
            const confirmed = confirm(`Are you sure you want to permanently delete ${itemName}? This action cannot be undone.`);
            if (!confirmed) {
                e.preventDefault();
            }
        });
    });
});

/**
 * Handle Theme switching (Light / Dark Mode)
 */
function initTheme() {
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const savedTheme = localStorage.getItem('medivault_theme') || 
                       document.documentElement.getAttribute('data-theme') || 'light';

    applyTheme(savedTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const nextTheme = currentTheme === 'light' ? 'dark' : 'light';
            applyTheme(nextTheme);
            localStorage.setItem('medivault_theme', nextTheme);

            // If user is authenticated, sync with backend
            fetch('/auth/toggle-theme', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).catch(() => {});
        });
    }
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const themeIcon = document.getElementById('theme-toggle-icon');
    const themeText = document.getElementById('theme-toggle-text');
    if (themeIcon) {
        if (theme === 'dark') {
            themeIcon.className = 'bi bi-sun-fill text-warning';
            if (themeText) themeText.textContent = 'Light Mode';
        } else {
            themeIcon.className = 'bi bi-moon-stars-fill text-primary';
            if (themeText) themeText.textContent = 'Dark Mode';
        }
    }
}
