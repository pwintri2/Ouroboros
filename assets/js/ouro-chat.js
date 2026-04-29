/**
 * Ouroboros AI Chat Widget - Multilingual & Content Aware
 * Robust version with dynamic path detection.
 */
(function() {
    // 1. Dynamic Path Detection
    const scriptTag = document.querySelector('script[src*="ouro-chat.js"]');
    const scriptSrc = scriptTag ? scriptTag.getAttribute('src') : '';
    const basePath = scriptSrc.replace('assets/js/ouro-chat.js', '');
    const CHAT_ENDPOINT = basePath + 'api/chat-handler.php';
    
    // Detect Language
    const htmlLang = document.documentElement.lang || 'en';
    const pathParts = window.location.pathname.split('/').filter(Boolean);
    // If hosted at domain.com/Ouroboros/, pathParts[0] might be 'Ouroboros'
    // Let's check the last parts
    const lastPart = pathParts[pathParts.length - 2]; 
    const supportedLangs = ['nl', 'fr', 'de', 'es'];
    const currentLang = supportedLangs.includes(lastPart) ? lastPart : (supportedLangs.includes(htmlLang) ? htmlLang : 'en');

    // Language Strings
    const i18n = {
        en: { welcome: "Hello. I am Ouroboros. How can I help you today?", placeholder: "Type your message...", thinking: "Ouroboros is thinking...", error: "Sorry, something went wrong.", connectionError: "I cannot connect right now. Stay calm." },
        nl: { welcome: "Hallo. Ik ben Ouroboros. Hoe kan ik je vandaag helpen?", placeholder: "Typ je bericht...", thinking: "Ouroboros denkt na...", error: "Excuses, er ging iets mis.", connectionError: "Ik kan geen verbinding maken. Rustig aan." },
        fr: { welcome: "Bonjour. Je suis Ouroboros. Comment puis-je vous aider aujourd'hui ?", placeholder: "Tapez votre message...", thinking: "Ouroboros réfléchit...", error: "Désolé, une erreur est survenue.", connectionError: "Connexion impossible pour le moment. Restez calme." },
        de: { welcome: "Hallo. Ich bin Ouroboros. Wie kann ich Ihnen heute helfen?", placeholder: "Schreiben Sie eine Nachricht...", thinking: "Ouroboros denkt nach...", error: "Entschuldigung, etwas ist schief gelaufen.", connectionError: "Verbindung zurzeit nicht möglich. Bleiben Sie ruhig." },
        es: { welcome: "Hola. Soy Ouroboros. ¿Cómo puedo ayudarte hoy?", placeholder: "Escribe tu mensaje...", thinking: "Ouroboros está pensando...", error: "Lo siento, algo salió mal.", connectionError: "No puedo conectar en este momento. Mantén la calma." }
    };

    const t = i18n[currentLang] || i18n.en;

    // UI Elements HTML
    const chatHTML = `
        <div id="ouro-chat-container">
            <div id="ouro-chat-trigger" title="Chat with Ouroboros">
                <svg viewBox="0 0 24 24"><path d="M12,2C6.47,2 2,6.47 2,12C2,17.53 6.47,22 12,22C17.53,22 22,17.53 22,12C22,6.47 17.53,2 12,2M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M13,7H11V11H7V13H11V17H13V13H17V11H13V7Z"/></svg>
            </div>
            <div id="ouro-chat-window">
                <div class="ouro-chat-header">
                    <h3>Ouroboros AI</h3>
                    <span class="ouro-close-btn">&times;</span>
                </div>
                <div id="ouro-chat-messages">
                    <div class="ouro-message bot">${t.welcome}</div>
                </div>
                <div class="ouro-chat-input-area">
                    <input type="text" id="ouro-chat-input" placeholder="${t.placeholder}" autocomplete="off">
                    <button id="ouro-send-btn">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="white"><path d="M2,21L23,12L2,3V10L17,12L2,14V21Z"/></svg>
                    </button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', chatHTML);

    const trigger = document.getElementById('ouro-chat-trigger');
    const windowEl = document.getElementById('ouro-chat-window');
    const closeBtn = document.querySelector('.ouro-close-btn');
    const input = document.getElementById('ouro-chat-input');
    const sendBtn = document.getElementById('ouro-send-btn');
    const messagesContainer = document.getElementById('ouro-chat-messages');

    trigger.addEventListener('click', () => {
        windowEl.classList.toggle('active');
        if (windowEl.classList.contains('active')) input.focus();
    });

    closeBtn.addEventListener('click', () => windowEl.classList.remove('active'));

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        appendMessage(text, 'user');
        input.value = '';
        
        const typingId = showTyping();
        const context = `Page: ${document.title}. Content Summary: ${document.querySelector('meta[name="description"]')?.content || ""}`;

        try {
            const response = await fetch(CHAT_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message: text, 
                    lang: currentLang,
                    context: context
                })
            });

            const data = await response.json();
            removeTyping(typingId);

            if (data.reply) {
                appendMessage(data.reply, 'bot');
            } else {
                appendMessage(t.error, 'bot');
            }
        } catch (error) {
            removeTyping(typingId);
            appendMessage(t.connectionError, 'bot');
        }
    }

    function appendMessage(text, side) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `ouro-message ${side}`;
        msgDiv.textContent = text;
        messagesContainer.appendChild(msgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function showTyping() {
        const id = 'typing-' + Date.now();
        const typingDiv = document.createElement('div');
        typingDiv.id = id;
        typingDiv.className = 'typing-indicator';
        typingDiv.textContent = t.thinking;
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        return id;
    }

    function removeTyping(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
})();
