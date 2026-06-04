import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the client shell without a React global", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "NTEToolbox" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "异环 NTE" })).toBeTruthy();
  });
});
