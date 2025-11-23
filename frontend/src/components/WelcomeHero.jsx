// src/components/WelcomeHero.jsx
import React from 'react';
import './WelcomeHero.css';

const WelcomeHero = ({ userName, isVisible = true }) => {
    const getGreeting = () => {
        const hour = new Date().getHours();
        if (hour < 12) return 'Good morning';
        if (hour < 18) return 'Good afternoon';
        return 'Good evening';
    };

    return (
        // toggle "exiting" class to animate out smoothly when isVisible becomes false
        <div className={`welcome-hero ${isVisible ? '' : 'exiting'}`} aria-hidden={!isVisible}>
            <h1 className="greeting-text">
                <span className="greeting-gradient">{getGreeting()}, {userName || 'Candidate'}.</span>
            </h1>
            <p className="sub-text">Ready to practice your interview skills?</p>
        </div>
    );
};

export default WelcomeHero;
