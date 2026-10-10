import React, { useEffect, useRef, useState } from 'react';

interface OrionVoiceOverlayProps {
  isOpen: boolean;
  onClose?: () => void;
  statusText?: string;
}

export const OrionVoiceOverlay: React.FC<OrionVoiceOverlayProps> = ({
  isOpen,
  onClose,
  statusText = 'Listening...'
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [isListening, setIsListening] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (!isOpen) {
      stopAudio();
      return;
    }

    startAudio();

    return () => {
      stopAudio();
    };
  }, [isOpen]);

  const startAudio = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioContextClass();
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128; // Small FFT for rapid bar response

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      audioCtxRef.current = audioCtx;
      analyserRef.current = analyser;
      setIsListening(true);

      drawVisualizer();
    } catch (err) {
      console.warn('Microphone access denied or unavailable, running fallback animation.', err);
      setIsListening(false);
      drawSimulatedVisualizer();
    }
  };

  const stopAudio = () => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop());
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      audioCtxRef.current.close();
    }
  };

  const drawVisualizer = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const analyser = analyserRef.current;
    if (!ctx || !analyser) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const render = () => {
      analyser.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const radius = 110; // Outer circle radius around the logo
      const numBars = 48;

      for (let i = 0; i < numBars; i++) {
        // Map dataArray values to bars
        const dataIndex = Math.floor((i / numBars) * bufferLength);
        const value = dataArray[dataIndex] || 0;
        const barHeight = (value / 255) * 45 + 4; // Height based on mic volume

        const angle = (i * 2 * Math.PI) / numBars;

        // Radial line points
        const xStart = centerX + Math.cos(angle) * radius;
        const yStart = centerY + Math.sin(angle) * radius;
        const xEnd = centerX + Math.cos(angle) * (radius + barHeight);
        const yEnd = centerY + Math.sin(angle) * (radius + barHeight);

        // Draw sound wave bar (CodeRED Red / Glowing White gradient)
        ctx.beginPath();
        ctx.moveTo(xStart, yStart);
        ctx.lineTo(xEnd, yEnd);
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.strokeStyle = i % 2 === 0 ? '#E31B23' : '#FFFFFF';
        ctx.shadowBlur = 12;
        ctx.shadowColor = '#E31B23';
        ctx.stroke();
      }

      animFrameRef.current = requestAnimationFrame(render);
    };

    render();
  };

  // Fallback idle wave if mic permission isn't granted yet
  const drawSimulatedVisualizer = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let step = 0;
    const render = () => {
      step += 0.05;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const radius = 110;
      const numBars = 48;

      for (let i = 0; i < numBars; i++) {
        const barHeight = Math.sin(step + i * 0.3) * 15 + 18;
        const angle = (i * 2 * Math.PI) / numBars;

        const xStart = centerX + Math.cos(angle) * radius;
        const yStart = centerY + Math.sin(angle) * radius;
        const xEnd = centerX + Math.cos(angle) * (radius + barHeight);
        const yEnd = centerY + Math.sin(angle) * (radius + barHeight);

        ctx.beginPath();
        ctx.moveTo(xStart, yStart);
        ctx.lineTo(xEnd, yEnd);
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.strokeStyle = i % 2 === 0 ? '#E31B23' : '#FFFFFF';
        ctx.shadowBlur = 10;
        ctx.shadowColor = '#E31B23';
        ctx.stroke();
      }

      animFrameRef.current = requestAnimationFrame(render);
    };

    render();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md transition-opacity duration-300">
      {/* Outer Glow & Semi-Transparent Glass Circle */}
      <div className="relative flex flex-col items-center justify-center w-80 h-80 rounded-full bg-slate-950/80 border border-red-500/30 shadow-[0_0_60px_rgba(227,27,35,0.35)] backdrop-blur-xl animate-in zoom-in-95 duration-200">
        
        {/* Dynamic Sound Wave Canvas Overlay */}
        <canvas
          ref={canvasRef}
          width={360}
          height={360}
          className="absolute inset-0 -top-5 -left-5 pointer-events-none z-0"
        />

        {/* Central Orion Branding */}
        <div className="relative z-10 flex flex-col items-center justify-center text-center select-none">
          {/* Constellation Star Graphic */}
          <div className="relative mb-2">
            <span className="text-3xl text-red-500 drop-shadow-[0_0_10px_#E31B23]">✦</span>
            <span className="absolute -top-1 -right-3 text-xs text-white/80 animate-ping">★</span>
          </div>

          {/* Orion Logo Header */}
          <div className="flex items-center space-x-1 tracking-[0.25em] font-extrabold text-2xl text-white drop-shadow-[0_2px_10px_rgba(255,255,255,0.4)]">
            <span>O R I O N</span>
          </div>

          {/* CodeRED Tag */}
          <div className="mt-1 px-2 py-0.5 rounded bg-red-600/80 text-[10px] uppercase tracking-widest text-white font-bold shadow-sm">
            CODERED
          </div>

          {/* Live Status Text */}
          <p className="mt-4 text-xs font-mono text-slate-300/80 animate-pulse">
            {statusText}
          </p>
        </div>

        {/* Optional Close Button */}
        {onClose && (
          <button
            onClick={onClose}
            className="absolute bottom-4 text-xs font-mono text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            [ESC to Close]
          </button>
        )}
      </div>
    </div>
  );
};