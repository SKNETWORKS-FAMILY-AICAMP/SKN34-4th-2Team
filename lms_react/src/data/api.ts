/** 하위 호환. 신규 코드는 http.ts 를 쓴다. */
export { API_BASE, http as api, readApiError } from './http';

export async function ensureCsrf(): Promise<void> {
  /* JWT 전환 후 CSRF는 쓰지 않는다 */
}
