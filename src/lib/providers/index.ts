import { MusicProvider } from '@/types/music';
import { GequhaiProvider } from './impl/gequhai';
import { BodianProvider } from './impl/bodian';
import { QQProvider } from './impl/qq';
import { KugouProvider } from './impl/kugou';
import { QQMp3Provider } from './impl/qqmp3';
import { MiguProvider } from './impl/migu';
import { LivepooProvider } from './impl/livepoo';
import { JianbinProvider } from './impl/jianbin';
import { NeteaseOfficialProvider } from './impl/netease';

const providers: Record<string, MusicProvider> = {
  'netease': new NeteaseOfficialProvider(),
  qq: new QQProvider(),
  kugou: new KugouProvider(),
  gequhai: new GequhaiProvider(),
  bodian: new BodianProvider(),
  qqmp3: new QQMp3Provider(),
  migu: new MiguProvider(),
  livepoo: new LivepooProvider(),
  'jianbin-netease': new JianbinProvider('jianbin-netease', 'netease'),
  'jianbin-qq': new JianbinProvider('jianbin-qq', 'qq'),
  'jianbin-kugou': new JianbinProvider('jianbin-kugou', 'kugou'),
  'jianbin-kuwo': new JianbinProvider('jianbin-kuwo', 'kuwo'),
};

export function getProvider(name: string = 'netease'): MusicProvider {
  return providers[name] || providers['netease'];
}

export function getAllProviders(): MusicProvider[] {
  return Object.values(providers);
}
