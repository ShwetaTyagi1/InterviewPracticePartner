import React, { useState } from 'react';
import WelcomeHero from './components/WelcomeHero';
import ChatInput from './components/ChatInput';
import NameDialog from './components/NameDialog';
import './App.css';

function App() {
  const [userName, setUserName] = useState(null);

  const handleNameSubmit = (name) => {
    setUserName(name);
  };

  return (
    <div className="app-container">
      {!userName && <NameDialog onNameSubmit={handleNameSubmit} />}

      <header className="app-header">
        <div className="logo">PrepPanda</div>
        {/* Add user profile or other header items here */}
      </header>

      <main className="main-content">
        <div className="content-wrapper">
          <WelcomeHero userName={userName} />
          <ChatInput />
        </div>
      </main>
    </div>
  );
}

export default App;
