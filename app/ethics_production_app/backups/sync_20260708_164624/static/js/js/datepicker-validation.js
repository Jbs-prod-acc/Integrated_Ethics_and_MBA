// datepicker-validation.js
// Validates date fields for dd/mm/yyyy format and provides UI feedback

function validateDateInput(input) {
  const ddmmyyyyRegex = /^(\d{2})\/(\d{2})\/(\d{4})$/;
  const yyyymmddRegex = /^(\d{4})-(\d{2})-(\d{2})$/;
  input.addEventListener('input', function () {
    let value = input.value;
    let isValid = false;
    if (input.type === 'date') {
      isValid = yyyymmddRegex.test(value);
    } else {
      isValid = ddmmyyyyRegex.test(value);
    }
    if (!isValid) {
      input.classList.add('date-warning');
      input.setCustomValidity(input.type === 'date' ? 'Date must be in yyyy-mm-dd format' : 'Date must be in dd/mm/yyyy format');
      showDateFormatHint(input);
    } else {
      input.classList.remove('date-warning');
      input.setCustomValidity('');
      hideDateFormatHint(input);
    }
  });
}

function showDateFormatHint(input) {
  let hint = input.nextElementSibling;
  if (!hint || !hint.classList.contains('date-format-hint')) {
    hint = document.createElement('div');
    hint.className = 'date-format-hint';
    hint.style.color = '#d9534f';
    hint.style.fontSize = '0.9em';
    hint.style.marginTop = '2px';
    hint.textContent = input.type === 'date' ? 'Format: yyyy-mm-dd' : 'Format: dd/mm/yyyy';
    input.parentNode.insertBefore(hint, input.nextSibling);
  }
}

function hideDateFormatHint(input) {
  let hint = input.nextElementSibling;
  if (hint && hint.classList.contains('date-format-hint')) {
    hint.remove();
  }
}

function setupDateValidation() {
  const dateInputs = document.querySelectorAll('input[type="text"], input[type="date"]');
  dateInputs.forEach(input => {
    if (input.name && (input.name.toLowerCase().includes('date') || input.id && input.id.toLowerCase().includes('date'))) {
      validateDateInput(input);
    }
  });
}

document.addEventListener('DOMContentLoaded', setupDateValidation);
