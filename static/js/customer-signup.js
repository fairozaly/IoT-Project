(function () {
  'use strict';

  const form = document.querySelector('[data-customer-signup]');
  if (!form) return;

  const fields = {
    first_name: document.getElementById('first_name'),
    last_name: document.getElementById('last_name'),
    address: document.getElementById('address'),
    phone: document.getElementById('phone'),
    email: document.getElementById('email'),
    password: document.getElementById('password'),
    confirm_password: document.getElementById('confirm_password')
  };

  const messages = {
    first_name: 'Enter your first name.',
    last_name: 'Enter your last name.',
    address: 'Enter your address.',
    phone: 'Enter a valid 10-digit phone number.',
    email: 'Enter a valid email address.',
    password: 'Use a password with at least 8 characters.',
    confirm_password: 'The passwords do not match.'
  };

  function errorElement(name) {
    return document.querySelector('[data-error-for="' + name + '"]');
  }

  function setError(name, message) {
    const field = fields[name];
    const error = errorElement(name);
    if (!field || !error) return;
    field.setAttribute('aria-invalid', 'true');
    error.textContent = message;
    error.hidden = false;
    field.closest('.customer-field')?.classList.add('has-error');
  }

  function clearError(name) {
    const field = fields[name];
    const error = errorElement(name);
    if (!field || !error) return;
    field.removeAttribute('aria-invalid');
    error.textContent = '';
    error.hidden = true;
    field.closest('.customer-field')?.classList.remove('has-error');
  }

  function validateField(name) {
    const field = fields[name];
    if (!field) return true;
    const value = field.value.trim();
    let message = '';

    if (field.required && !value) {
      message = messages[name];
    } else if (name === 'phone' && value && !field.validity.valid) {
      message = messages.phone;
    } else if (name === 'email' && !field.validity.valid) {
      message = messages.email;
    } else if (name === 'password' && value.length < 8) {
      message = messages.password;
    } else if (name === 'confirm_password' && value !== fields.password.value) {
      message = messages.confirm_password;
    }

    if (message) setError(name, message); else clearError(name);
    return !message;
  }

  function validateAll() {
    const order = ['first_name', 'last_name', 'address', 'phone', 'email', 'password', 'confirm_password'];
    const invalid = order.filter((name) => !validateField(name));
    if (invalid.length) {
      fields[invalid[0]].focus();
      return false;
    }
    return true;
  }

  Object.keys(fields).forEach((name) => {
    fields[name]?.addEventListener('blur', function () {
      if (this.value.trim() || this === fields.confirm_password) validateField(name);
    });
    fields[name]?.addEventListener('input', function () {
      if (this.getAttribute('aria-invalid') === 'true') validateField(name);
      if (name === 'password' && fields.confirm_password.value) validateField('confirm_password');
    });
  });

  document.querySelectorAll('[data-password-toggle]').forEach((toggle) => {
    toggle.addEventListener('click', function () {
      const input = document.getElementById(this.dataset.passwordToggle);
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      this.textContent = showing ? 'Show' : 'Hide';
      this.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
    });
  });

  form.addEventListener('submit', function (event) {
    if (!validateAll()) {
      event.preventDefault();
      return;
    }
    const submit = form.querySelector('button[type="submit"]');
    if (submit) {
      submit.disabled = true;
      submit.classList.add('is-submitting');
      submit.innerHTML = 'Creating account <span aria-hidden="true">…</span>';
    }
  });

  const summary = document.getElementById('signup-error');
  if (summary) summary.focus();
})();
