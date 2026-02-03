// photos.local - JavaScript utilities

// Auto-dismiss flash messages after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(function(flash) {
        setTimeout(function() {
            flash.style.opacity = '0';
            flash.style.transition = 'opacity 0.3s';
            setTimeout(function() {
                flash.remove();
            }, 300);
        }, 5000);
    });
});

// API helper functions
const api = {
    post: function(url, data) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        }).then(response => response.json());
    },

    get: function(url) {
        return fetch(url).then(response => response.json());
    }
};

// Status polling for dashboard
function pollStatus(interval) {
    interval = interval || 30000;

    function update() {
        api.get('/api/status').then(function(data) {
            // Update status values if elements exist
            const photoCount = document.querySelector('.status-item .value');
            if (photoCount && data.cache) {
                // Find the photos count element
                document.querySelectorAll('.status-item').forEach(function(item) {
                    const label = item.querySelector('.label');
                    const value = item.querySelector('.value');
                    if (label && value) {
                        if (label.textContent === 'Photos') {
                            value.textContent = data.cache.count;
                        } else if (label.textContent === 'Slideshow') {
                            value.textContent = data.slideshow.running ? 'Running' : 'Stopped';
                            value.className = 'value ' + (data.slideshow.running ? 'running' : 'stopped');
                        }
                    }
                });
            }
        }).catch(function(error) {
            console.error('Failed to poll status:', error);
        });
    }

    // Initial update
    update();

    // Poll periodically
    setInterval(update, interval);
}

// Confirm before destructive actions
function confirmAction(message) {
    return confirm(message);
}

// Initialize polling on dashboard page
if (document.querySelector('.dashboard')) {
    pollStatus(30000);
}
