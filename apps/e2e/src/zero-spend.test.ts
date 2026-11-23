import net from "node:net";
import { expect, test } from "vitest";
import { liveSandboxAuthorized, scrubProviderEnv } from "./zero-spend.setup.ts";

test("live sandbox needs both gates", () => {
  expect(liveSandboxAuthorized(["--live-sandbox"], { ALLOW_PAID_SANDBOX: "1" })).toBe(true);
  expect(liveSandboxAuthorized(["--live-sandbox"], {})).toBe(false);
  expect(liveSandboxAuthorized([], { ALLOW_PAID_SANDBOX: "1" })).toBe(false);
});

test("scrub removes provider keys", () => {
  const env = { GEMINI_API_KEY: "present", PATH: "/usr/bin" } as NodeJS.ProcessEnv;
  scrubProviderEnv(env);
  expect(env.GEMINI_API_KEY).toBeUndefined();
  expect(env.PATH).toBe("/usr/bin");
});

test("fetch to a public host is blocked", async () => {
  await expect(fetch("https://example.com/")).rejects.toThrow(/blocked outbound fetch/i);
});

test("loopback sockets stay open", async () => {
  const server = net.createServer();
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve());
  });
  const address = server.address();
  if (address == null || typeof address === "string") {
    throw new Error("expected a tcp port");
  }
  const client = net.connect({ host: "127.0.0.1", port: address.port });
  await new Promise<void>((resolve, reject) => {
    client.once("connect", () => resolve());
    client.once("error", reject);
  });
  client.end();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});
