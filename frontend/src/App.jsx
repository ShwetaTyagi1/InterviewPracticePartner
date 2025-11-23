// src/App.jsx
import React, { useState, useRef, useEffect } from 'react';
import WelcomeHero from './components/WelcomeHero';
import ChatInput from './components/ChatInput';
import NameDialog from './components/NameDialog';
import './App.css';

import { startSession, sendMessage } from './api/api';

function App() {
  const [userName, setUserName] = useState(null);

  // Start session on mount
  useEffect(() => {
    startSession().catch(err => console.error("Session start failed", err));
  }, []);

  // messages state (very small message model)
  const [messages, setMessages] = useState([]);
  const messagesRef = useRef(null);
  useEffect(() => {
    const el = messagesRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

  // debug: log the messages container geometry when messages change
  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    // log heights so we can verify the container has nonzero height and scrollable content
    console.log('[MSG DEBUG] clientHeight:', el.clientHeight, 'scrollHeight:', el.scrollHeight, 'scrollTop:', el.scrollTop);
  }, [messages]);

  const [welcomeVisible, setWelcomeVisible] = useState(true);
  const [chatPinned, setChatPinned] = useState(false);
  const [botTyping, setBotTyping] = useState(false);

  const timerRef = useRef(null);
  const unmountWelcomeTimeoutRef = useRef(null);

  const handleNameSubmit = (name) => {
    setUserName(name);
    // ensure welcome shows initially
    setWelcomeVisible(true);
  };

  const handleStartSession = () => {
    // kick off fade animation by toggling a class (we keep element in DOM briefly for animation)
    setWelcomeVisible(false);

    // pin the chat input (this will apply pinned class with smooth transition)
    setChatPinned(true);

    // show typing indicator for ~800ms then push bot message
    setBotTyping(true);
    setTimeout(() => {
      setBotTyping(false);

      const introText = `Hey ${userName}! I'm your personal interview practice assistant.\nI’ll help you strengthen your concepts and prepare confidently across OOPS, OS, DBMS, and CN. Shall we get started?`;
      const botMessage = {
        id: `bot_${Date.now()}`,
        role: 'bot',
        text: introText,
        createdAt: new Date().toISOString()
      };
      setMessages((m) => [...m, botMessage]);
    }, 1500); // typing duration
  };

  const handleSendMessage = async (text) => {
    if (!text.trim()) return;

    // 1. Add user message immediately
    const userMsg = {
      id: `user_${Date.now()}`,
      role: 'user',
      text,
      createdAt: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMsg]);

    // 2. Show typing indicator
    setBotTyping(true);

    try {
      // 3. Call backend API
      const data = await sendMessage(text);

      // 4. Update state with bot response
      setBotTyping(false);
      const botMsg = {
        id: `bot_${Date.now()}`,
        role: 'bot',
        text: data.reply,
        createdAt: new Date().toISOString()
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (error) {
      console.error("Failed to get response:", error);
      setBotTyping(false);
      // Optional: Add error message to chat
      const errorMsg = {
        id: `bot_err_${Date.now()}`,
        role: 'bot',
        text: "Sorry, I'm having trouble connecting to the server right now.",
        createdAt: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errorMsg]);
    }
  };

  // cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (unmountWelcomeTimeoutRef.current) clearTimeout(unmountWelcomeTimeoutRef.current);
    };
  }, []);

  return (
    <div className="app-container">
      {!userName && <NameDialog onNameSubmit={handleNameSubmit} />}

      <main className="main-content">
        {/* Render WelcomeHero only while visible. Once false we unmount it. */}
        {welcomeVisible && (
          <div className="content-wrapper">
            <WelcomeHero userName={userName} onStart={handleStartSession} />
            {/* While welcome is visible we keep the "regular" messages container below the hero */}
            <div ref={messagesRef} className="messages-container" aria-live="polite">
              {messages.map((msg) => (
                <div key={msg.id} className={`message-bubble ${msg.role === 'bot' ? 'bot' : 'user'}`}>
                  <div className="message-text" style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
                </div>
              ))}
              {botTyping && (
                <div className="message-bubble bot typing">
                  <div className="message-text">typing...</div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* When welcome is gone, render messages container at top-level inside main, fullscreen mode */}
        {!welcomeVisible && (
          <div className="messages-container fullscreen" ref={messagesRef} aria-live="polite">
            {messages.map((msg) => (
              <div key={msg.id} className={`message-bubble ${msg.role === 'bot' ? 'bot' : 'user'}`}>
                <div className="message-text" style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
              </div>
            ))}
            {botTyping && (
              <div className="message-bubble bot typing">
                <div className="message-text">typing...</div>
              </div>
            )}
          </div>
        )}

        {/* ChatInput stays rendered as before (pinned logic still works) */}
        {/* ChatInput stays rendered as before (pinned logic still works) */}
        {chatPinned && (
          <ChatInput isPinned={chatPinned} onSend={handleSendMessage} />
        )}
      </main>
    </div>
  );
}

export default App;
