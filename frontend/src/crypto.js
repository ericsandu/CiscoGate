const encoder = new TextEncoder();

function bytesToBase64(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

/**
 * Hackathon key agreement used by the frontend task.
 * Tier 3 must derive the same key from the proxy ID before decrypting.
 */
async function deriveKey(sharedSecret) {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    encoder.encode(`CiscoGate:${sharedSecret}`),
  );

  return crypto.subtle.importKey(
    'raw',
    digest,
    { name: 'AES-GCM' },
    false,
    ['encrypt'],
  );
}

export async function encryptForProxy(value, sharedSecret) {
  if (!window.isSecureContext && window.location.hostname !== 'localhost') {
    throw new Error('WebCrypto necesită HTTPS sau localhost.');
  }

  const key = await deriveKey(sharedSecret);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = encoder.encode(JSON.stringify(value));
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plaintext);

  return {
    version: 1,
    algorithm: 'AES-GCM',
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(encrypted)),
  };
}
