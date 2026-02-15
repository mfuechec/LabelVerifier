import { describe, it, expect } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import { getErrorMessage } from './errors';

function makeAxiosError(status: number, data: unknown, hasResponse = true): AxiosError {
  const headers = new AxiosHeaders();
  const config = { headers } as import('axios').InternalAxiosRequestConfig;
  if (!hasResponse) {
    return new AxiosError('Network Error', 'ERR_NETWORK', config);
  }
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', config, null, {
    status,
    statusText: 'Error',
    headers: {},
    config,
    data,
  });
}

describe('getErrorMessage', () => {
  it('returns string detail from 422 response', () => {
    const err = makeAxiosError(422, { detail: 'Image too large: 34.8M pixels. Maximum: 33.2M pixels.' });
    expect(getErrorMessage(err)).toBe('Image too large: 34.8M pixels. Maximum: 33.2M pixels.');
  });

  it('joins msg fields from array detail (FastAPI validation format)', () => {
    const err = makeAxiosError(422, {
      detail: [
        { loc: ['body', 'images'], msg: 'field required', type: 'value_error.missing' },
        { loc: ['body', 'pdf'], msg: 'invalid format', type: 'value_error' },
      ],
    });
    expect(getErrorMessage(err)).toBe('field required; invalid format');
  });

  it('returns connection message for network error (no response)', () => {
    const err = makeAxiosError(0, null, false);
    expect(getErrorMessage(err)).toBe('Unable to reach the server. Check your connection and try again.');
  });

  it('returns server error message for 500 with no detail', () => {
    const err = makeAxiosError(500, {});
    expect(getErrorMessage(err)).toBe('An unexpected server error occurred. Please try again later.');
  });

  it('returns generic message for plain Error object', () => {
    expect(getErrorMessage(new Error('something broke'))).toBe('An unexpected error occurred. Please try again.');
  });

  it('returns generic message for non-error value', () => {
    expect(getErrorMessage('just a string')).toBe('An unexpected error occurred. Please try again.');
    expect(getErrorMessage(null)).toBe('An unexpected error occurred. Please try again.');
  });
});
