#!/usr/bin/env node
/**
 * Render TikTok Pharm'Actus video via Remotion.
 *
 * Usage:
 *   node scripts/render.mjs --input=props.json --output=video.mp4
 *
 * props.json format:
 *   {
 *     "clips": [{"url": "...", "durationInSeconds": 5}, ...],
 *     "voiceoverUrl": "https://...",
 *     "musicUrl": "https://..." (optional),
 *     "words": [{"word": "...", "start": 0.12, "end": 0.45}, ...]
 *   }
 */

import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import {readFileSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = resolve(__dirname, '..');

// Parse args
const args = Object.fromEntries(
  process.argv.slice(2).map((arg) => {
    const [key, value] = arg.replace(/^--/, '').split('=');
    return [key, value];
  })
);

const inputPath = args.input || resolve(ROOT, 'props.json');
const outputPath = args.output || resolve(ROOT, 'out/video.mp4');

console.log('[render] input :', inputPath);
console.log('[render] output:', outputPath);

// Load props
const inputProps = JSON.parse(readFileSync(inputPath, 'utf-8'));
console.log(
  `[render] clips=${inputProps.clips?.length || 0}, words=${inputProps.words?.length || 0}`
);

// Bundle Remotion project
console.log('[render] bundling Remotion project...');
const bundled = await bundle({
  entryPoint: resolve(ROOT, 'src/index.ts'),
  webpackOverride: (config) => config,
});

// Select composition with inputProps (so calculateMetadata runs)
console.log('[render] selecting composition...');
const composition = await selectComposition({
  serveUrl: bundled,
  id: 'TikTokPharmactus',
  inputProps,
});

console.log(
  `[render] duration=${composition.durationInFrames} frames (${composition.durationInFrames / composition.fps}s)`
);

// Render
console.log('[render] rendering...');
await renderMedia({
  composition,
  serveUrl: bundled,
  codec: 'h264',
  outputLocation: outputPath,
  inputProps,
  chromiumOptions: {
    gl: 'swangle',
  },
});

console.log('[render] done :', outputPath);
