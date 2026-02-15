import axios from 'axios';

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return 'Unable to reach the server. Check your connection and try again.';
    }

    const detail = error.response.data?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: { msg: string }) => d.msg).join('; ');
    }

    if (error.response.status >= 500) {
      return 'An unexpected server error occurred. Please try again later.';
    }
  }

  return 'An unexpected error occurred. Please try again.';
}
