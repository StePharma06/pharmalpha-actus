import {Config} from '@remotion/cli/config';
import {enableTailwind} from '@remotion/tailwind';

Config.overrideWebpackConfig((currentConfiguration) => {
  return enableTailwind(currentConfiguration);
});

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
Config.setConcurrency(2);
