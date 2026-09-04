import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ControlsPanel from "./ControlsPanel";
import * as api from "../api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ControlsPanel", () => {
  it("clicking START calls postCommand('start')", async () => {
    const spy = vi.spyOn(api, "postCommand").mockResolvedValue({ status: "ok", command: "start" });
    render(<ControlsPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "START" }));
    });

    expect(spy).toHaveBeenCalledWith("start");
  });

  it("clicking ABORT calls postCommand('abort')", async () => {
    const spy = vi.spyOn(api, "postCommand").mockResolvedValue({ status: "ok", command: "abort" });
    render(<ControlsPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "STOP / ABORT" }));
    });

    expect(spy).toHaveBeenCalledWith("abort");
  });

  it("disables both buttons while a request is in flight", async () => {
    let resolveCommand: (v: { status: string; command: string }) => void = () => {};
    vi.spyOn(api, "postCommand").mockReturnValue(
      new Promise((resolve) => {
        resolveCommand = resolve;
      }),
    );
    render(<ControlsPanel />);

    const startBtn = screen.getByRole("button", { name: "START" });
    const abortBtn = screen.getByRole("button", { name: "STOP / ABORT" });

    fireEvent.click(startBtn);

    await waitFor(() => expect(startBtn).toBeDisabled());
    expect(abortBtn).toBeDisabled();

    await act(async () => {
      resolveCommand({ status: "ok", command: "start" });
    });
    await waitFor(() => expect(startBtn).not.toBeDisabled());
    expect(abortBtn).not.toBeDisabled();
  });

  it("shows an inline error on command failure, without throwing", async () => {
    vi.spyOn(api, "postCommand").mockRejectedValue(new Error("HTTP 503"));
    render(<ControlsPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "STOP / ABORT" }));
    });

    expect(await screen.findByText(/ABORT failed: HTTP 503/)).toBeInTheDocument();
  });

  it("does not render any confirmation control before ABORT", () => {
    render(<ControlsPanel />);
    // Exactly two buttons: START and STOP/ABORT -- no "confirm" dialog.
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("shows the bench-test safety note", () => {
    render(<ControlsPanel />);
    expect(screen.getByText(/BENCH TEST — PROPS REMOVED/)).toBeInTheDocument();
  });
});
