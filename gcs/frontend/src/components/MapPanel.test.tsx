import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import MapPanel from "./MapPanel";
import * as api from "../api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MapPanel", () => {
  it("shows the explicit not-implemented placeholder when data is null", async () => {
    vi.spyOn(api, "getMap").mockResolvedValue({ resolution: null, width: null, height: null, data: null });
    render(<MapPanel />);

    expect(
      await screen.findByText(/No SLAM map yet — mapping not implemented in onboard-autonomy\./),
    ).toBeInTheDocument();
  });

  it("shows the placeholder when data is an empty array, not a fabricated grid", async () => {
    vi.spyOn(api, "getMap").mockResolvedValue({ resolution: 1, width: 0, height: 0, data: [] });
    render(<MapPanel />);

    await waitFor(() =>
      expect(screen.getByText(/No SLAM map yet/)).toBeInTheDocument(),
    );
  });

  it("shows dimensions instead of the placeholder once real data arrives", async () => {
    vi.spyOn(api, "getMap").mockResolvedValue({ resolution: 1, width: 15, height: 15, data: [0, 1, -1] });
    render(<MapPanel />);

    expect(await screen.findByText(/15 × 15 cells/)).toBeInTheDocument();
    expect(screen.queryByText(/No SLAM map yet/)).not.toBeInTheDocument();
  });
});
