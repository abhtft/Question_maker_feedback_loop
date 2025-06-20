class VoiceInput {
    constructor() {
        this.recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        this.recognition.continuous = false;
        this.recognition.lang = 'en-US';
        this.currentField = null;
        this.setupRecognition();
        this.setupButtons();
    }

    setupRecognition() {
        this.recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            if (this.currentField) {
                document.getElementById(this.currentField).value = transcript;
                this.stopListening();
            }
        };

        this.recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            this.stopListening();
        };
    }

    setupButtons() {
        document.querySelectorAll('.voice-btn').forEach(button => {
            button.addEventListener('click', () => {
                this.currentField = button.dataset.field;
                this.startListening(button);
            });
        });
    }

    startListening(button) {
        this.stopListening();
        button.classList.add('listening');
        this.recognition.start();
    }

    stopListening() {
        this.recognition.stop();
        document.querySelectorAll('.voice-btn').forEach(btn => {
            btn.classList.remove('listening');
        });
    }
} 