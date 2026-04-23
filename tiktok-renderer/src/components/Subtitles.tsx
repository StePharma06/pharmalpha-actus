import React from 'react';
import {useCurrentFrame} from 'remotion';

export type Caption = {
  from: number;
  to: number;
  text: string;
};

export type SubtitleStyle = 'tiktok' | 'clean';

type Props = {
  captions: Caption[];
  style?: SubtitleStyle;
  position?: number; // % from top
};

const STYLE_PRESETS = {
  tiktok: {
    fontSize: 76,
    fontWeight: 900,
    textColor: '#FFFFFF',
    stroke: '4px black',
    letterSpacing: '-0.01em',
    uppercase: true,
    maxWidth: '88%',
  },
  clean: {
    fontSize: 40,
    fontWeight: 700,
    textColor: '#FFFFFF',
    stroke: '2px black',
    letterSpacing: '0em',
    uppercase: false,
    maxWidth: '85%',
  },
};

export const Subtitles: React.FC<Props> = ({captions, style = 'tiktok', position = 72}) => {
  const frame = useCurrentFrame();
  const preset = STYLE_PRESETS[style];

  const active = captions.find((c) => frame >= c.from && frame < c.to);
  if (!active) return null;

  const text = preset.uppercase ? active.text.toUpperCase() : active.text;

  return (
    <div
      style={{
        position: 'absolute',
        top: `${position}%`,
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: preset.maxWidth,
        textAlign: 'center',
        fontSize: preset.fontSize,
        fontWeight: preset.fontWeight,
        color: preset.textColor,
        letterSpacing: preset.letterSpacing,
        lineHeight: 1.1,
        fontFamily: '"Oswald", "Inter", sans-serif',
        WebkitTextStroke: preset.stroke,
        textShadow: '0 4px 16px rgba(0,0,0,0.95), 0 0 8px rgba(0,0,0,0.8)',
      }}
    >
      {text}
    </div>
  );
};
