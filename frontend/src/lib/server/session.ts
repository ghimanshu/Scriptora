import "server-only";
import { NextResponse } from "next/server";
import { config } from "./config";
import { csrfToken } from "./csrf";
export interface Tokens {
  access_token: string;
  refresh_token: string;
  expires_in?: number;
}
export function setSession(response: NextResponse, tokens: Tokens) {
  const c = config();
  const base = {
    secure: c.secure,
    sameSite: "lax" as const,
    path: "/",
    httpOnly: true,
  };
  response.cookies.set(c.names.access, tokens.access_token, {
    ...base,
    maxAge: tokens.expires_in || 900,
  });
  response.cookies.set(c.names.refresh, tokens.refresh_token, {
    ...base,
    maxAge: 604800,
  });
  response.cookies.set(c.names.csrf, csrfToken(tokens.refresh_token), {
    ...base,
    httpOnly: false,
    maxAge: 604800,
  });
}
export function clearSession(response: NextResponse) {
  const c = config();
  Object.values(c.names).forEach((name) =>
    response.cookies.set(name, "", {
      path: "/",
      secure: c.secure,
      httpOnly: name !== c.names.csrf,
      sameSite: "lax",
      maxAge: 0,
    }),
  );
}
