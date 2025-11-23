import React, { useState } from 'react';
import { Mic, Send, Image as ImageIcon, Upload } from 'lucide-react';
import './ChatInput.css';

const ChatInput = () => {
    const [inputText, setInputText] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        if (inputText.trim()) {
            console.log('Sending:', inputText);
            setInputText('');
        }
    };

    return (
        <div className="chat-input-container">
            <form className="chat-input-wrapper" onSubmit={handleSubmit}>
                <div className="input-actions-left">
                    <button type="button" className="icon-button" title="Upload File">
                        <div className="icon-circle">
                            <Upload size={20} />
                        </div>
                    </button>
                </div>

                <input
                    type="text"
                    className="chat-text-input"
                    placeholder="Type your answer or ask a question..."
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                />

                <div className="input-actions-right">
                    <button type="button" className="icon-button" title="Use Microphone">
                        <Mic size={20} />
                    </button>
                    {inputText && (
                        <button type="submit" className="icon-button send-button" title="Send">
                            <Send size={20} />
                        </button>
                    )}
                </div>
            </form>
        </div>
    );
};

export default ChatInput;
