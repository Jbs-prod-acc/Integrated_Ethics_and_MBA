(function () {
  "use strict";

  const selector = 'input[name="sample_size[]"]';
  const exampleMessage =
    "Enter a positive number like 100 or an interval like 100-150. Use numbers and one hyphen only.";

  function validationMessage(input) {
    const value = input.value.trim();
    if (!value) {
      return "Sample Size is required. " + exampleMessage;
    }

    const compact = value.replace(/\s+/g, "");
    if (!/^\d+(?:-\d+)?$/.test(compact)) {
      return exampleMessage;
    }

    const values = compact.split("-").map(Number);
    if (values.some((number) => number < 1)) {
      return "Sample Size must be greater than zero. " + exampleMessage;
    }
    if (values.length === 2 && values[1] < values[0]) {
      return "The interval must end at or above its starting number, for example 100-150.";
    }
    if (values.length === 2 && values[1] > values[0] * 2) {
      return (
        "The interval is too wide. For example, an interval starting at 100 " +
        "may not end above 200."
      );
    }
    return "";
  }

  function feedbackElement(input) {
    let feedback = input.parentElement.querySelector(".sample-size-feedback");
    if (!feedback) {
      feedback = document.createElement("div");
      feedback.className = "invalid-feedback sample-size-feedback";
      feedback.setAttribute("role", "alert");
      input.insertAdjacentElement("afterend", feedback);
    }
    return feedback;
  }

  function validate(input) {
    const message = validationMessage(input);
    input.required = true;
    input.setCustomValidity(message);
    input.classList.toggle("is-invalid", Boolean(message));
    input.classList.toggle("border-warning", Boolean(message));
    input.setAttribute("aria-invalid", message ? "true" : "false");
    const feedback = feedbackElement(input);
    feedback.textContent = message;
    feedback.style.display = message ? "block" : "none";
    return !message;
  }

  document.addEventListener("input", function (event) {
    if (event.target.matches(selector)) {
      validate(event.target);
    }
  });

  document.addEventListener(
    "submit",
    function (event) {
      const form = event.target;
      const inputs = Array.from(form.querySelectorAll(selector));
      const invalidInput = inputs.find((input) => !validate(input));
      if (!invalidInput) {
        inputs.forEach((input) => {
          input.value = input.value.replace(/\s+/g, "");
        });
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      invalidInput.scrollIntoView({ behavior: "smooth", block: "center" });
      invalidInput.focus();
      window.alert(invalidInput.validationMessage || exampleMessage);
    },
    true
  );

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(selector).forEach((input) => {
      input.required = true;
      input.setAttribute("autocomplete", "off");
      if (input.value.trim()) {
        validate(input);
      }
    });
  });
})();
