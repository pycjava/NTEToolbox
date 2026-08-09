import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("index.html", () => {
  it("declares an inline favicon to avoid browser 404 noise", () => {
    const html = readFileSync(resolve(__dirname, "../index.html"), "utf8");

    expect(html).toContain('rel="icon"');
    expect(html).toContain("data:image/svg+xml");
  });
});
