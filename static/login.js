// Form switching
document.querySelectorAll('.auth-tab, .switch-form').forEach(item => {
    item.addEventListener('click', function () {
        const targetTab = this.dataset.tab || this.dataset.form;

        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.classList.remove('active');
            if (tab.dataset.tab === targetTab) tab.classList.add('active');
        });

        document.querySelectorAll('.form-container').forEach(form => {
            form.classList.remove('active');
        });
        document.querySelector(`.${targetTab}-form`).classList.add('active');
    });
});

// Enhanced role toggle functionality
document.querySelectorAll('.role-option').forEach(option => {
    option.addEventListener('click', function () {
        const form = this.closest('.auth-form');
        const role = this.dataset.role;

        form.querySelectorAll('.role-option').forEach(opt => opt.classList.remove('active'));
        this.classList.add('active');

        // Update fields
        if (form.id === 'signupForm') {
            form.querySelectorAll('.signup-fields').forEach(field => field.classList.remove('active'));
            form.querySelector(`.${role}-fields`).classList.add('active');
        }

        // Update username field label and type based on role
        if (form.id === 'loginForm') {
            const usernameLabel = document.getElementById('username-label');
            const usernameInput = document.getElementById('login-username');
            
            if (role === 'student') {
                usernameLabel.textContent = 'Roll Number';
                usernameInput.type = 'text';
                document.querySelector('.host-secret').style.display = 'none';
            } else if (role === 'host') {
                usernameLabel.textContent = 'Email';
                usernameInput.type = 'email';
                document.querySelector('.host-secret').style.display = 'block';
            }
        }

        // Update hidden usertype input
        form.querySelector('input[name="usertype"]').value = role;
    });
});

// Password toggle
document.querySelectorAll('.password-toggle').forEach(toggle => {
    toggle.addEventListener('click', function () {
        const input = this.previousElementSibling;
        const icon = this.querySelector('i');
        input.type = input.type === 'password' ? 'text' : 'password';
        icon.classList.toggle('fa-eye');
        icon.classList.toggle('fa-eye-slash');
    });
});

// Form validation
document.getElementById('signupForm').addEventListener('submit', function (e) {
    const pass = document.getElementById('signup-password').value;
    const confirm = document.getElementById('confirm-password').value;
    
    // Only check passwords if we're actually submitting the form (not if we're in OTP mode)
    if (document.getElementById('createAccountBtn').textContent === 'Create Account') {
        if (pass !== confirm) {
            e.preventDefault();
            showPopup('Password Error', 'Passwords do not match. Please try again.', 'error');
        }
    }
});

// Show popup function for reuse
function showPopup(title, message, type = 'success') {
    const overlay = document.getElementById('popupOverlay');
    const icon = document.getElementById('popupIcon');
    const titleEl = document.getElementById('popupTitle');
    const popupMessage = document.getElementById('popupMessage');
    
    icon.className = "popup-icon " + type;
    icon.innerHTML = type === 'success' ? 
        '<i class="fas fa-check-circle"></i>' : 
        '<i class="fas fa-exclamation-circle"></i>';
    titleEl.textContent = title;
    popupMessage.textContent = message;
    
    overlay.classList.add('active');
}

// Show OTP popup function
function showOtpPopup() {
    document.getElementById('otpPopupOverlay').classList.add('active');
    startOtpTimer(60);
    document.getElementById('otp-input-popup').focus();
}

// Popup close button handlers
document.querySelectorAll('.popup-close').forEach(button => {
    button.addEventListener('click', function() {
        this.closest('.popup-overlay').classList.remove('active');
    });
});

// Close popup when clicking outside
document.querySelectorAll('.popup-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
        if (e.target === this) {
            this.classList.remove('active');
        }
    });
});

// OTP Timer functions
let otpTimerInterval;

function startOtpTimer(seconds) {
    const timerDisplay = document.getElementById('otpTimerPopup');
    clearInterval(otpTimerInterval);
    
    let timeLeft = seconds;
    timerDisplay.textContent = `OTP expires in: ${timeLeft} seconds`;
    
    otpTimerInterval = setInterval(() => {
        timeLeft--;
        timerDisplay.textContent = `OTP expires in: ${timeLeft} seconds`;
        
        if (timeLeft <= 0) {
            clearInterval(otpTimerInterval);
            timerDisplay.textContent = "OTP expired! Request a new one.";
            document.getElementById('verifyOtpBtn').disabled = true;
        }
    }, 1000);
}

function stopOtpTimer() {
    clearInterval(otpTimerInterval);
}

// Set default actions
document.getElementById('loginForm').action = '/login';
document.getElementById('signupForm').action = '/register';

// Enhanced OTP handling with popup
document.addEventListener('DOMContentLoaded', function() {
    const signupForm = document.getElementById('signupForm');
    const createAccountBtn = document.getElementById('createAccountBtn');
    const verifyOtpBtn = document.getElementById('verifyOtpBtn');
    const resendOtpBtn = document.getElementById('resendOtpBtn');

    signupForm.addEventListener('submit', function(e) {
        e.preventDefault(); // prevent default form submission
        
        // If we're already at the Create Account stage, submit the form
        if (createAccountBtn.textContent === 'Create Account') {
            // Final validation before submitting
            const phoneVerified = document.getElementById('phone-verified').value;
            if (phoneVerified !== 'true') {
                showPopup('Error', 'Please verify your phone number first', 'error');
                return;
            }
            
            // Check password match again
            const pass = document.getElementById('signup-password').value;
            const confirm = document.getElementById('confirm-password').value;
            if (pass !== confirm) {
                showPopup('Password Error', 'Passwords do not match. Please try again.', 'error');
                return;
            }
            
            // All validations passed, submit the form
            this.submit();
            return;
        }
        
        // Otherwise, we're at the Generate OTP stage
        const phoneNumber = document.getElementById('signup-phone').value.trim();

        // Format check
        if (!phoneNumber.match(/^\+?[1-9]\d{9,14}$/)) {
            showPopup('Error', 'Invalid phone number format. Please include country code (e.g., +91)', 'error');
            return;
        }

        // Send OTP
        createAccountBtn.textContent = 'Sending...';
        createAccountBtn.disabled = true;
        fetch('/send-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                phone_number: phoneNumber,
                usertype: document.getElementById('signup-usertype').value  
            }),
        })
        .then(res => res.json())
        .then(data => {
            createAccountBtn.disabled = false;
            if (data.success) {
                // Show the OTP popup instead of inline form
                showOtpPopup();
                document.getElementById('otpStatusPopup').textContent = 'OTP sent successfully! Enter the 6-digit code.';
                document.getElementById('otpStatusPopup').classList.add('success');
                document.getElementById('otpStatusPopup').classList.remove('error');
                document.getElementById('otpStatusPopup').style.display = 'block';
            } else {
                showPopup('Error', data.message, 'error');
                createAccountBtn.textContent = 'Generate OTP';
            }
        })
        .catch(err => {
            console.error('OTP Send Error:', err);
            showPopup('Error', 'Could not send OTP. Please try again.', 'error');
            createAccountBtn.disabled = false;
            createAccountBtn.textContent = 'Generate OTP';
        });
    });

    // Verify OTP button handler
    verifyOtpBtn.addEventListener('click', function() {
        const otp = document.getElementById('otp-input-popup').value.trim();
        const statusEl = document.getElementById('otpStatusPopup');
        
        if (!otp || otp.length !== 6) {
            statusEl.textContent = 'Please enter a valid 6-digit OTP';
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            statusEl.style.display = 'block';
            return;
        }

        this.textContent = 'Verifying...';
        this.disabled = true;

        fetch('/verify-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ otp }),
        })
        .then(res => res.json())
        .then(data => {
            this.disabled = false;
            if (data.success) {
                document.getElementById('phone-verified').value = 'true';
                statusEl.textContent = 'Phone number verified successfully!';
                statusEl.classList.add('success');
                statusEl.classList.remove('error');
                
                // Mark phone field as verified
                document.getElementById('signup-phone').readOnly = true;
                document.getElementById('signup-phone').classList.add('otp-verified');
                
                // Update button to final stage
                createAccountBtn.textContent = 'Create Account';
                
                // Close the OTP popup after a short delay
                setTimeout(() => {
                    document.getElementById('otpPopupOverlay').classList.remove('active');
                    stopOtpTimer();
                }, 1500);

                // Show success popup
                showPopup('Success', 'Phone number verified successfully! You can now create your account.', 'success');
            } else {
                statusEl.textContent = data.message;
                statusEl.classList.add('error');
                statusEl.classList.remove('success');
                this.textContent = 'Verify OTP';
            }
        })
        .catch(err => {
            console.error('OTP Verify Error:', err);
            statusEl.textContent = 'Could not verify OTP. Please try again.';
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            this.disabled = false;
            this.textContent = 'Verify OTP';
        });
    });

    // Resend OTP button handler
    resendOtpBtn.addEventListener('click', function() {
        const phoneNumber = document.getElementById('signup-phone').value.trim();
        this.disabled = true;
        this.textContent = 'Sending...';

        fetch('/send-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                phone_number: phoneNumber,
                usertype: document.getElementById('signup-usertype').value  // Add usertype 
            }),
        })
        .then(res => res.json())
        .then(data => {
            setTimeout(() => {
                this.disabled = false;
                this.textContent = 'Resend OTP';
            }, 30000); // Disable resend for 30 seconds
            
            const statusEl = document.getElementById('otpStatusPopup');
            if (data.success) {
                statusEl.textContent = 'New OTP sent successfully! Valid for 60 seconds.';
                statusEl.classList.add('success');
                statusEl.classList.remove('error');
                document.getElementById('verifyOtpBtn').disabled = false;
                startOtpTimer(60);
            } else {
                statusEl.textContent = data.message;
                statusEl.classList.add('error');
                statusEl.classList.remove('success');
            }
            statusEl.style.display = 'block';
        })
        .catch(err => {
            console.error('OTP Resend Error:', err);
            const statusEl = document.getElementById('otpStatusPopup');
            statusEl.textContent = 'Could not send OTP. Please try again.';
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            statusEl.style.display = 'block';
            
            this.disabled = false;
            this.textContent = 'Resend OTP';
        });
    });
});
// Forgot Password Functionality
document.addEventListener('DOMContentLoaded', function() {
    // Store reset user info in a more reliable way
    let resetUserInfo = {
        identifier: '',
        usertype: '',
        secretKey: ''  // Added secret key storage
    };

    // Fix: Use the correct selector for the "Forgot Password?" link
    document.getElementById('forgotPasswordLink').addEventListener('click', function(e) {
        e.preventDefault();
        document.getElementById('forgotPasswordOverlay').classList.add('active');
        // Reset to first step
        showForgotPasswordStep(1);
    });

    // Toggle between Student/Host roles in forgot password popup
    document.querySelectorAll('#forgotRoleStudent, #forgotRoleHost').forEach(option => {
        option.addEventListener('click', function() {
            const role = this.dataset.role;
            
            // Update active class
            document.getElementById('forgotRoleStudent').classList.remove('active');
            document.getElementById('forgotRoleHost').classList.remove('active');
            this.classList.add('active');
            
            // Show/hide appropriate fields
            if (role === 'student') {
                document.getElementById('forgotStudentField').style.display = 'block';
                document.getElementById('forgotHostField').style.display = 'none';
            } else if (role === 'host') {
                document.getElementById('forgotStudentField').style.display = 'none';
                document.getElementById('forgotHostField').style.display = 'block';
            }
        });
    });

    // Request OTP button handler
    document.getElementById('requestResetOtpBtn').addEventListener('click', function() {
        // Determine if we're student or host mode
        const isStudent = document.getElementById('forgotRoleStudent').classList.contains('active');
        
        let identifier = '', usertype = '', secretKey = '';
        
        if (isStudent) {
            identifier = document.getElementById('forgot-rollnumber').value.trim();
            usertype = 'student';
            
            if (!identifier) {
                showForgotPasswordError('Please enter your roll number');
                return;
            }
        } else {
            identifier = document.getElementById('forgot-email').value.trim();
            usertype = 'host';
            secretKey = document.getElementById('forgot-secret-key').value.trim();
            
            if (!identifier) {
                showForgotPasswordError('Please enter your email');
                return;
            }
            
            if (!secretKey) {
                showForgotPasswordError('Please enter the host secret key');
                return;
            }
        }
        
        // Disable button and show loading
        this.disabled = true;
        this.textContent = 'Sending...';
        
        // Save user info for next steps
        resetUserInfo = {
            identifier: identifier,
            usertype: usertype,
            secretKey: secretKey  // Store secret key for later use
        };
        
        // Request OTP from server
        fetch('/request-reset-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                identifier: identifier,
                usertype: usertype,
                secret_key: secretKey
            }),
        })
        .then(res => {
            if (!res.ok) {
                throw new Error('Server returned ' + res.status);
            }
            return res.json();
        })
        .then(data => {
            this.disabled = false;
            this.textContent = 'Send Reset OTP';
            
            if (data.success) {
                // Move to OTP verification step
                showForgotPasswordStep(2);
                startForgotOtpTimer(60);
                
                // Show success message
                const statusEl = document.getElementById('forgotOtpStatus');
                statusEl.textContent = 'OTP sent successfully to your registered phone!';
                statusEl.classList.add('success');
                statusEl.classList.remove('error');
                statusEl.style.display = 'block';
                
                // Focus the OTP input
                document.getElementById('forgot-otp-input').focus();
            } else {
                showForgotPasswordError(data.message || 'Failed to send OTP');
            }
        })
        .catch(err => {
            console.error('OTP Request Error:', err);
            this.disabled = false;
            this.textContent = 'Send Reset OTP';
            showForgotPasswordError('Failed to send OTP. Please try again.');
        });
    });

    // Verify OTP for password reset
    document.getElementById('verifyResetOtpBtn').addEventListener('click', function() {
        const otp = document.getElementById('forgot-otp-input').value.trim();
        const statusEl = document.getElementById('forgotOtpStatus');
        
        if (!otp || otp.length !== 6) {
            statusEl.textContent = 'Please enter a valid 6-digit OTP';
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            statusEl.style.display = 'block';
            return;
        }
        
        this.disabled = true;
        this.textContent = 'Verifying...';
        
        // Verify OTP
        fetch('/verify-reset-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                otp: otp,
                identifier: resetUserInfo.identifier,
                usertype: resetUserInfo.usertype,
                secret_key: resetUserInfo.secretKey  // Include secret key for host users
            }),
        })
        .then(res => {
            if (!res.ok) {
                throw new Error('Server returned ' + res.status);
            }
            return res.json();
        })
        .then(data => {
            this.disabled = false;
            this.textContent = 'Verify OTP';
            
            if (data.success) {
                // Move to password reset step
                showForgotPasswordStep(3);
                
                // Clear OTP timer
                clearInterval(forgotOtpTimerInterval);
            } else {
                statusEl.textContent = data.message || 'Invalid OTP. Please try again.';
                statusEl.classList.add('error');
                statusEl.classList.remove('success');
                statusEl.style.display = 'block';
            }
        })
        .catch(err => {
            console.error('OTP Verification Error:', err);
            this.disabled = false;
            this.textContent = 'Verify OTP';
            
            statusEl.textContent = 'Failed to verify OTP. Please try again.';
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            statusEl.style.display = 'block';
        });
    });

    // Resend OTP for password reset
    document.getElementById('resendResetOtpBtn').addEventListener('click', function() {
        const statusEl = document.getElementById('forgotOtpStatus');
        
        this.disabled = true;
        this.textContent = 'Sending...';
        
        // Use stored user info
        fetch('/request-reset-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                identifier: resetUserInfo.identifier,
                usertype: resetUserInfo.usertype,
                secret_key: resetUserInfo.secretKey  // Include secret key for host users
            }),
        })
        .then(res => {
            if (!res.ok) {
                throw new Error('Server returned ' + res.status);
            }
            return res.json();
        })
        .then(data => {
            // Disable resend for 30 seconds
            setTimeout(() => {
                this.disabled = false;
                this.textContent = 'Resend OTP';
            }, 30000);
            
            if (data.success) {
                // Reset timer
                startForgotOtpTimer(60);
                document.getElementById('verifyResetOtpBtn').disabled = false;
                
                statusEl.textContent = 'New OTP sent successfully! Valid for 60 seconds.';
                statusEl.classList.add('success');
                statusEl.classList.remove('error');
                statusEl.style.display = 'block';
            } else {
                statusEl.textContent = data.message || 'Failed to send OTP';
                statusEl.classList.add('error');
                statusEl.classList.remove('success');
                statusEl.style.display = 'block';
            }
        })
        .catch(err => {
            console.error('OTP Resend Error:', err);
            
            statusEl.textContent = 'Failed to send OTP. Please try again.';
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            statusEl.style.display = 'block';
            
            setTimeout(() => {
                this.disabled = false;
                this.textContent = 'Resend OTP';
            }, 30000);
        });
    });

    // Submit password reset
    document.getElementById('resetPasswordBtn').addEventListener('click', function() {
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-new-password').value;
        const statusEl = document.getElementById('passwordResetStatus');
        
        if (!newPassword) {
            statusEl.textContent = 'Please enter a new password';
            statusEl.classList.add('error');
            statusEl.style.display = 'block';
            return;
        }
        
        if (newPassword !== confirmPassword) {
            statusEl.textContent = 'Passwords do not match';
            statusEl.classList.add('error');
            statusEl.style.display = 'block';
            return;
        }
        
        this.disabled = true;
        this.textContent = 'Updating...';
        
        fetch('/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                identifier: resetUserInfo.identifier,
                usertype: resetUserInfo.usertype,
                new_password: newPassword,
                secret_key: resetUserInfo.secretKey  // Include secret key for host users
            }),
        })
        .then(res => {
            if (!res.ok) {
                throw new Error('Server returned ' + res.status);
            }
            return res.json();
        })
        .then(data => {
            this.disabled = false;
            this.textContent = 'Reset Password';
            
            if (data.success) {
                // Close the forgot password popup
                document.getElementById('forgotPasswordOverlay').classList.remove('active');
                
                // Show success popup
                showPopup('Success', 'Your password has been reset successfully. You can now login with your new password.', 'success');
                
                // Clear reset user info
                resetUserInfo = {
                    identifier: '',
                    usertype: '',
                    secretKey: ''
                };
            } else {
                statusEl.textContent = data.message || 'Failed to reset password';
                statusEl.classList.add('error');
                statusEl.style.display = 'block';
            }
        })
        .catch(err => {
            console.error('Password Reset Error:', err);
            this.disabled = false;
            this.textContent = 'Reset Password';
            
            statusEl.textContent = 'Failed to reset password. Please try again.';
            statusEl.classList.add('error');
            statusEl.style.display = 'block';
        });
    });

    // Make sure these helper functions are defined properly
    window.showForgotPasswordStep = function(step) {
        document.querySelectorAll('.forgot-password-step').forEach(el => {
            el.style.display = 'none';
        });
        document.getElementById(`forgotPasswordStep${step}`).style.display = 'block';
    };

    window.showForgotPasswordError = function(message) {
        const step = document.querySelector('.forgot-password-step[style="display: block;"]');
        const stepNumber = step.id.slice(-1);
        
        if (stepNumber === '1') {
            // For step 1, show as popup
            showPopup('Error', message, 'error');
        } else if (stepNumber === '2') {
            // For step 2, show in status element
            const statusEl = document.getElementById('forgotOtpStatus');
            statusEl.textContent = message;
            statusEl.classList.add('error');
            statusEl.classList.remove('success');
            statusEl.style.display = 'block';
        } else if (stepNumber === '3') {
            // For step 3, show in password reset status
            const statusEl = document.getElementById('passwordResetStatus');
            statusEl.textContent = message;
            statusEl.classList.add('error');
            statusEl.style.display = 'block';
        }
    };

    // OTP Timer for forgot password
    window.forgotOtpTimerInterval = null;

    window.startForgotOtpTimer = function(seconds) {
        const timerDisplay = document.getElementById('forgotOtpTimer');
        clearInterval(window.forgotOtpTimerInterval);
        
        let timeLeft = seconds;
        timerDisplay.textContent = `OTP expires in: ${timeLeft} seconds`;
        
        window.forgotOtpTimerInterval = setInterval(() => {
            timeLeft--;
            timerDisplay.textContent = `OTP expires in: ${timeLeft} seconds`;
            
            if (timeLeft <= 0) {
                clearInterval(window.forgotOtpTimerInterval);
                timerDisplay.textContent = "OTP expired! Request a new one.";
                document.getElementById('verifyResetOtpBtn').disabled = true;
            }
        }, 1000);
    };
});