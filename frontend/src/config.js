export const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || '/api';

export const REFRESH_INTERVALS = {
  chat: 3000,
  liveFeed: 8000,
};
