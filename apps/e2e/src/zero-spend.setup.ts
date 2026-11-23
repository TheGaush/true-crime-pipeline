import dns from "node:dns";
import net from "node:net";

const PROVIDER_KEYS = [
  "GEMINI_API_KEY",
  "DEEPSEEK_API_KEY",
  "ELEVENLABS_API_KEY",
  "GOOGLE_API_KEY",
  "GOOGLE_GENAI_API_KEY",
  "VERTEX_API_KEY",
  "OPENAI_API_KEY",
];

const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost", "[::1]"]);

export function liveSandboxAuthorized(argv: readonly string[], env: NodeJS.ProcessEnv): boolean {
  return argv.includes("--live-sandbox") && env.ALLOW_PAID_SANDBOX === "1";
}

export function scrubProviderEnv(env: NodeJS.ProcessEnv = process.env): void {
  for (const key of Object.keys(env)) {
    if (PROVIDER_KEYS.includes(key) || key.endsWith("_API_KEY") || key.endsWith("_SECRET")) {
      delete env[key];
    }
  }
}

function isLoopback(host: string | undefined): boolean {
  return host == null || host === "" || LOOPBACK.has(host);
}

let installed = false;

export function installOutboundBlock(): void {
  if (installed) return;
  installed = true;

  const originalConnect = net.Socket.prototype.connect;
  function blockedConnect(this: net.Socket, ...args: unknown[]): unknown {
    const first: unknown = args[0];
    let host: string | undefined;
    if (typeof first === "string" && args.length === 1) {
      return Reflect.apply(originalConnect, this, args);
    }
    if (typeof first === "object" && first !== null && "host" in first) {
      const value = (first as { host?: unknown }).host;
      host = typeof value === "string" ? value : undefined;
    } else if (typeof args[1] === "string") {
      host = args[1];
    }
    if (!isLoopback(host) && host !== undefined) {
      throw new Error(`zero-spend offline guard blocked outbound socket to ${host}`);
    }
    return Reflect.apply(originalConnect, this, args);
  }
  net.Socket.prototype.connect = blockedConnect as typeof net.Socket.prototype.connect;

  const originalLookup = dns.lookup.bind(dns);
  function blockedLookup(hostname: string, ...rest: unknown[]): unknown {
    if (!isLoopback(hostname)) {
      const error = new Error(`zero-spend offline guard blocked outbound DNS for ${hostname}`);
      const callback = rest.find((item) => typeof item === "function") as
        | ((err: Error) => void)
        | undefined;
      if (callback) {
        callback(error);
        return;
      }
      throw error;
    }
    return Reflect.apply(originalLookup, dns, [hostname, ...rest]);
  }
  dns.lookup = blockedLookup as typeof dns.lookup;

  const originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = (async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
    const raw =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw);
    if (!isLoopback(url.hostname)) {
      throw new Error(`zero-spend offline guard blocked outbound fetch to ${url.hostname}`);
    }
    return originalFetch(input, init);
  }) as typeof fetch;
}

if (!liveSandboxAuthorized(process.argv, process.env)) {
  scrubProviderEnv();
  installOutboundBlock();
}
