(function () {
  'use strict';

  const DECLARATION_FIELDS = new Set([
    'declaration_name',
    'applicant_signature',
    'full_name',
    'declaration_date',
    'submission_date'
  ]);

  function normalizeEthicsAutosaveUrl(url) {
    if (
      typeof url === 'string'
      && url.startsWith('/')
      && !url.startsWith('/ethics/')
      && url.includes('autosave')
      && (window.location.pathname === '/ethics' || window.location.pathname.startsWith('/ethics/'))
    ) {
      return `/ethics${url}`;
    }
    return url;
  }

  // Several legacy form scripts still use root-relative autosave paths.
  // Normalize only autosave requests when this app is mounted at /ethics.
  if (!window.__ethicsAutosaveFetchNormalized) {
    const originalFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      if (typeof input === 'string') {
        input = normalizeEthicsAutosaveUrl(input);
      } else if (input instanceof Request) {
        const normalizedUrl = normalizeEthicsAutosaveUrl(input.url);
        if (normalizedUrl !== input.url) {
          input = new Request(normalizedUrl, input);
        }
      }
      return originalFetch(input, init);
    };
    window.__ethicsAutosaveFetchNormalized = true;
  }

  function setStatus(statusEl, text, color) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.style.color = color;
  }

  function collectFormData(form) {
    const formData = new FormData(form);

    form.querySelectorAll('input[type="file"][name]').forEach((fileInput) => {
      // File uploads are handled by normal submission, not draft autosave.
      formData.delete(fileInput.name);
    });
    DECLARATION_FIELDS.forEach((fieldName) => formData.delete(fieldName));

    const checkboxes = form.querySelectorAll('input[type="checkbox"][name]');
    checkboxes.forEach((checkbox) => {
      const sameNameCheckboxes = Array.from(checkboxes)
        .filter((candidate) => candidate.name === checkbox.name);
      const isCheckboxGroup = checkbox.name.endsWith('[]') || sameNameCheckboxes.length > 1;

      // FormData already preserves every checked value in checkbox groups.
      // Only add an explicit false value for a single unchecked boolean.
      if (!isCheckboxGroup && !checkbox.checked) {
        formData.set(checkbox.name, 'false');
      }
    });

    return formData;
  }

  function bindLogoutAutosave(form, config, localDraft) {
    if (form.dataset.logoutAutosaveBound === '1') return;

    document.addEventListener('click', function (event) {
      const logoutLink = event.target.closest('a[href]');
      if (!logoutLink) return;

      let logoutUrl;
      try {
        logoutUrl = new URL(logoutLink.href, window.location.href);
      } catch (_error) {
        return;
      }
      if (!logoutUrl.pathname.endsWith('/logout')) return;

      event.preventDefault();
      if (form.dataset.logoutAutosaveRunning === '1') return;
      form.dataset.logoutAutosaveRunning = '1';
      localDraft.save();

      const saveRequest = fetch(normalizeEthicsAutosaveUrl(config.endpoint), {
        method: 'POST',
        body: collectFormData(form),
        credentials: 'same-origin'
      }).catch(() => null);
      const maximumWait = new Promise((resolve) => {
        window.setTimeout(resolve, 4000);
      });

      Promise.race([saveRequest, maximumWait]).finally(() => {
        window.location.assign(logoutUrl.href);
      });
    }, true);

    form.dataset.logoutAutosaveBound = '1';
  }

  function initLocalDraftBackup(form, config) {
    if (form.dataset.localDraftBackupBound === '1') {
      return {
        save: () => {},
        clear: () => {}
      };
    }

    const identityField = form.querySelector(
      '[name="student_number"], [name="form_id"], [name="forma_id"], [name="formb_id"], [name="formc_id"], [name="email"], [name="email_address"]'
    );
    const formIdentity = identityField && identityField.value ? identityField.value : 'active';
    const storageKey = config.storageKey || [
      'ethics-form-draft',
      window.location.pathname,
      normalizeEthicsAutosaveUrl(config.endpoint) || form.action || 'form',
      formIdentity
    ].join(':');

    function controls() {
      return Array.from(form.querySelectorAll('input[name], textarea[name], select[name]'))
        .filter((field) => (
          !['file', 'submit', 'button', 'hidden'].includes(field.type)
          && !DECLARATION_FIELDS.has(field.name)
        ));
    }

    function fieldKeys() {
      const occurrences = {};
      return controls().map((field) => {
        const base = `${field.name}:${field.type || field.tagName.toLowerCase()}`;
        const occurrence = occurrences[base] || 0;
        occurrences[base] = occurrence + 1;
        return { field, key: `${base}:${occurrence}` };
      });
    }

    function save() {
      try {
        const values = {};
        fieldKeys().forEach(({ field, key }) => {
          values[key] = (field.type === 'checkbox' || field.type === 'radio')
            ? { checked: field.checked }
            : { value: field.value };
        });
        window.sessionStorage.setItem(storageKey, JSON.stringify({
          savedAt: Date.now(),
          values
        }));
      } catch (_error) {
        // Server autosave remains available when browser storage is disabled.
      }
    }

    function clear() {
      try {
        window.sessionStorage.removeItem(storageKey);
      } catch (_error) {
        // Nothing else is required when browser storage is unavailable.
      }
    }

    try {
      const rawDraft = window.sessionStorage.getItem(storageKey);
      if (rawDraft) {
        const draft = JSON.parse(rawDraft);
        const isRecent = draft.savedAt && (Date.now() - draft.savedAt) < 24 * 60 * 60 * 1000;
        if (isRecent && draft.values) {
          const restoredFields = [];
          fieldKeys().forEach(({ field, key }) => {
            const savedField = draft.values[key];
            if (!savedField) return;
            if (field.type === 'checkbox' || field.type === 'radio') {
              field.checked = Boolean(savedField.checked);
            } else if (Object.prototype.hasOwnProperty.call(savedField, 'value')) {
              field.value = savedField.value;
            }
            restoredFields.push(field);
          });
          restoredFields.forEach((field) => {
            field.dispatchEvent(new Event('change', { bubbles: true }));
          });
        } else {
          clear();
        }
      }
    } catch (_error) {
      clear();
    }

    form.addEventListener('input', save);
    form.addEventListener('change', save);
    form.addEventListener('submit', clear);
    form.dataset.localDraftBackupBound = '1';
    return { save, clear };
  }

  function initAutosaveRefreshGuard(options) {
    const config = options || {};
    const form = document.querySelector(config.formSelector || 'form');
    if (!form || !config.endpoint || form.dataset.refreshAutosaveBound === '1') {
      return;
    }

    const localDraft = initLocalDraftBackup(form, config);
    bindLogoutAutosave(form, config, localDraft);
    let dirty = false;
    let submitting = false;
    const markDirty = (event) => {
      if (
        event.target
        && event.target.name
        && event.target.type !== 'file'
        && !DECLARATION_FIELDS.has(event.target.name)
      ) {
        dirty = true;
      }
    };
    const flush = () => {
      if (!dirty || submitting) return;
      localDraft.save();
      const payload = collectFormData(form);
      dirty = false;
      const endpoint = normalizeEthicsAutosaveUrl(config.endpoint);
      if (navigator.sendBeacon && navigator.sendBeacon(endpoint, payload)) {
        return;
      }
      fetch(endpoint, {
        method: 'POST',
        body: payload,
        credentials: 'same-origin',
        keepalive: true
      }).catch(() => {});
    };

    form.addEventListener('input', markDirty);
    form.addEventListener('change', markDirty);
    form.addEventListener('submit', () => {
      submitting = true;
    });
    window.addEventListener('pagehide', flush);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flush();
    });
    form.dataset.refreshAutosaveBound = '1';
  }

  function initFormAutosave(options) {
    const config = options || {};
    const form = document.querySelector(config.formSelector || 'form');
    if (!form || !config.endpoint) {
      return;
    }

    const statusEl = document.getElementById(config.statusElementId || 'autosave-status');
    const delay = Number(config.delay || 1200);
    const localDraft = initLocalDraftBackup(form, config);
    bindLogoutAutosave(form, config, localDraft);
    let autosaveTimeout = null;
    let inFlight = false;
    let dirty = false;
    let saveQueued = false;
    let submitting = false;

    function autosave() {
      clearTimeout(autosaveTimeout);
      if (!dirty || submitting) return;
      if (inFlight) {
        saveQueued = true;
        return;
      }

      inFlight = true;
      dirty = false;
      setStatus(statusEl, 'Saving...', '#555');

      const payload = collectFormData(form);

      fetch(normalizeEthicsAutosaveUrl(config.endpoint), {
        method: 'POST',
        body: payload,
        credentials: 'same-origin'
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
          if (dirty || saveQueued) {
            saveQueued = false;
            autosave();
          }
        });
    }

    function scheduleAutosave() {
      dirty = true;
      localDraft.save();
      clearTimeout(autosaveTimeout);
      autosaveTimeout = setTimeout(autosave, delay);
    }

    function flushAutosave() {
      if (!dirty || submitting) return;
      clearTimeout(autosaveTimeout);
      localDraft.save();
      const payload = collectFormData(form);
      dirty = false;

      const endpoint = normalizeEthicsAutosaveUrl(config.endpoint);
      if (navigator.sendBeacon && navigator.sendBeacon(endpoint, payload)) {
        return;
      }

      fetch(endpoint, {
        method: 'POST',
        body: payload,
        credentials: 'same-origin',
        keepalive: true
      }).catch(() => {});
    }

    const fields = form.querySelectorAll('input, textarea, select');
    fields.forEach((field) => {
      if (!field.name) return;
      if (field.type === 'submit' || field.type === 'button' || field.type === 'file') return;
      if (DECLARATION_FIELDS.has(field.name)) return;

      const eventName = (field.tagName === 'SELECT' || field.type === 'checkbox' || field.type === 'radio') ? 'change' : 'input';
      field.addEventListener(eventName, scheduleAutosave);

      if (eventName !== 'change') {
        field.addEventListener('change', scheduleAutosave);
      }
    });

    form.addEventListener('submit', (event) => {
      if (event.defaultPrevented) return;
      submitting = true;
      clearTimeout(autosaveTimeout);
    });
    window.addEventListener('pagehide', flushAutosave);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        flushAutosave();
      }
    });
  }

  window.initFormAutosave = initFormAutosave;
  window.initAutosaveRefreshGuard = initAutosaveRefreshGuard;
})();
