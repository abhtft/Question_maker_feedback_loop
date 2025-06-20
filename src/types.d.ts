interface Window {
  SpeechRecognition: any;
  webkitSpeechRecognition: any;
}

interface SpeechRecognitionEvent {
  results: {
    [key: number]: {
      [key: number]: {
        transcript: string;
      };
    };
  };
  error: string;
} 