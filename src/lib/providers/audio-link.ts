import axios from 'axios';
import type { Agent } from 'https';

const AUDIO_EXTENSIONS = new Set(['aac', 'flac', 'm4a', 'mp3', 'ogg', 'opus', 'wav']);

type ValidateAudioLinkOptions = {
  headers?: Record<string, string>;
  httpsAgent?: Agent;
  timeout?: number;
};

function responseUrl(response: unknown, fallback: string) {
  const value = response as { request?: { res?: { responseUrl?: string } } };
  return value.request?.res?.responseUrl || fallback;
}

function urlExtension(url: string) {
  try {
    const pathname = new URL(url).pathname;
    return pathname.includes('.') ? pathname.split('.').pop()?.toLowerCase() || '' : '';
  } catch {
    return '';
  }
}

export async function validateAudioLink(url: string, options: ValidateAudioLinkOptions = {}) {
  const response = await axios.get(url, {
    headers: {
      Range: 'bytes=0-1',
      ...options.headers,
    },
    httpsAgent: options.httpsAgent,
    maxRedirects: 5,
    responseType: 'stream',
    timeout: options.timeout || 15000,
  });
  const stream = response.data as { destroy?: () => void };
  stream.destroy?.();

  const finalUrl = responseUrl(response, url);
  const contentType = String(response.headers['content-type'] || '').toLowerCase();
  const isAudioType = contentType.startsWith('audio/') || contentType.includes('application/octet-stream');
  if (contentType && !isAudioType) {
    throw new Error(`Non-audio content type: ${contentType}`);
  }
  if (!contentType && !AUDIO_EXTENSIONS.has(urlExtension(finalUrl))) {
    throw new Error('Audio response has no recognizable content type or extension');
  }
  return { url: finalUrl, contentType };
}
