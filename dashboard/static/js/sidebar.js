/**
 * Sidebar Navigation Management
 * Handles active state, toggle, and mobile menu functionality
 */

document.addEventListener('DOMContentLoaded', () => {
    // Detect current page and set active state
    const currentPath = window.location.pathname;
    const navItems = document.querySelectorAll('.nav-item[href]');

    navItems.forEach(item => {
        const href = item.getAttribute('href');

        // Exact match for root path
        if (currentPath === '/' && href === '/') {
            item.classList.add('active');
        }
        // Match for other paths
        else if (href !== '/' && currentPath.startsWith(href)) {
            item.classList.add('active');
        }
    });

    // Sidebar toggle functionality
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');

            // Save state to localStorage
            localStorage.setItem('sidebar-collapsed', sidebar.classList.contains('collapsed'));

            // Update toggle icon
            const icon = sidebarToggle.querySelector('span');
            if (icon) {
                icon.textContent = sidebar.classList.contains('collapsed') ? '☰' : '✕';
            }
        });

        // Restore sidebar state from localStorage
        const isCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
        if (isCollapsed) {
            sidebar.classList.add('collapsed');
            const icon = sidebarToggle.querySelector('span');
            if (icon) {
                icon.textContent = '☰';
            }
        }
    }

    // Mobile menu functionality
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    if (mobileMenuBtn && sidebar) {
        mobileMenuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('mobile-open');
        });
    }

    // Close mobile menu on overlay click
    const overlay = document.querySelector('.sidebar-overlay');
    if (overlay && sidebar) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('mobile-open');
        });
    }

    // Close mobile menu when clicking nav item
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            if (sidebar && sidebar.classList.contains('mobile-open')) {
                sidebar.classList.remove('mobile-open');
            }
        });
    });

    // Close mobile menu on ESC key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('mobile-open')) {
            sidebar.classList.remove('mobile-open');
        }
    });

    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            // Close mobile menu if window is resized to desktop
            if (window.innerWidth > 1024 && sidebar && sidebar.classList.contains('mobile-open')) {
                sidebar.classList.remove('mobile-open');
            }
        }, 250);
    });
});
