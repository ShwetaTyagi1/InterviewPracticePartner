// src/App.jsx
import React, { useState, useRef, useEffect } from 'react';
import WelcomeHero from './components/WelcomeHero';
import ChatInput from './components/ChatInput';
import NameDialog from './components/NameDialog';
import './App.css';

function App() {
  const [userName, setUserName] = useState(null);




  // messages state (very small message model)
  const [messages, setMessages] = useState([]);
  const messagesRef = useRef(null);
  useEffect(() => {
    const el = messagesRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
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

    // clear any existing timers
    if (timerRef.current) clearTimeout(timerRef.current);
    if (unmountWelcomeTimeoutRef.current) clearTimeout(unmountWelcomeTimeoutRef.current);

    // Start the 10s flow AFTER user presses Continue
    timerRef.current = setTimeout(() => {
      // kick off fade animation by toggling a class (we keep element in DOM briefly for animation)
      setWelcomeVisible(false);

      // pin the chat input (this will apply pinned class with smooth transition)
      setChatPinned(true);

      // show typing indicator for ~800ms then push bot message
      setBotTyping(true);
      setTimeout(() => {
        setBotTyping(false);

        const introText = `Hey ${name}! I'm your personal interview practice assistant.\nI’ll help you strengthen your concepts and prepare confidently across OOPS, OS, DBMS, CN. Shall we get started?`;
        const botMessage = {
          id: `bot_${Date.now()}`,
          role: 'bot',
          text: introText,
          createdAt: new Date().toISOString()
        };
        setMessages((m) => [...m, botMessage]);
      }, 800); // typing duration
    }, 2000); // 2s

    // safety: unmount welcome after animation ends (keep small delay to let transition finish)
    unmountWelcomeTimeoutRef.current = setTimeout(() => {
      // keep welcomeVisible false; if you want to unmount entirely you can, but we already set it to false
      // no-op here; this ref exists for cleanup if needed
    }, 11000);
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
            <WelcomeHero userName={userName} />
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
        <ChatInput isPinned={chatPinned} onSend={(text) => {
          const userMsg = { id: `user_${Date.now()}`, role: 'user', text, createdAt: new Date().toISOString() };
          setMessages((m) => [...m, userMsg]);

          // TODO: send to backend here
          console.log('USER SEND (TODO: send to backend):', text);
        }} />
      </main>
    </div>
  );
}

export default App;
