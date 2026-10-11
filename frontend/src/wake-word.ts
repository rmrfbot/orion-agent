export type WakeStatus = 'off' | 'starting' | 'listening' | 'capturing' | 'working' | 'error' | 'unavailable';
export type WakeSnapshot = { status: WakeStatus; notice: string };

export type RecognitionAlternative = { transcript: string };
export type RecognitionResult = ArrayLike<RecognitionAlternative> & { isFinal?: boolean };
export type RecognitionEvent = {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
};

export type SpeechRecognizer = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type Options = {
  createRecognizer: () => SpeechRecognizer | undefined;
  onCommand: (text: string) => Promise<boolean>;
  normalizeCommand: (text: string) => string;
};

export class WakeWordSession {
  private readonly options: Options;
  private readonly listeners = new Set<() => void>();
  private state: WakeSnapshot = { status: 'off', notice: '' };
  private active = false;
  private mode: 'wake' | 'command' = 'wake';
  private recognizer?: SpeechRecognizer;
  private restartTimer?: ReturnType<typeof setTimeout>;
  private commandTimer?: ReturnType<typeof setTimeout>;
  private commandParts: string[] = [];
  private wakeCommand = '';
  private awaitingCommand = false;

  constructor(options: Options) {
    this.options = options;
  }

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private update(state: WakeSnapshot) {
    this.state = state;
    this.listeners.forEach(listener => listener());
  }

  start() {
    if (this.active) return true;
    const recognizer = this.options.createRecognizer();
    if (!recognizer) {
      this.update({ status: 'unavailable', notice: 'Chrome speech recognition is unavailable. Use Push to talk.' });
      return false;
    }

    this.active = true;
    this.mode = 'wake';
    this.update({ status: 'starting', notice: '' });
    this.startRecognition(recognizer);
    return this.active;
  }

  private startRecognition(recognizer?: SpeechRecognizer) {
    if (!this.active) return;
    const current = recognizer ?? this.options.createRecognizer();
    if (!current) {
      this.active = false;
      this.update({ status: 'unavailable', notice: 'Chrome speech recognition is unavailable. Use Push to talk.' });
      return;
    }

    this.recognizer = current;
    current.lang = 'en-US';
    current.continuous = true;
    current.interimResults = true;
    current.onstart = () => {
      if (this.active) {
        this.update({
          status: this.mode === 'wake' ? 'listening' : 'capturing',
          notice: '',
        });
      }
    };
    current.onresult = event => this.handleResult(current, event);
    current.onerror = event => {
      if (!this.active) return;
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        this.fail('Chrome microphone or speech-recognition permission was denied. Allow it for this site, then try again.');
      } else if (event.error === 'network') {
        this.fail('Chrome speech recognition could not reach its recognition service. Use Push to talk or try again.');
      } else if (event.error !== 'no-speech' && event.error !== 'aborted') {
        this.fail(`Chrome speech recognition failed (${event.error}). Use Push to talk or try again.`);
      }
    };
    current.onend = () => {
      if (this.recognizer === current) this.recognizer = undefined;
      if (!this.active) return;
      if (this.mode === 'wake') {
        this.scheduleRestart();
      } else if (this.awaitingCommand) {
        this.awaitingCommand = false;
        this.update({ status: 'capturing', notice: 'Wake phrase heard. Say your command now.' });
        this.startRecognition();
      } else if (this.wakeCommand) {
        const command = this.wakeCommand;
        this.wakeCommand = '';
        void this.submitCommand(command);
      } else if (this.commandParts.length) {
        void this.submitCommand(this.commandParts.join(' '));
      } else {
        this.finishEmptyCommand();
      }
    };

    try {
      current.start();
    } catch (error) {
      this.fail(error instanceof Error
        ? `Could not start Chrome speech recognition: ${error.message}`
        : 'Could not start Chrome speech recognition. Use Push to talk.');
    }
  }

  private handleResult(current: SpeechRecognizer, event: RecognitionEvent) {
    if (!this.active || this.recognizer !== current) return;

    for (let index = event.resultIndex; index < event.results.length; index++) {
      const result = event.results[index];
      const transcript = result[0]?.transcript?.trim() ?? '';
      if (!transcript || result.isFinal === false) continue;

      if (this.mode === 'wake') {
        const match = transcript.match(/\bhey[\s,.:!-]*orion\b([\s\S]*)/i);
        if (!match) continue;
        const command = match[1].trim().replace(/^[\s,.:!-]+/, '');
        if (command) {
          this.mode = 'command';
          this.wakeCommand = command;
        } else {
          this.mode = 'command';
          this.commandParts = [];
          this.awaitingCommand = true;
          this.update({ status: 'capturing', notice: 'Wake phrase heard. Say your command now.' });
          this.commandTimer = setTimeout(() => {
            this.commandTimer = undefined;
            this.recognizer?.stop();
          }, 8000);
        }
        current.stop();
        return;
      }

      this.commandParts.push(transcript);
      if (this.commandTimer) clearTimeout(this.commandTimer);
      this.commandTimer = setTimeout(() => {
        this.commandTimer = undefined;
        if (this.recognizer === current) current.stop();
      }, 1000);
    }
  }

  private async submitCommand(raw: string) {
    if (this.commandTimer) clearTimeout(this.commandTimer);
    this.commandTimer = undefined;
    const command = this.options.normalizeCommand(raw);
    this.commandParts = [];
    if (!command) {
      this.finishEmptyCommand();
      return;
    }
    this.update({ status: 'working', notice: '' });
    try {
      const accepted = await this.options.onCommand(command);
      if (!this.active) return;
      if (accepted) {
        this.mode = 'wake';
        this.update({ status: 'starting', notice: '' });
        this.scheduleRestart();
      } else {
        this.fail('The command was not submitted. Check that ORION is connected and not already running a task.');
      }
    } catch (error) {
      if (this.active) this.fail(error instanceof Error ? error.message : 'The voice command could not be submitted.');
    }
  }

  private finishEmptyCommand() {
    if (this.commandTimer) clearTimeout(this.commandTimer);
    this.commandTimer = undefined;
    this.commandParts = [];
    this.mode = 'wake';
    this.update({ status: 'starting', notice: 'No command detected. Listening for “Hey Orion” again.' });
    this.scheduleRestart();
  }

  private fail(notice: string) {
    this.active = false;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    if (this.commandTimer) clearTimeout(this.commandTimer);
    this.restartTimer = undefined;
    this.commandTimer = undefined;
    const recognizer = this.recognizer;
    this.recognizer = undefined;
    if (recognizer) {
      recognizer.onstart = null;
      recognizer.onresult = null;
      recognizer.onerror = null;
      recognizer.onend = null;
      recognizer.abort();
    }
    this.update({ status: 'error', notice });
  }

  private scheduleRestart() {
    if (!this.active) return;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    this.restartTimer = setTimeout(() => {
      this.restartTimer = undefined;
      this.startRecognition();
    }, 300);
  }

  stop() {
    this.active = false;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    if (this.commandTimer) clearTimeout(this.commandTimer);
    this.restartTimer = undefined;
    this.commandTimer = undefined;
    const recognizer = this.recognizer;
    this.recognizer = undefined;
    if (recognizer) {
      recognizer.onstart = null;
      recognizer.onresult = null;
      recognizer.onerror = null;
      recognizer.onend = null;
      recognizer.abort();
    }
    this.commandParts = [];
    this.wakeCommand = '';
    this.awaitingCommand = false;
    this.update({ status: 'off', notice: '' });
  }

  dispose() {
    this.stop();
    this.listeners.clear();
  }
}
