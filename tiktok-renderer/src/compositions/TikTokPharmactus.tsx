import React from 'react';
import {AbsoluteFill, Audio, Sequence, Video, useVideoConfig, spring, useCurrentFrame} from 'remotion';
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
  cta: z
    .object({
      voiceoverUrl: z.string(),
      durationInSeconds: z.number(),
      pauseBeforeSeconds: z.number().default(1.0),
      backgroundClipUrl: z.string().default(''),
    })
    .optional(),
});

export type TikTokPharmactusProps = z.infer<typeof tiktokPharmactusSchema>;

export const TikTokPharmactus: React.FC<TikTokPharmactusProps> = ({
  clips,
  voiceoverUrl,
  musicUrl,
  words,
  cta,
}) => {
  const {fps} = useVideoConfig();

  // Calcule le frame de démarrage de chaque clip story
  let cumulativeFrames = 0;
  const clipsWithTiming = clips.map((clip) => {
    const from = cumulativeFrames;
    const durationInFrames = Math.round(clip.durationInSeconds * fps);
    cumulativeFrames += durationInFrames;
    return {...clip, from, durationInFrames};
  });

  const storyEndFrame = cumulativeFrames;

  // CTA timing
  const ctaPauseFrames = cta ? Math.round(cta.pauseBeforeSeconds * fps) : 0;
  const ctaStartFrame = storyEndFrame + ctaPauseFrames;
  const ctaDurationFrames = cta ? Math.round(cta.durationInSeconds * fps) : 0;
  const ctaEndFrame = ctaStartFrame + ctaDurationFrames;

  // Story voiceover duration = min(last word end, storyEndFrame) to avoid bleeding into CTA
  const storyVoiceEndSeconds = words && words.length > 0 ? words[words.length - 1].end : 0;
  const voiceStoryDurationFrames = Math.min(
    Math.round(storyVoiceEndSeconds * fps),
    storyEndFrame
  );

  // CTA caption = texte fixe affiché pendant le CTA
  const ctaCaptions = cta
    ? [
        {
          from: ctaStartFrame,
          to: ctaEndFrame,
          text: "Abonne-toi pour continuer à découvrir d'autres secrets de la médecine.",
        },
      ]
    : [];

  return (
    <AbsoluteFill className="bg-black">
      {/* Clips vidéo story en séquence */}
      {clipsWithTiming.map((clip, i) => (
        <Sequence key={i} from={clip.from} durationInFrames={clip.durationInFrames}>
          <Video src={clip.url} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </Sequence>
      ))}

      {/* Voix off story — coupee a min(voix, clips) pour eviter superposition avec CTA */}
      <Sequence from={0} durationInFrames={voiceStoryDurationFrames}>
        <Audio src={voiceoverUrl} volume={1} />
      </Sequence>

      {/* Musique de fond (toute la durée sauf CTA) */}
      {musicUrl && (
        <Sequence from={0} durationInFrames={storyEndFrame}>
          <Audio src={musicUrl} volume={0.12} />
        </Sequence>
      )}

      {/* Sous-titres story — style moderne avec highlight mot par mot */}
      {words && words.length > 0 && (
        <Sequence from={0} durationInFrames={storyEndFrame}>
          <Subtitles words={words} style="modern" position={72} accentColor="#f97316" />
        </Sequence>
      )}

      {/* ──── SEGMENT CTA ──── */}
      {cta && (
        <>
          {/* Pendant la pause (1s), on garde le dernier clip visible mais figé */}
          <Sequence from={storyEndFrame} durationInFrames={ctaPauseFrames + ctaDurationFrames}>
            {cta.backgroundClipUrl ? (
              <AbsoluteFill>
                <Video
                  src={cta.backgroundClipUrl}
                  muted
                  style={{width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(0.35) blur(2px)'}}
                />
              </AbsoluteFill>
            ) : (
              <AbsoluteFill className="bg-black" />
            )}
          </Sequence>

          {/* Voix CTA après la pause */}
          <Sequence from={ctaStartFrame} durationInFrames={ctaDurationFrames}>
            <Audio src={cta.voiceoverUrl} volume={1} />
          </Sequence>

          {/* Overlay bouton "Abonne-toi" TikTok style + texte */}
          <Sequence from={ctaStartFrame} durationInFrames={ctaDurationFrames}>
            <AbonneToiOverlay />
          </Sequence>

          {/* Sous-titre CTA */}
          {ctaCaptions.length > 0 && <Subtitles captions={ctaCaptions} style="clean" position={82} />}
        </>
      )}
    </AbsoluteFill>
  );
};

/**
 * Overlay bouton "Abonne-toi" style TikTok (rouge + plus blanc).
 * Animation : scale in + pulse.
 */
const AbonneToiOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scaleIn = spring({frame, fps, config: {damping: 10}});
  const pulse = 1 + Math.sin((frame / fps) * Math.PI * 1.5) * 0.04;

  return (
    <AbsoluteFill className="flex items-center justify-center">
      <div style={{transform: `scale(${scaleIn * pulse})`}} className="flex flex-col items-center gap-8">
        {/* Avatar placeholder (cercle rouge avec +) */}
        <div
          style={{
            width: 240,
            height: 240,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #ff2d55, #ff0050)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 12px 40px rgba(255, 0, 80, 0.6)',
            border: '6px solid white',
            position: 'relative',
          }}
        >
          <span style={{color: 'white', fontSize: 140, fontWeight: 900, lineHeight: 1}}>+</span>
        </div>

        {/* Bouton Abonne-toi */}
        <div
          style={{
            background: '#ff0050',
            color: 'white',
            padding: '28px 72px',
            borderRadius: 16,
            fontSize: 68,
            fontWeight: 900,
            letterSpacing: '-0.01em',
            fontFamily: '"Oswald", sans-serif',
            textTransform: 'uppercase',
            boxShadow: '0 8px 28px rgba(0,0,0,0.5)',
          }}
        >
          ABONNE-TOI
        </div>
      </div>
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
