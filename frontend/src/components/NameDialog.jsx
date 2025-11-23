import React, { useState } from 'react';
import './NameDialog.css';

const NameDialog = ({ onNameSubmit }) => {
    const [name, setName] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        if (name.trim()) {
            onNameSubmit(name.trim());
        }
    };

    return (
        <div className="dialog-overlay">
            <div className="dialog-box">
                <h2 className="dialog-title">Welcome to PrepPanda!</h2>
                <p className="dialog-subtitle">Let's get started with your interview practice</p>

                <form onSubmit={handleSubmit}>
                    <input
                        type="text"
                        className="name-input"
                        placeholder="Enter your name"
                        //value={name}
                        onChange={(e) => {
                            const value = e.target.value;
                            if (/^[A-Za-z\s]*$/.test(value)) {
                                setName(value);
                            }

                        }}
                        autoFocus
                    />
                    <button type="submit" className="submit-button" disabled={!name.trim()}>
                        Continue
                    </button>
                </form>
            </div>
        </div>
    );
};

export default NameDialog;
