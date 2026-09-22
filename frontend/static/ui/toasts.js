(function (window) {
    const toasts = (function () {
        let currentToast = null;

        function buildIcon(type) {
            if (type === 'success') {
                return '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>';
            } else if (type === 'loading') {
                return '<svg class="size-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
            }
            return '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';
        }

        function showToast(type, message, duration = 5000) {
            if (currentToast) {
                hideToast(currentToast);
            }

            const container = document.getElementById('toast-container');
            if (!container) return null;
            const toastId = 'toast-' + Date.now();

            let bgClass, textClass, borderClass, icon;
            if (type === 'success') {
                bgClass = 'bg-green-50 border-green-200';
                textClass = 'text-green-800';
                borderClass = 'border';
                icon = buildIcon('success');
            } else if (type === 'loading') {
                bgClass = 'bg-blue-50 border-blue-200';
                textClass = 'text-blue-800';
                borderClass = 'border';
                icon = buildIcon('loading');
            } else if (type === 'warning') {
                bgClass = 'bg-yellow-50 border-yellow-200';
                textClass = 'text-yellow-800';
                borderClass = 'border';
                icon = buildIcon('warning');
            } else {
                bgClass = 'bg-red-50 border-red-200';
                textClass = 'text-red-800';
                borderClass = 'border';
                icon = buildIcon('error');
            }

            const toast = document.createElement('div');
            toast.id = toastId;
            toast.className = `${bgClass} ${borderClass} ${textClass} rounded-lg shadow-lg p-4 pointer-events-auto transition-all duration-300 transform translate-x-0 opacity-100`;
            toast.innerHTML = `
                <div class="flex items-center gap-3">
                    <div class="flex-shrink-0">
                        ${icon}
                    </div>
                    <div class="flex-grow">
                        <p class="text-sm font-medium">${message}</p>
                    </div>
                    ${type !== 'loading' ? `
                    <button type="button" class="toast-close flex-shrink-0 inline-flex items-center justify-center size-5 rounded-lg text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-400">
                        <span class="sr-only">Close</span>
                        <svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                    ` : ''}
                </div>
            `;

            container.appendChild(toast);
            currentToast = toastId;

            // Attach close handler for non-loading toasts
            if (type !== 'loading') {
                const btn = toast.querySelector('.toast-close');
                if (btn) btn.addEventListener('click', () => hideToast(toastId));
            }

            if (type !== 'loading' && duration > 0) {
                setTimeout(() => hideToast(toastId), duration);
            }

            return toastId;
        }

        function hideToast(toastId) {
            const toast = document.getElementById(toastId);
            if (toast) {
                toast.classList.add('translate-x-full', 'opacity-0');
                setTimeout(() => {
                    if (toast.parentNode) toast.parentNode.removeChild(toast);
                    if (currentToast === toastId) currentToast = null;
                }, 300);
            }
        }

        return { showToast, hideToast };
    })();

    window.App = window.App || {};
    window.App.toasts = toasts;
})(window);

// Toast wrappers that delegate to `window.App.toasts` (implemented in ui/toasts.js)
function showToast(type, message, duration = 5000) {
    if (window.App && window.App.toasts && typeof window.App.toasts.showToast === 'function') {
        return window.App.toasts.showToast(type, message, duration);
    }
    // Fallback: simple alert if toasts not initialized
    try {
        console[type === 'error' ? 'error' : 'log'](message);
    } catch (e) { }
    return null;
}

function hideToast(toastId) {
    if (window.App && window.App.toasts && typeof window.App.toasts.hideToast === 'function') {
        return window.App.toasts.hideToast(toastId);
    }
    const toast = document.getElementById(toastId);
    if (toast) toast.remove();
}