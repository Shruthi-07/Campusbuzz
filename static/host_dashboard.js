document.addEventListener('DOMContentLoaded', function() {
    // Modal handling
    const createEventModal = document.getElementById('create-event-modal');
    const registrationsModal = document.getElementById('registrations-modal');
    const createEventBtn = document.getElementById('create-event-btn');
    const noEventsCreateBtn = document.getElementById('no-events-create-btn');
    const cancelCreateEventBtn = document.getElementById('cancel-create-event');
    const closeRegistrationsBtn = document.getElementById('close-registrations');
    const downloadRegistrationsBtn = document.getElementById('download-registrations');
    const closeModalButtons = document.querySelectorAll('.close-modal');

    // Open create event modal
    if (createEventBtn) {
        createEventBtn.addEventListener('click', function(e) {
            e.preventDefault();
            createEventModal.style.display = 'block';
        });
    }

    // Open create event modal from no-events section
    if (noEventsCreateBtn) {
        noEventsCreateBtn.addEventListener('click', function() {
            createEventModal.style.display = 'block';
        });
    }

    // Close create event modal
    if (cancelCreateEventBtn) {
        cancelCreateEventBtn.addEventListener('click', function() {
            createEventModal.style.display = 'none';
        });
    }

    // Close registrations modal
    if (closeRegistrationsBtn) {
        closeRegistrationsBtn.addEventListener('click', function() {
            registrationsModal.style.display = 'none';
        });
    }

    // Close modals with X button
    closeModalButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            button.closest('.modal').style.display = 'none';
        });
    });

    // Close modals when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target == createEventModal) {
            createEventModal.style.display = 'none';
        } else if (event.target == editEventModal) {
            editEventModal.style.display = 'none';
        } else if (event.target == registrationsModal) {
            registrationsModal.style.display = 'none';
        }
    });

    // Handle View Registrations button clicks
    const viewRegistrationsButtons = document.querySelectorAll('.view-registrations');
    viewRegistrationsButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const eventId = this.getAttribute('data-event-id');
            const registrationsContainer = document.getElementById('registrations-container');
            
            // Show loading indicator
            registrationsContainer.innerHTML = '<div class="loader">Loading registrations...</div>';
            registrationsModal.style.display = 'block';
            
            // Fetch registrations
            fetch('/get_event_registrations/' + eventId)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        if (data.registrations.length > 0) {
                            // Create table for registrations
                            let tableHTML = `
                                <h3>${data.event_title} - Registrations</h3>
                                <table class="registrations-table">
                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>Roll Number</th>
                                            <th>Email</th>
                                            <th>Phone</th>
                                            <th>Department</th>
                                            <th>Registration Date</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                            `;
                            
                            data.registrations.forEach(reg => {
                                tableHTML += `
                                    <tr>
                                        <td>${reg.name}</td>
                                        <td>${reg.roll_number}</td>
                                        <td>${reg.email}</td>
                                        <td>${reg.phone_number}</td>
                                        <td>${reg.department}</td>
                                        <td>${reg.registration_date}</td>
                                    </tr>
                                `;
                            });
                            
                            tableHTML += `
                                    </tbody>
                                </table>
                            `;
                            
                            registrationsContainer.innerHTML = tableHTML;
                            
                            // Store event ID for download functionality
                            downloadRegistrationsBtn.setAttribute('data-event-id', eventId);
                        } else {
                            registrationsContainer.innerHTML = `
                                <div class="no-registrations">
                                    <i class="fas fa-user-times"></i>
                                    <p>No registrations found for this event yet.</p>
                                </div>
                            `;
                        }
                    } else {
                        registrationsContainer.innerHTML = `
                            <div class="error-message">
                                <p>Failed to load registrations: ${data.message}</p>
                            </div>
                        `;
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    registrationsContainer.innerHTML = `
                        <div class="error-message">
                            <p>An error occurred while loading registrations.</p>
                        </div>
                    `;
                });
        });
    });

    // Handle download registrations
    if (downloadRegistrationsBtn) {
        downloadRegistrationsBtn.addEventListener('click', function() {
            const eventId = this.getAttribute('data-event-id');
            if (eventId) {
                window.location.href = '/download_registrations/' + eventId;
            }
        });
    }

    // Handle Cancel Event button clicks
    const cancelEventButtons = document.querySelectorAll('.cancel-event');
    cancelEventButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const eventId = this.getAttribute('data-event-id');
            
            if (confirm('Are you sure you want to cancel this event? This action cannot be undone.')) {
                fetch('/cancel_event/' + eventId, {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Event cancelled successfully.');
                        // Reload the page to reflect changes
                        window.location.reload();
                    } else {
                        alert('Failed to cancel event: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred while cancelling the event.');
                });
            }
        });
    });

    // Handle View Report button clicks
    const viewReportButtons = document.querySelectorAll('.view-report');
    viewReportButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const eventId = this.getAttribute('data-event-id');
            window.location.href = '/event_report/' + eventId;
        });
    });

    // Date validation for event creation
    const eventDateInput = document.getElementById('event-date');
    const registrationDeadlineInput = document.getElementById('registration-deadline');
    
    if (eventDateInput && registrationDeadlineInput) {
        // Set minimum date as today
        const today = new Date();
        const formattedDate = today.toISOString().split('T')[0];
        eventDateInput.setAttribute('min', formattedDate);
        
        // Ensure registration deadline 
        eventDateInput.addEventListener('change', function() {
            const eventDate = new Date(this.value);
            eventDate.setHours(23, 59, 59, 999); // Set event date to end of day
            const registrationDeadline = new Date(registrationDeadlineInput.value);
        
            if (registrationDeadline > eventDate) {
                alert('Registration deadline must be on or before the event day.');
                registrationDeadlineInput.value = '';
            }
        });
        
        registrationDeadlineInput.addEventListener('change', function() {
            if (eventDateInput.value) {
                const eventDate = new Date(eventDateInput.value);
                eventDate.setHours(23, 59, 59, 999); // End of event day
                const registrationDeadline = new Date(this.value);
        
                if (registrationDeadline > eventDate) {
                    alert('Registration deadline must be on or before the event day.');
                    this.value = '';
                }
            }
        });        
    }

    // Check for expired events on page load
    function checkExpiredEvents() {
        fetch('/check_expired_events')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.count > 0) {
                    // Optionally notify the user that events were moved
                    console.log(`${data.count} expired events moved to history`);
                }
            })
            .catch(error => {
                console.error('Error checking expired events:', error);
            });
    }

    // Call this function when the page loads
    checkExpiredEvents();
});
// Mobile menu toggle functionality
document.addEventListener('DOMContentLoaded', function() {
    const toggle = document.querySelector('.toggle');
    const menu = document.querySelector('.menu');
    
    // Toggle menu when hamburger icon is clicked
    toggle.addEventListener('click', function() {
        menu.classList.toggle('active');
        toggle.classList.toggle('active');
    });
    
    // Close menu when a menu item is clicked (for better UX)
    const menuItems = document.querySelectorAll('.menu li a');
    menuItems.forEach(item => {
        item.addEventListener('click', function() {
            menu.classList.remove('active');
            toggle.classList.remove('active');
        });
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', function(event) {
        const isClickInsideMenu = menu.contains(event.target);
        const isClickOnToggle = toggle.contains(event.target);
        
        if (!isClickInsideMenu && !isClickOnToggle && menu.classList.contains('active')) {
            menu.classList.remove('active');
            toggle.classList.remove('active');
        }
    });
});

// Add event listeners for delete past event buttons
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to delete buttons
    const deleteButtons = document.querySelectorAll('.delete-past-event');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const eventId = this.getAttribute('data-event-id');
            
            if (confirm('Are you sure you want to delete this event record? This action cannot be undone.')) {
                deletePastEvent(eventId);
            }
        });
    });
});

// Function to delete past event
function deletePastEvent(eventId) {
    fetch(`/delete_past_event/${eventId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            alert(data.message);
            
            // Remove the event card from DOM
            const eventCard = document.querySelector(`.delete-past-event[data-event-id="${eventId}"]`).closest('.event-card');
            eventCard.remove();
            
            // If no more past events, show "no events" message
            const pastEventsContainer = document.querySelector('#past-events .events-container');
            if (pastEventsContainer.querySelector('.event-card') === null) {
                pastEventsContainer.innerHTML = `
                    <div class="no-events-message">
                        <i class="fas fa-history"></i>
                        <p>No past events found.</p>
                    </div>
                `;
            }
        } else {
            // Show error message
            alert('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('An error occurred while deleting the event.');
    });
}