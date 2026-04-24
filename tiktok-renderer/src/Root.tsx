import React from 'react';
import {Composition} from 'remotion';
import './styles.css';
import {TikTokPharmactus, tiktokPharmactusSchema} from './compositions/TikTokPharmactus';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TikTokPharmactus"
      component={TikTokPharmactus}
      durationInFrames={30 * 60} // 60s default, overridden at render via calculateMetadata
      fps={30}
      width={1080}
      height={1920}
      schema={tiktokPharmactusSchema}
      calculateMetadata={({props}) => {
        const storySeconds = props.clips.reduce((sum, c) => sum + c.durationInSeconds, 0);
        const ctaSeconds = props.cta
          ? props.cta.pauseBeforeSeconds + props.cta.durationInSeconds
          : 0;
        const total = storySeconds + ctaSeconds;
        return {
          durationInFrames: Math.max(30, Math.round(total * 30)),
        };
      }}
      defaultProps={{
        clips: [
          {url: 'https://example.com/placeholder.mp4', durationInSeconds: 5},
        ],
        voiceoverUrl: 'https://example.com/voice.mp3',
        musicUrl: undefined,
        words: [],
      }}
    />
  );
};
