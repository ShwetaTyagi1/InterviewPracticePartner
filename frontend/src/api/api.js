/**
 * api.js
 * 
 * Centralized API calls for the Interview Practice Partner.
 */

const API_BASE_URL = 'http://localhost:5000';

/**
 * Starts a new session with the backend.
 * Should be called when the app starts or reloads.
 */
export const startSession = async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/session/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`Failed to start session: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('[API] Session started:', data);
        return data;
    } catch (error) {
        console.error('[API] Error starting session:', error);
        throw error;
    }
};

/**
 * Sends a user message to the backend and returns the bot's reply.
 * 
 * @param {string} text - The user's message text.
 * @returns {Promise<Object>} - The backend response containing the 'reply' field.
 */
export const sendMessage = async (text) => {
    try {
        const response = await fetch(`${API_BASE_URL}/interaction/interact`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: text }),
        });

        if (!response.ok) {
            throw new Error(`Failed to send message: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('[API] Message sent, received:', data);
        return data;
    } catch (error) {
        console.error('[API] Error sending message:', error);
        throw error;
    }
};

/**
 * Deletes the current session.
 * Should be called when the user leaves or reloads the page.
 */
export const deleteSession = () => {
    const url = `${API_BASE_URL}/session/delete`;

    // Use sendBeacon if available for reliable delivery on unload
    if (navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify({})], { type: 'application/json' });
        navigator.sendBeacon(url, blob);
        console.log('[API] Session delete beacon sent');
    } else {
        // Fallback to fetch with keepalive
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            keepalive: true,
        }).catch(err => console.error('[API] Error deleting session:', err));
    }
};
