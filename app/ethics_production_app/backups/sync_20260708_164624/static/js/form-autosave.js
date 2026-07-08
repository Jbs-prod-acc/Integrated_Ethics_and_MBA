(function () {
  'use strict';

  function setStatus(statusEl, text, color) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.style.color = color;
  }

  function collectFormData(form) {
    const formData = new FormData(form);

    const checkboxes = form.querySelectorAll('input[type="checkbox"][name]');
    checkboxes.forEach((checkbox) => {
      if (checkbox.checked) {
        formData.set(checkbox.name, checkbox.value || 'true');
      } else {
        formData.set(checkbox.name, 'false');
      }
    });

    return formData;
  }

  function initFormAutosave(options) {
    const config = options || {};
    const form = document.querySelector(config.formSelector || 'form');
    if (!form || !config.endpoint) {
      return;
    }

    const statusEl = document.getElementById(config.statusElementId || 'autosave-status');
    const delay = Number(config.delay || 1200);
    let autosaveTimeout = null;
    let inFlight = false;

    function autosave() {
      if (inFlight) return;

      inFlight = true;
      setStatus(statusEl, 'Saving...', '#555');

      const payload = collectFormData(form);
      const csrfToken = payload.get('csrf_token');

      fetch(config.endpoint, {
        method: 'POST',
        body: payload,
        credentials: 'same-origin',
        headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {}
      })
        .then((response) => response.json().catch(() => ({ success: false, error: 'Invalid JSON response' })))
        .then((data) => {
          if (data && data.success) {
            setStatus(statusEl, 'Saved', '#198754');
          } else {
            setStatus(statusEl, 'Autosave failed', '#dc3545');
          }
        })
        .catch(() => {
          setStatus(statusEl, 'Autosave failed', '#dc3545');
        })
        .finally(() => {
          inFlight = false;
        });
    }

    function scheduleAutosave() {
      clearTimeout(autosaveTimeout);
      autosaveTimeout = setTimeout(autosave, delay);
    }

    const fields = form.querySelectorAll('input, textarea, select');
    fields.forEach((field) => {
      if (!field.name) return;
      if (field.type === 'submit' || field.type === 'button' || field.type === 'file') return;

      const eventName = (field.tagName === 'SELECT' || field.type === 'checkbox' || field.type === 'radio') ? 'change' : 'input';
      field.addEventListener(eventName, scheduleAutosave);

      if (eventName !== 'change') {
        field.addEventListener('change', scheduleAutosave);
      }
    });
  }

  window.initFormAutosave = initFormAutosave;
})();
