// Single source of truth for the backend base URL.
// Override at build/dev time with PUBLIC_API_BASE_URL in a .env file.
export const API_BASE_URL = import.meta.env.PUBLIC_API_BASE_URL || 'http://localhost:8000';
