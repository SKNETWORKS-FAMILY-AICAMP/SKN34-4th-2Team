/** Explicit settings for archived Firebase scripts; never supply production defaults. */
export function requireLegacyEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`3차 Firebase 보관 도구: ${name} 환경변수를 명시하세요.`);
  return value;
}
