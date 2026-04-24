import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';

export type Caption = {
  from: number; // frame
  to: number;   // frame
  text: string;
};

export type Word = {
  word: string;
  start: number; // seconds
  end: number;   // seconds
};

export type SubtitleStyle = 'tiktok' | 'modern' | 'clean';

type Props = {
  captions?: Caption[];
  words?: Word[];             // pour style="modern" avec highlight mot par mot
  style?: SubtitleStyle;
  position?: number;          // % from top
  accentColor?: string;       // pour le mot highlighted
};

/**
 * Subtitles :
 *  - style="tiktok" : chunks de 3 mots, fond blanc sur noir, stroke
 *  - style="modern" : highlight mot actuel (orange), fond arrondi semi-transparent
 *    Style viral TikTok 2026 — requiert words (pas captions)
 */
export const Subtitles: React.FC<Props> = ({
  captions,
  words,
  style = 'modern',
  position = 70,
  accentColor = '#f97316',
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const currentTime = frame / fps;

  // Style "modern" avec highlight mot par mot
  if (style === 'modern' && words && words.length > 0) {
    // Trouve l'index du mot courant (ou le dernier passé)
    let currentIdx = -1;
    for (let i = 0; i < words.length; i++) {
      if (currentTime >= words[i].start && currentTime < words[i].end) {
        currentIdx = i;
        break;
      }
    }
    // Si on est en transition (entre deux mots), on garde le mot précédent actif
    if (currentIdx === -1) {
      for (let i = words.length - 1; i >= 0; i--) {
        if (currentTime >= words[i].end) {
          currentIdx = i;
          break;
        }
      }
    }
    if (currentIdx === -1) return null;

    // Regroupe par chunks de 3 mots (alignés sur le mot courant)
    const CHUNK_SIZE = 3;
    const chunkStart = Math.floor(currentIdx / CHUNK_SIZE) * CHUNK_SIZE;
    const chunk = words.slice(chunkStart, chunkStart + CHUNK_SIZE);
    if (chunk.length === 0) return null;

    return (
      <div
        style={{
          position: 'absolute',
          top: `${position}%`,
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '88%',
          textAlign: 'center',
          fontSize: 78,
          fontWeight: 900,
          letterSpacing: '-0.02em',
          lineHeight: 1.15,
          fontFamily: '"Inter", "SF Pro Display", sans-serif',
          color: '#ffffff',
          padding: '20px 36px',
          background: 'rgba(0, 0, 0, 0.78)',
          borderRadius: 22,
          boxShadow: '0 8px 28px rgba(0,0,0,0.4)',
          textShadow: '0 2px 8px rgba(0,0,0,0.6)',
          display: 'inline-block',
          maxWidth: '88%',
        }}
      >
        {chunk.map((w, i) => {
          const globalIdx = chunkStart + i;
          const isActive = globalIdx === currentIdx;
          const cleanWord = w.word.replace(/^[,; ]+|[,; ]+$/g, '');
          return (
            <span
              key={i}
              style={{
                color: isActive ? accentColor : '#ffffff',
                marginRight: 14,
                display: 'inline-block',
                transform: isActive ? 'scale(1.08)' : 'scale(1)',
                transition: 'none',
              }}
            >
              {cleanWord}
            </span>
          );
        })}
      </div>
    );
  }

  // Style classique avec captions
  if (!captions || captions.length === 0) return null;
  const active = captions.find((c) => frame >= c.from && frame < c.to);
  if (!active) return null;

  if (style === 'tiktok') {
    return (
      <div
        style={{
          position: 'absolute',
          top: `${position}%`,
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '88%',
          textAlign: 'center',
          fontSize: 76,
          fontWeight: 900,
          color: '#ffffff',
          letterSpacing: '-0.01em',
          lineHeight: 1.1,
          fontFamily: '"Oswald", "Inter", sans-serif',
          WebkitTextStroke: '4px black',
          textShadow: '0 4px 16px rgba(0,0,0,0.95), 0 0 8px rgba(0,0,0,0.8)',
          textTransform: 'uppercase',
        }}
      >
        {active.text}
      </div>
    );
  }

  // style="clean"
  return (
    <div
      style={{
        position: 'absolute',
        top: `${position}%`,
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '85%',
        textAlign: 'center',
        fontSize: 48,
        fontWeight: 700,
        color: '#ffffff',
        fontFamily: '"Inter", sans-serif',
        background: 'rgba(0,0,0,0.6)',
        padding: '14px 24px',
        borderRadius: 14,
      }}
    >
      {active.text}
    </div>
  );
};
