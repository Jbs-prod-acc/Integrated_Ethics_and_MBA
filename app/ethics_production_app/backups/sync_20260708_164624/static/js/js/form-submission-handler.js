/**
 * Form Submission Handler - Prevents Double Submissions
 * Adds loading indicators and disables buttons during form submission
 */

(function() {
    'use strict';

    // Create loading overlay HTML
    function createLoadingOverlay() {
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.id = 'globalLoadingOverlay';
        overlay.innerHTML = `
            <div class="loading-spinner-container">
                <div class="loading-spinner"></div>
                <div class="loading-text">Loading...</div>
                <div class="loading-subtext" style="font-size: 13px; color: #666; margin-top: 10px;">
                    Please wait, do not refresh the page
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        return overlay;
    }

    // Show loading overlay
    function showLoading() {
        let overlay = document.getElementById('globalLoadingOverlay');
        if (!overlay) {
            overlay = createLoadingOverlay();
        }
        overlay.classList.add('active');
    }

    // Hide loading overlay
    function hideLoading() {
        const overlay = document.getElementById('globalLoadingOverlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
    }

    // Disable form and all submit buttons
    function disableForm(form) {
        form.classList.add('submitting');
        
        // Disable all submit buttons in the form
        const submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
        submitButtons.forEach(button => {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML || button.value;
            
            // Add loading spinner to button
            if (button.tagName === 'BUTTON') {
                button.innerHTML = `
                    <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                    Submitting...
                `;
            } else {
                button.value = 'Submitting...';
            }
        });

        // Disable all other buttons
        const allButtons = form.querySelectorAll('button:not([type="submit"])');
        allButtons.forEach(button => {
            button.disabled = true;
        });

        // Make inputs readonly instead of disabled (disabled fields don't submit their values!)
        // Exclude hidden fields and checkboxes/radios
        const inputs = form.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]), textarea');
        inputs.forEach(input => {
            input.readOnly = true;
            input.style.pointerEvents = 'none';
            input.style.opacity = '0.6';
        });

        // Prevent interaction without disabling (disabled inputs don't submit values)
        const checkboxRadio = form.querySelectorAll('input[type="checkbox"], input[type="radio"]');
        checkboxRadio.forEach(input => {
            input.style.pointerEvents = 'none';
            input.style.opacity = '0.6';
            input.dataset.submittingReadonly = 'true';
        });

        const selects = form.querySelectorAll('select');
        selects.forEach(select => {
            select.style.pointerEvents = 'none';
            select.style.opacity = '0.6';
            select.dataset.submittingReadonly = 'true';
        });
    }

    // Re-enable form (in case of error or timeout)
    function enableForm(form) {
        form.classList.remove('submitting');
        
        // Re-enable all submit buttons
        const submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
        submitButtons.forEach(button => {
            button.disabled = false;
            if (button.dataset.originalText) {
                if (button.tagName === 'BUTTON') {
                    button.innerHTML = button.dataset.originalText;
                } else {
                    button.value = button.dataset.originalText;
                }
            }
        });

        // Re-enable all other buttons
        const allButtons = form.querySelectorAll('button:not([type="submit"])');
        allButtons.forEach(button => {
            button.disabled = false;
        });

        // Re-enable text inputs by removing readonly
        const inputs = form.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="submit"]), textarea');
        inputs.forEach(input => {
            input.readOnly = false;
            input.style.pointerEvents = '';
            input.style.opacity = '';
        });

        // Re-enable checkboxes and radios
        const checkboxRadio = form.querySelectorAll('input[type="checkbox"], input[type="radio"]');
        checkboxRadio.forEach(input => {
            if (input.dataset.submittingReadonly) {
                input.style.pointerEvents = '';
                input.style.opacity = '';
                delete input.dataset.submittingReadonly;
            }
        });

        // Re-enable select elements
        const selects = form.querySelectorAll('select');
        selects.forEach(select => {
            if (select.dataset.submittingReadonly) {
                select.style.pointerEvents = '';
                select.style.opacity = '';
                delete select.dataset.submittingReadonly;
            }
        });
    }

        // Highlight the current sidebar item across pages
        function setSidebarActiveLink() {
            const currentPath = window.location.pathname.replace(/\/+$/, '');
            document.querySelectorAll('.sidebar-nav a, .sidebar-link').forEach(link => {
                const href = link.getAttribute('href');
                if (!href) return;
                try {
                    const linkUrl = new URL(href, window.location.origin);
                    const linkPath = linkUrl.pathname.replace(/\/+$/, '');
                    if (linkPath === currentPath) {
                        link.classList.add('active');
                    }
                } catch (error) {
                    // Ignore invalid URLs
                }
            });
        }

    // Track submitted forms to prevent re-submission
    const submittedForms = new WeakSet();

    // Handle form submission
    function handleFormSubmit(event) {
        const form = event.target;

        // Check if form is already being submitted
        if (submittedForms.has(form)) {
            event.preventDefault();
            console.log('Form already submitted, preventing duplicate submission');
            return false;
        }

        // Mark form as submitted
        submittedForms.add(form);

        // Disable form
        disableForm(form);

        // Show loading overlay unless form opts out
        if (!form.classList.contains('no-loading-indicator')) {
            showLoading();
        }

        // Optional: Set a timeout to re-enable form after a long wait (safety measure)
        // This prevents forms from being permanently locked if there's a JavaScript error
        const timeout = setTimeout(() => {
            // Only re-enable if the page hasn't navigated away
            if (document.body.contains(form)) {
                console.warn('Form submission taking longer than expected');
                // Keep form disabled but hide overlay for better UX
                // hideLoading();
            }
        }, 60000); // 60 seconds

        // Store timeout ID to clear it if needed
        form.dataset.loadingTimeout = timeout;

        // Allow the form to submit normally
        return true;
    }

    // Initialize when DOM is ready
    function init() {
        // Add submit event listeners to all forms
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.addEventListener('submit', handleFormSubmit);
        });

        // Set the active sidebar item for navigation clarity
        setSidebarActiveLink();

        // Handle dynamically added forms (using event delegation)
        document.addEventListener('submit', function(event) {
            if (event.target.tagName === 'FORM') {
                // Check if this form already has a listener
                if (!event.target.hasAttribute('data-submit-handler')) {
                    event.target.setAttribute('data-submit-handler', 'true');
                    // The event will bubble up and be handled by the delegated listener
                }
            }
        }, true);

        console.log('Form submission handler initialized');
    }

    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose utility functions globally if needed
    window.FormSubmissionHandler = {
        showLoading: showLoading,
        hideLoading: hideLoading,
        disableForm: disableForm,
        enableForm: enableForm
    };

})();
