(function () {
  function setConditionalField(containerId, inputName, visible) {
    const container = document.getElementById(containerId);
    const input = document.querySelector('[name="' + inputName + '"]');
    if (!container || !input) return;

    container.style.display = visible ? 'block' : 'none';
    input.required = visible;
    input.disabled = !visible;
    if (!visible) {
      input.value = '';
    }
  }

  window.togglePublicData = function () {
    const selected = document.querySelector('input[name="data_public"]:checked');
    const answer = selected ? selected.value : '';
    setConditionalField('public_evidence_fields', 'public_evidence', answer === 'No');
    setConditionalField('access_conditions_fields', 'access_conditions', answer === 'Yes');
  };

  window.togglePersonalInfo = function () {
    const selected = document.querySelector('input[name="personal_info"]:checked');
    const container = document.getElementById('personalInfoComment');
    const comment = document.querySelector('[name="personal_info_comment"]');
    if (!container || !comment) return;

    const containsPersonalInfo = !!selected && selected.value === 'Yes';
    container.style.display = containsPersonalInfo ? 'block' : 'none';
    comment.required = containsPersonalInfo;
    comment.disabled = false;

    if (containsPersonalInfo) {
      if (comment.value.trim().toLowerCase() === 'not applicable') {
        comment.value = '';
      }
    } else if (selected) {
      comment.value = 'Not Applicable';
    }
  };

  window.togglePrivatePermission = function () {
    const selected = document.querySelector('input[name="private_permission"]:checked');
    const visible = selected && selected.value === 'Yes';
    const container = document.getElementById('permission_details_box');
    const details = document.querySelector('[name="permission_details"]');
    const file = document.querySelector('[name="private_permission_file"]');
    const clearFile = document.querySelector('[name="clear_private_permission_file"]');

    if (container) container.style.display = visible ? 'block' : 'none';
    if (details) {
      details.required = !!visible;
      details.disabled = !visible;
      if (!visible) details.value = '';
    }
    if (file) {
      file.disabled = !visible;
      if (!visible) file.value = '';
    }
    if (clearFile) clearFile.value = visible ? 'No' : 'Yes';
  };

  window.deletePrivatePermissionUpload = function () {
    if (!window.confirm('Delete the uploaded permission document from this draft?')) return;

    const file = document.querySelector('[name="private_permission_file"]');
    const clearFile = document.querySelector('[name="clear_private_permission_file"]');
    const currentFile = document.getElementById('current_private_permission_file');
    const uploadStatus = document.getElementById('private_permission_upload_status');

    if (file) file.value = '';
    if (clearFile) {
      clearFile.value = 'Yes';
      clearFile.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (currentFile) currentFile.remove();
    if (uploadStatus) uploadStatus.textContent = 'Uploaded document deleted from this draft.';
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.togglePublicData();
    window.togglePersonalInfo();
    window.togglePrivatePermission();

    const permissionFile = document.querySelector('[name="private_permission_file"]');
    const uploadStatus = document.getElementById('private_permission_upload_status');
    if (permissionFile && uploadStatus) {
      permissionFile.addEventListener('change', function () {
        uploadStatus.textContent = permissionFile.files && permissionFile.files.length
          ? 'Selected file: ' + permissionFile.files[0].name
          : '';
      });
    }
  });
})();
