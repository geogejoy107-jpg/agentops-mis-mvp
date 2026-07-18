export const HUMAN_PASSWORD_MIN_LENGTH = 12;
export const HUMAN_PASSWORD_MAX_LENGTH = 256;

export const HUMAN_SCRYPT_PARAMS = Object.freeze({
  name: "scrypt" as const,
  n: 16_384,
  r: 8,
  p: 1,
  keylen: 32,
});
