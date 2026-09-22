(function (window) {
    const nav = {
        setActiveMenuItem(page) {
            const desktopLinks = document.querySelectorAll('#desktopSidebar [data-page]');
            desktopLinks.forEach(link => { link.classList.remove('bg-gray-200'); link.classList.add('bg-gray-100'); });
            const mobileLinks = document.querySelectorAll('#mobileSidebar [data-page]');
            mobileLinks.forEach(link => { link.classList.remove('bg-gray-200'); link.classList.add('bg-white'); });
            const activeDesktopLinks = document.querySelectorAll(`#desktopSidebar [data-page="${page}"]`);
            activeDesktopLinks.forEach(link => { link.classList.add('bg-gray-200'); link.classList.remove('bg-gray-100'); });
            const activeMobileLinks = document.querySelectorAll(`#mobileSidebar [data-page="${page}"]`);
            activeMobileLinks.forEach(link => { link.classList.add('bg-gray-200'); link.classList.remove('bg-white'); });
        }
        ,
        handlePageNavigation(page) {
            if (typeof handlePageNavigation === 'function') return handlePageNavigation(page);
            console.warn('handlePageNavigation() not available');
        },
        navigateToHome() {
            if (typeof navigateToHome === 'function') return navigateToHome();
            window.location.href = '/';
        }
    };

    window.App = window.App || {};
    window.App.nav = nav;
})(window);

// URL ROUTING
// Handle browser back/forward navigation
window.addEventListener('popstate', function(event) {
    if (event.state && event.state.page) {
        // Use the stored page state
        handlePageNavigation(event.state.page);
    } else {
        // Determine page from URL
        const page = getPageFromURL(window.location.pathname);
        handlePageNavigation(page);
    }
});

function navigateToHome() {
    // Navigate to home page (this will trigger a redirect to / which checks system status)
    window.location.href = '/';
}

// Sidebar navigation active state management
function setActiveMenuItem(page) {
    // Remove active state from all links in desktop sidebar
    const desktopLinks = document.querySelectorAll('#desktopSidebar [data-page]');
    desktopLinks.forEach(link => {
        link.classList.remove('bg-gray-200');
        link.classList.add('bg-gray-100');
    });
    
    // Remove active state from all links in mobile sidebar
    const mobileLinks = document.querySelectorAll('#mobileSidebar [data-page]');
    mobileLinks.forEach(link => {
        link.classList.remove('bg-gray-200');
        link.classList.add('bg-white');
    });
    
    // Add active state to clicked desktop sidebar links
    const activeDesktopLinks = document.querySelectorAll(`#desktopSidebar [data-page="${page}"]`);
    activeDesktopLinks.forEach(link => {
        link.classList.add('bg-gray-200');
        link.classList.remove('bg-gray-100');
    });
    
    // Add active state to clicked mobile sidebar links
    const activeMobileLinks = document.querySelectorAll(`#mobileSidebar [data-page="${page}"]`);
    activeMobileLinks.forEach(link => {
        link.classList.add('bg-gray-200');
        link.classList.remove('bg-white');
    });
}

// Navigation functionality
function showContent(contentId) {
    // Hide all content sections
    const contentSections = ['welcome-content', 'this-is-content', 'rediscover-content', 'genre-mix-content', 'manage-playlists-content', 'system-check-content', 'terms-content'];
    contentSections.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = 'none';
        }
    });

    // Show the selected content
    const targetContent = document.getElementById(contentId);
    if (targetContent) {
        targetContent.style.display = 'block';
    }
}

// Add click handlers to all navigation links
document.addEventListener('click', function(event) {
    const link = event.target.closest('[data-page]');
    if (link) {
        event.preventDefault();
        const page = link.getAttribute('data-page');
        
        // Use the shared navigation handler
        handlePageNavigation(page);
        
        // Update URL based on page (only for click navigation, not popstate)
        updateURL(page);
        
        // Close mobile sidebar if clicked
        if (window.innerWidth < 768) {
            mobileSidebar.classList.add('-translate-x-full');
            sidebarOverlay.classList.add('hidden');
        }
    }
});

// Mobile menu toggle functionality
const mobileMenuBtn = document.getElementById('hs-navbar-alignment-collapse');
const mobileSidebar = document.getElementById('mobileSidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const closeMobileSidebarBtn = document.getElementById('closeMobileSidebar');

mobileMenuBtn.addEventListener('click', function() {
    mobileSidebar.classList.toggle('-translate-x-full');
    sidebarOverlay.classList.toggle('hidden');
});

// Close sidebar when clicking on close button
closeMobileSidebarBtn.addEventListener('click', function() {
    mobileSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
});

// Close sidebar when clicking on overlay
sidebarOverlay.addEventListener('click', function() {
    mobileSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function(event) {
    if (window.innerWidth < 768 && 
        !mobileSidebar.contains(event.target) && 
        !mobileMenuBtn.contains(event.target) &&
        !mobileSidebar.classList.contains('-translate-x-full')) {
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
});

// Handle page navigation (used by both click and popstate)
function handlePageNavigation(page) {
    // Map page to content
    let contentId;
    if (page === 'home') {
        contentId = 'welcome-content';
    } else if (page === 'this-is-artist') {
        contentId = 'this-is-content';
        // Load artists when navigating to This Is page (only if libraries selected)
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadArtists(), 100);
        }
    } else if (page === 're-discover') {
        contentId = 'rediscover-content';
    } else if (page === 'genre-mix') {
        contentId = 'genre-mix-content';
        // Load genres when navigating to Genre Mix page (only if libraries selected)
        if (selectedLibraryIds.length > 0) {
            setTimeout(() => loadGenres(), 100);
        }
    } else if (page === 'playlists') {
        contentId = 'manage-playlists-content';
        // Load playlists when navigating to manage page
        setTimeout(() => loadPlaylists(), 100);
    } else if (page === 'system-check') {
        contentId = 'system-check-content';
        // Auto-run system checks when navigating to system check page
        setTimeout(() => runSystemChecks(), 100);
    } else if (page === 'terms') {
        contentId = 'terms-content';
    }

    setActiveMenuItem(page);
    showContent(contentId);
}