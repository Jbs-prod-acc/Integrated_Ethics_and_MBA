document.addEventListener('DOMContentLoaded', function () {
  if (typeof flatpickr !== 'function') {
    return;
  }

  document.querySelectorAll('.js-ddmmyyyy-datepicker').forEach(function (input) {
    flatpickr(input, {
      dateFormat: 'd/m/Y',
      allowInput: false,
      disableMobile: true,
      monthSelectorType: 'static'
    });
  });
});
