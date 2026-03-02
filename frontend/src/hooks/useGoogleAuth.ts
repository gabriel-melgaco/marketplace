const REDIRECT_URI = `${window.location.origin}/google`;
const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export type GoogleAuthIntent = "login" | "connect";

function generateState(intent: GoogleAuthIntent): string {
  const nonce = crypto.randomUUID();
  const state = `${intent}:${nonce}`;
  localStorage.setItem("google_oauth_state", state);
  return state;
}

export function startGoogleOAuth(intent: GoogleAuthIntent) {
  const params = new URLSearchParams({
    client_id: GOOGLE_CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    response_type: "code",
    scope: "openid profile email",
    access_type: "online",
    state: generateState(intent),
  });
  window.location.href = `${GOOGLE_AUTH_URL}?${params.toString()}`;
}
