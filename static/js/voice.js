function showLoading(button) {
    button.innerHTML = '<div class="spinner"></div>';
    button.disabled = true;
}

function hideLoading(button) {
    button.innerHTML = '<i class="fas fa-microphone"></i>';
    button.disabled = false;
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    // Show error for 3 seconds
    setTimeout(() => errorDiv.remove(), 3000);
} 