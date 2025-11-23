// src/components/WelcomeHero.jsx
import React from 'react';
import './WelcomeHero.css';

const WelcomeHero = ({ userName, onStart }) => {
    const getGreeting = () => {
        const hour = new Date().getHours();
        if (hour < 12) return 'Good morning';
        if (hour < 18) return 'Good afternoon';
        return 'Good evening';
    };

    return (
        <div className="welcome-hero">
            <h1 className="greeting-text">
                <span className="greeting-gradient">
                    {getGreeting()}, {userName || 'Candidate'}!
                </span>
            </h1>
            <p className="sub-text">Ready to ace your interviews?</p>

            <div className="hero-description">
                <p>
                    IntervueX is your personal interview assistant. We help you strengthen your CS fundamentals by asking interview-style questions from OOP, OS, DBMS, and CN.
                    We provide adaptive follow-ups along with detailed feedback and areas of improvement, so you walk into your next interview confident and fully prepared.
                </p>
                <p className="closing-text">All the best!</p>
            </div>

            <button className="get-started-btn" onClick={onStart}>
                Get Started
            </button>
        </div>
    );
};

export default WelcomeHero;
