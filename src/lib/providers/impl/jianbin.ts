import axios from 'axios';
import { MusicItem, MusicProvider, PlayInfo } from '@/types/music';

const BASE_URL = 'https://www.jbsou.cn/';
const REQUEST_TIMEOUT = 30000;

const SEARCH_HEADERS = {
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
  'accept': 'application/json, text/javascript, */*; q=0.01',
  'accept-encoding': 'gzip, deflate, br, zstd',
  'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
  'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
  'origin': 'https://www.jbsou.cn',
  'x-requested-with': 'XMLHttpRequest',
  'referer': 'https://www.jbsou.cn/',
};

const PAGE_HEADERS = {
  'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'accept-language': SEARCH_HEADERS['accept-language'],
  'user-agent': SEARCH_HEADERS['user-agent'],
};

type JbsouSearchItem = {
  songid?: string | number;
  name?: string;
  artist?: string;
  album?: string;
  url?: string;
  cover?: string;
};

type JbsouSearchResponse = {
  code?: number;
  data?: JbsouSearchItem[] | string;
  error?: string;
};

function toAbsoluteUrl(value?: string) {
  if (!value) return '';
  try {
    return new URL(value, BASE_URL).toString();
  } catch {
    return value;
  }
}

function extractExt(url: string) {
  const clean = url.split('?')[0];
  const parts = clean.split('.');
  return parts.length > 1 ? parts[parts.length - 1] : 'mp3';
}

function normalizeSearchResponse(payload: unknown): JbsouSearchResponse {
  if (!payload) return {};
  if (typeof payload === 'string') {
    try {
      return JSON.parse(payload) as JbsouSearchResponse;
    } catch {
      return {};
    }
  }
  return payload as JbsouSearchResponse;
}

function parseSessionCookie(setCookie?: string[] | string) {
  const values = Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : [];
  for (const value of values) {
    const match = value.match(/(?:^|[,;]\s*)PHPSESSID=([^;,\s]+)/i);
    if (match) return `PHPSESSID=${match[1]}`;
  }
  return '';
}

function isJbsouUrl(value: string) {
  try {
    return new URL(value).hostname === new URL(BASE_URL).hostname;
  } catch {
    return false;
  }
}

function getResponseUrl(response: unknown) {
  const request = response as { request?: { res?: { responseUrl?: string } } };
  const resUrl = request?.request?.res?.responseUrl;
  if (typeof resUrl === 'string' && resUrl.startsWith('http')) return resUrl;
  const config = response as { config?: { url?: string } };
  const configUrl = config?.config?.url;
  return typeof configUrl === 'string' ? configUrl : '';
}

async function resolveFinalUrl(url: string, cookie?: string) {
  const response = await axios.head(url, {
    headers: {
      'user-agent': SEARCH_HEADERS['user-agent'],
      ...(cookie && isJbsouUrl(url) ? { cookie } : {}),
    },
    timeout: REQUEST_TIMEOUT,
    maxRedirects: 5,
  });
  const resolved = getResponseUrl(response);
  const finalUrl = resolved && resolved.startsWith('http') ? resolved : url;
  if (isJbsouUrl(url) && isJbsouUrl(finalUrl)) {
    throw new Error('JBSou play session was not accepted');
  }
  return finalUrl;
}

function normalizeIdToUrl(id: string) {
  const value = (id || '').trim();
  if (!value) return '';
  const decodedOnce = value.includes('%') ? safeDecode(value) : value;
  const decoded = decodedOnce.includes('%') ? safeDecode(decodedOnce) : decodedOnce;
  if (decoded.startsWith('http')) return decoded;
  return toAbsoluteUrl(decoded);
}

function safeDecode(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export class JianbinProvider implements MusicProvider {
  name: string;
  private source: string;

  constructor(name: string, source: string) {
    this.name = name;
    this.source = source;
  }

  private async bootstrapSession() {
    const response = await axios.get(BASE_URL, {
      headers: PAGE_HEADERS,
      timeout: REQUEST_TIMEOUT,
    });
    const cookie = parseSessionCookie(response.headers['set-cookie']);
    if (!cookie) throw new Error('JBSou did not provide a PHP session');
    return cookie;
  }

  private async requestSearch(query: string, cookie: string) {
    const params = new URLSearchParams({
      input: query,
      filter: 'name',
      type: this.source,
      page: '1',
    });
    const { data } = await axios.post<JbsouSearchResponse>(BASE_URL, params, {
      headers: { ...SEARCH_HEADERS, cookie },
      timeout: REQUEST_TIMEOUT,
    });
    return normalizeSearchResponse(data);
  }

  async search(query: string): Promise<MusicItem[]> {
    try {
      let payload: JbsouSearchResponse = {};
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const cookie = await this.bootstrapSession();
        payload = await this.requestSearch(query, cookie);
        if (payload.code === 200 || Array.isArray(payload.data)) {
          break;
        }
      }
      const list = Array.isArray(payload.data) ? payload.data : [];
      return list
        .map((item) => {
          const downloadUrl = toAbsoluteUrl(item?.url);
          const signedCoverUrl = toAbsoluteUrl(item?.cover);
          const coverUrl = signedCoverUrl
            ? `/api/jbsou/asset?url=${encodeURIComponent(signedCoverUrl)}`
            : '';
          return {
            id: downloadUrl ? encodeURIComponent(downloadUrl) : '',
            title: item?.name || '未知歌曲',
            artist: item?.artist || '未知歌手',
            album: item?.album || undefined,
            cover: coverUrl || undefined,
            provider: this.name,
          };
        })
        .filter((item) => item.id);
    } catch (error) {
      console.error('Jianbin search error:', error);
      return [];
    }
  }

  async getPlayInfo(id: string): Promise<PlayInfo> {
    try {
      const url = normalizeIdToUrl(id);
      if (!url) throw new Error('Invalid id');
      if (!isJbsouUrl(url)) {
        const finalUrl = await resolveFinalUrl(url);
        return {
          url: finalUrl,
          type: extractExt(finalUrl),
        };
      }

      let finalUrl = '';
      let lastError: unknown;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const cookie = await this.bootstrapSession();
          finalUrl = await resolveFinalUrl(url, cookie);
          break;
        } catch (error) {
          lastError = error;
        }
      }
      if (!finalUrl) throw lastError || new Error('Failed to resolve JBSou play url');
      if (!finalUrl.startsWith('http')) throw new Error('Invalid play url');
      return {
        url: finalUrl,
        type: extractExt(finalUrl),
      };
    } catch (error) {
      console.error('Jianbin getPlayInfo error:', error);
      throw error;
    }
  }
}
