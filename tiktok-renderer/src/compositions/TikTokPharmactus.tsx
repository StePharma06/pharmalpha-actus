import React from 'react';
import {AbsoluteFill, Audio, Sequence, Video, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {Subtitles} from '../components/Subtitles';

export const tiktokPharmactusSchema = z.object({
  clips: z.array(
    z.object({
      url: z.string(),
      durationInSeconds: z.number(),
    })
  ),
  voiceoverUrl: z.string(),
  musicUrl: z.string().optional(),
  words: z
    .array(
      z.object({
        word: z.string(),
        start: z.number(),
        end: z.number(),
      })
    )
    .optional(),
});

export type TikTokPharmactusProps = z.infer<typeof tiktokPharmactusSchema>;

export const TikTokPharmactus: React.FC<TikTokPharmactusProps> = ({
  clips,
  voiceoverUrl,
  musicUrl,
  words,
}) => {
  const {fps} = useVideoConfig();

  // Calcule le frame de démarrage de chaque clip
  let cumulativeFrames = 0;
  const clipsWithTiming = clips.map((clip) => {
    const from = cumulativeFrames;
    const durationInFrames = Math.round(clip.durationInSeconds * fps);
    cumulativeFrames += durationInFrames;
    return {...clip, from, durationInFrames};
  });

  // Convertit les timestamps (en secondes) en frames pour les sous-titres
  const captions = words
    ? groupWordsToCaptions(words, fps)
    : [];

  return (
    <AbsoluteFill className="bg-black">
      {/* Clips vidéo en séquence */}
      {clipsWithTiming.map((clip, i) => (
        <Sequence key={i} from={clip.from} durationInFrames={clip.durationInFrames}>
          <Video
            src={clip.url}
            muted
            style={{width: '100%', height: '100%', objectFit: 'cover'}}
          />
        </Sequence>
      ))}

      {/* Voix off ElevenLabs (continue sur toute la vidéo) */}
      <Audio src={voiceoverUrl} volume={1} />

      {/* Musique de fond (faible volume) */}
      {musicUrl ? <Audio src={musicUrl} volume={0.12} /> : null}

      {/* Sous-titres mot par mot */}
      {captions.length > 0 && <Subtitles captions={captions} style="tiktok" position={72} />}
    </AbsoluteFill>
  );
};

/**
 * Regroupe les mots ElevenLabs en chunks de 2-3 mots avec timing en frames.
 * Minimum 1s (30 frames) par chunk pour lisibilité.
 */
function groupWordsToCaptions(
  words: {word: string; start: number; end: number}[],
  fps: number
): {from: number; to: number; text: string}[] {
  if (words.length === 0) return [];

  const MIN_FRAMES = Math.round(1.0 * fps);
  const MAX_WORDS = 3;
  const MAX_CHARS = 22;

  // Clean: strip whitespace, skip empty
  const clean = words.filter((w) => w.word.trim().length > 0);
  if (clean.length === 0) return [];

  // Group by punctuation or max words
  const chunks: {word: string; start: number; end: number}[][] = [];
  let current: {word: string; start: number; end: number}[] = [];
  for (const w of clean) {
    current.push(w);
    const hasPunct = /[.!?,;:]/.test(w.word);
    const joined = current.map((c) => c.word).join(' ');
    if (current.length >= MAX_WORDS || hasPunct || joined.length > MAX_CHARS) {
      chunks.push(current);
      current = [];
    }
  }
  if (current.length > 0) {
    if (chunks.length > 0) {
      chunks[chunks.length - 1].push(...current);
    } else {
      chunks.push(current);
    }
  }

  const captions: {from: number; to: number; text: string}[] = [];
  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    let text = chunk.map((w) => w.word).join(' ').trim();
    text = text.replace(/^[,; ]+|[,; ]+$/g, '');
    if (!text) continue;

    const startFrame = Math.round(chunk[0].start * fps);
    let endFrame = Math.round(chunk[chunk.length - 1].end * fps);

    // Enforce min duration, extend to next chunk if possible
    if (endFrame - startFrame < MIN_FRAMES) {
      if (i + 1 < chunks.length) {
        const nextStart = Math.round(chunks[i + 1][0].start * fps);
        endFrame = Math.min(nextStart, startFrame + MIN_FRAMES);
      } else {
        endFrame = startFrame + MIN_FRAMES;
      }
    }

    captions.push({from: startFrame, to: endFrame, text});
  }

  return captions;
}
