import { expect, test } from "@playwright/test";

const pageHtml = `<!doctype html><body>
<section id="conveyor"><article>first</article><article>second</article><article>third</article></section>
<div role="tablist">
  <button role="tab" disabled>account-1 locked</button>
  <button role="tab">account-2</button>
</div>
<button id="copy">Copy Motion Prompt</button>
<p id="copied"></p>
<p id="qa">Strike 1 amber</p>
<input id="file" type="file" aria-label="mp4 file" />
<p id="file-note"></p>
<dialog id="anim" open aria-label="animatic"><video aria-label="animatic video"></video></dialog>
<p>integrated loudness -14 LUFS</p>
<p>8000-hr tracker</p>
<script>
  document.getElementById("copy").onclick = () => { document.getElementById("copied").textContent = "Copied"; };
  document.getElementById("file").onchange = (event) => {
    const file = event.target.files[0];
    document.getElementById("file-note").textContent = file && file.name.endsWith(".mp4") ? "accepted" : "rejected";
  };
  document.getElementById("anim").addEventListener("cancel", (event) => event.preventDefault());
</script>
</body>`;

test("five desk journeys stay quiet", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) errors.push(String(response.status()));
  });
  await page.setContent(pageHtml);
  await expect(page.locator("#conveyor article")).toHaveCount(3);
  await expect(page.getByRole("tab", { name: "account-1 locked" })).toBeDisabled();
  await expect(page.getByRole("tab", { name: "account-2" })).toBeEnabled();
  await page.getByRole("button", { name: "Copy Motion Prompt" }).click();
  await expect(page.locator("#copied")).toHaveText("Copied");
  await expect(page.locator("#qa")).toContainText("Strike 1");
  await page.locator("#file").setInputFiles({ name: "clip.mp4", mimeType: "video/mp4", buffer: Buffer.from("mp4") });
  await expect(page.locator("#file-note")).toHaveText("accepted");
  await expect(page.getByRole("dialog", { name: "animatic" })).toBeVisible();
  await expect(page.getByText("-14 LUFS")).toBeVisible();
  await expect(page.getByText("8000-hr tracker")).toBeVisible();
  expect(errors).toEqual([]);
});
