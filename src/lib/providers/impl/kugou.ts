import axios from 'axios';
import { Agent } from 'https';
import { MusicItem, MusicProvider, PlayInfo } from '@/types/music';
import { validateAudioLink } from '@/lib/providers/audio-link';

const SEARCH_API_URL = 'https://songsearch.kugou.com/song_search_v2';
const CGG_API_URL = 'https://music-api2.cenguigui.cn/';
const BAKA_API_URL = 'https://api.baka.plus/meting/';
const SVIP90_BASE_URL = 'https://music.90svip.cn/';
const HAITANG_API_URLS = [
  'https://musicapi.haitangw.net/kgqq/kg.php',
  'https://music.haitangw.cc/kgqq/kg.php',
];
const REQUEST_TIMEOUT = 15000;
const BAKA_HTTPS_AGENT = new Agent({ rejectUnauthorized: false });

const SEARCH_HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
};

type KugouSearchItem = {
  FileHash?: string;
  hash?: string;
  SongName?: string;
  songname?: string;
  FileName?: string;
  filename?: string;
  SingerName?: string;
  singername?: string;
  AlbumName?: string;
  album_name?: string;
  Duration?: number;
  duration?: number;
  timelen?: number;
  Image?: string;
  cover_url?: string;
  trans_param?: {
    union_cover?: string;
  };
};

type KugouSearchResponse = {
  data?: {
    lists?: KugouSearchItem[];
  };
};

export type KugouLyricData = {
  songid: string;
  provider: 'kugou';
  lines: Array<{ time: number; text: string }>;
  lrc: string;
};

type KugouExtra = {
  selectedParser?: KugouParser;
  selectedFormat?: string;
  cover?: string;
};

type KugouParser = '90svip' | 'baka' | 'cenguigui' | 'haitang';

const KUGOU_DOWNLOAD_OPTIONS = [
  { value: '90svip', label: '90svip 默认', quality: '320k/mp3', format: 'mp3' },
  { value: 'baka', label: 'Baka 备用', quality: 'lossless', format: 'flac' },
  { value: 'cenguigui', label: '尘归归备用', quality: 'mixed', format: 'mp3' },
  { value: 'haitang', label: '海棠备用', quality: 'mixed', format: 'mp3' },
];

function extractExt(url: string, fallback = 'mp3') {
  const clean = url.split('?')[0];
  const parts = clean.split('.');
  return parts.length > 1 ? parts[parts.length - 1] : fallback;
}

function normalizeCover(value?: string) {
  if (!value) return undefined;
  return value.includes('{size}') ? value.replace('{size}', '400') : value;
}

function formatDuration(seconds?: number) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return undefined;
  const normalized = seconds > 10000 ? Math.floor(seconds / 1000) : Math.floor(seconds);
  return `${String(Math.floor(normalized / 60)).padStart(2, '0')}:${String(normalized % 60).padStart(2, '0')}`;
}

function parseLyricLines(lyric: string) {
  const lines: Array<{ time: number; text: string }> = [];
  const timePattern = /\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\]/g;

  for (const rawLine of lyric.split(/\r?\n/)) {
    const matches = [...rawLine.matchAll(timePattern)];
    if (matches.length === 0) continue;
    const text = rawLine.replace(timePattern, '').trim();
    for (const match of matches) {
      const minutes = Number(match[1]);
      const seconds = Number(match[2]);
      const fraction = match[3] ? Number(match[3].padEnd(3, '0').slice(0, 3)) / 1000 : 0;
      lines.push({ time: minutes * 60 + seconds + fraction, text });
    }
  }

  return lines
    .filter((line) => line.text)
    .sort((a, b) => a.time - b.time);
}

function cleanLyric(value: string) {
  return value
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function getExtraValue(extra: unknown, key: string) {
  const payload = extra as Record<string, unknown> | undefined;
  const value = payload?.[key];
  return typeof value === 'string' || typeof value === 'number' ? value : undefined;
}

function parseSessionCookie(setCookie?: string[] | string) {
  const values = Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : [];
  for (const value of values) {
    const match = value.match(/(?:^|[,;]\s*)PHPSESSID=([^;,\s]+)/i);
    if (match) return `PHPSESSID=${match[1]}`;
  }
  return '';
}

export class KugouProvider implements MusicProvider {
  name = 'kugou';

  async search(query: string, limit = 20, offset = 0): Promise<MusicItem[]> {
    try {
      const pageSize = Math.min(Math.max(Math.floor(limit) || 20, 1), 30);
      const page = Math.floor(Math.max(Math.floor(offset) || 0, 0) / pageSize) + 1;
      const { data } = await axios.get<KugouSearchResponse>(SEARCH_API_URL, {
        headers: SEARCH_HEADERS,
        params: {
          format: 'json',
          keyword: query.trim(),
          platform: 'WebFilter',
          page,
          pagesize: pageSize,
        },
        timeout: REQUEST_TIMEOUT,
      });
      const list = data?.data?.lists || [];
      return list
        .map((item) => this.mapItem(item))
        .filter((item): item is MusicItem => Boolean(item));
    } catch (error) {
      console.error('Kugou search error:', error);
      return [];
    }
  }

  async getPlayInfo(id: string, extra?: unknown): Promise<PlayInfo> {
    const fallbackCover = getExtraValue(extra, 'cover') as string | undefined;
    const selectedParser = (extra as KugouExtra | undefined)?.selectedParser;
    const resolvers = {
      '90svip': () => this.getBy90svip(id),
      baka: () => this.getByBaka(id),
      cenguigui: () => this.getByCenguigui(id),
      haitang: () => this.getByHaitang(id),
    };
    const order: KugouParser[] = ['90svip', 'baka', 'cenguigui', 'haitang'];
    if (selectedParser && order.includes(selectedParser)) {
      order.splice(order.indexOf(selectedParser), 1);
      order.unshift(selectedParser);
    }
    let lastError: unknown;
    for (const parser of order) {
      try {
        const info = await resolvers[parser]();
        return {
          url: info.url,
          type: extractExt(info.url),
          bitrate: info.bitrate,
          cover: info.cover || fallbackCover,
        };
      } catch (error) {
        lastError = error;
        console.warn(`Kugou ${parser} fallback:`, error);
      }
    }
    throw lastError || new Error('Failed to get Kugou play url');
  }

  async getLyric(id: string, extra?: unknown): Promise<KugouLyricData> {
    const keyword = String(getExtraValue(extra, 'filename') || '');
    const duration = String(getExtraValue(extra, 'duration') || '-1');
    const { data: searchData } = await axios.get('http://lyrics.kugou.com/search', {
      params: { keyword, duration, hash: id },
      timeout: REQUEST_TIMEOUT,
    });
    const candidate = searchData?.candidates?.[0];
    if (!candidate?.id || !candidate?.accesskey) {
      return { songid: id, provider: 'kugou', lines: [], lrc: '' };
    }

    const { data: lyricData } = await axios.get('http://lyrics.kugou.com/download', {
      params: {
        ver: 1,
        client: 'pc',
        id: candidate.id,
        accesskey: candidate.accesskey,
        fmt: 'lrc',
        charset: 'utf8',
      },
      timeout: REQUEST_TIMEOUT,
    });
    const encoded = typeof lyricData?.content === 'string' ? lyricData.content : '';
    const lrc = encoded ? cleanLyric(Buffer.from(encoded, 'base64').toString('utf8')) : '';
    return {
      songid: id,
      provider: 'kugou',
      lines: parseLyricLines(lrc),
      lrc,
    };
  }

  private mapItem(item: KugouSearchItem): MusicItem | null {
    const id = String(item.FileHash || item.hash || '');
    if (!id) return null;
    const title = item.SongName || item.songname || item.FileName || item.filename || '未知歌曲';
    const artist = item.SingerName || item.singername || '未知歌手';
    const cover = normalizeCover(item.trans_param?.union_cover || item.cover_url || item.Image);
    const duration = item.Duration || item.duration || item.timelen;
    return {
      id,
      title,
      artist,
      album: item.AlbumName || item.album_name || undefined,
      cover,
      duration: formatDuration(duration),
      provider: this.name,
      extra: {
        cover,
        selectedParser: '90svip',
        selectedFormat: 'mp3',
        qualityOptions: KUGOU_DOWNLOAD_OPTIONS,
        filename: item.FileName || item.filename || `${title} - ${artist}`,
        duration: duration || -1,
      },
    };
  }

  private async getBy90svip(id: string) {
    const params = new URLSearchParams({
      input: id,
      filter: 'id',
      type: 'kugou',
      page: '1',
    });
    const response = await axios.post(SVIP90_BASE_URL, params, {
      headers: {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': SVIP90_BASE_URL,
        'User-Agent': SEARCH_HEADERS['User-Agent'],
        'X-Requested-With': 'XMLHttpRequest',
      },
      timeout: REQUEST_TIMEOUT,
    });
    const item = Array.isArray(response.data?.data) ? response.data.data[0] : undefined;
    const rawUrl = typeof item?.url === 'string' ? item.url : '';
    if (!rawUrl) throw new Error('90svip returned no play url');
    const url = new URL(rawUrl, SVIP90_BASE_URL).toString();
    const cookie = parseSessionCookie(response.headers['set-cookie']);
    if (!cookie) throw new Error('90svip returned no PHP session');
    const verified = await validateAudioLink(url, {
      headers: {
        cookie,
        'Referer': SVIP90_BASE_URL,
        'User-Agent': SEARCH_HEADERS['User-Agent'],
      },
      timeout: REQUEST_TIMEOUT,
    });
    return { url: verified.url, bitrate: '320k', cover: undefined };
  }

  private async getByBaka(id: string) {
    const url = `${BAKA_API_URL}?server=kugou&type=url&id=${encodeURIComponent(id)}&br=2000`;
    const verified = await validateAudioLink(url, {
      headers: SEARCH_HEADERS,
      httpsAgent: BAKA_HTTPS_AGENT,
      timeout: REQUEST_TIMEOUT,
    });
    return { url: verified.url, bitrate: 'lossless', cover: undefined };
  }

  private async getByCenguigui(id: string) {
    for (const level of ['lossless', 'exhigh', 'standard']) {
      const { data } = await axios.get(CGG_API_URL, {
        params: { kg: '', id, type: 'song', format: 'json', level },
        timeout: REQUEST_TIMEOUT,
      });
      const payload = data?.data || {};
      const url = String(payload.url || '').trim();
      if (url.startsWith('http')) {
        try {
          const verified = await validateAudioLink(url, { headers: SEARCH_HEADERS });
          return {
            url: verified.url,
            bitrate: level,
            cover: typeof payload.pic === 'string' ? payload.pic : undefined,
          };
        } catch {
          continue;
        }
      }
    }
    throw new Error('Failed to get cenguigui url');
  }

  private async getByHaitang(id: string) {
    for (const apiUrl of HAITANG_API_URLS) {
      for (const level of ['hires', 'lossless', 'exhigh']) {
        try {
          const { data } = await axios.get(apiUrl, {
            params: { type: 'json', id, level },
            timeout: REQUEST_TIMEOUT,
          });
          const payload = data?.data || {};
          const url = String(payload.url || '').trim();
          if (url.startsWith('http')) {
            try {
              const verified = await validateAudioLink(url, { headers: SEARCH_HEADERS });
              return { url: verified.url, bitrate: level, cover: undefined };
            } catch {
              continue;
            }
          }
        } catch {
        }
      }
    }
    throw new Error('Failed to get haitang url');
  }
}
