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

  it("disables START while its own request is in flight, and re-enables after", async () => {
    let resolveCommand: (v: { status: string; command: string }) => void = () => {};
    vi.spyOn(api, "postCommand").mockReturnValue(
      new Promise((resolve) => {
        resolveCommand = resolve;
      }),
    );
    render(<ControlsPanel />);

    const startBtn = screen.getByRole("button", { name: "START" });

    fireEvent.click(startBtn);

    await waitFor(() => expect(startBtn).toBeDisabled());

    await act(async () => {
      resolveCommand({ status: "ok", command: "start" });
    });
    await waitFor(() => expect(startBtn).not.toBeDisabled());
  });

  it("never disables ABORT because of a pending START -- ABORT fires immediately regardless", async () => {
    let resolveStart: (v: { status: string; command: string }) => void = () => {};
    const spy = vi.spyOn(api, "postCommand").mockImplementation((command) => {
      if (command === "start") {
        return new Promise((resolve) => {
          resolveStart = resolve;
        });
      }
      return Promise.resolve({ status: "ok", command });
    });
    render(<ControlsPanel />);

    const startBtn = screen.getByRole("button", { name: "START" });
    const abortBtn = screen.getByRole("button", { name: "STOP / ABORT" });

    fireEvent.click(startBtn);
    await waitFor(() => expect(startBtn).toBeDisabled());

    // ABORT must stay enabled and fire immediately, without waiting for
    // the still-pending START request to resolve.
    expect(abortBtn).not.toBeDisabled();
    await act(async () => {
      fireEvent.click(abortBtn);
    });
    expect(spy).toHaveBeenCalledWith("abort");

    await act(async () => {
      resolveStart({ status: "ok", command: "start" });
    });
    await waitFor(() => expect(startBtn).not.toBeDisabled());
  });

  it("disables ABORT only while its own request is in flight, and re-enables after", async () => {
    let resolveAbort: (v: { status: string; command: string }) => void = () => {};
    vi.spyOn(api, "postCommand").mockReturnValue(
      new Promise((resolve) => {
        resolveAbort = resolve;
      }),
    );
    render(<ControlsPanel />);

    const startBtn = screen.getByRole("button", { name: "START" });
    const abortBtn = screen.getByRole("button", { name: "STOP / ABORT" });

    fireEvent.click(abortBtn);

    await waitFor(() => expect(abortBtn).toBeDisabled());
    // START must not be disabled by ABORT's in-flight state either.
    expect(startBtn).not.toBeDisabled();

    await act(async () => {
      resolveAbort({ status: "ok", command: "abort" });
    });
    await waitFor(() => expect(abortBtn).not.toBeDisabled());
  });

  it("shows an inline error on command failure, without throwing", async () => {
    vi.spyOn(api, "postCommand").mockRejectedValue(new Error("HTTP 503"));
    render(<ControlsPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "STOP / ABORT" }));
    });

    expect(await screen.findByText(/ABORT failed: HTTP 503/)).toBeInTheDocument();
  });

  it("keeps both START and ABORT error messages visible when both fail close together", async () => {
    vi.spyOn(api, "postCommand").mockImplementation((command) =>
      Promise.reject(new Error(`HTTP 503 (${command})`)),
    );
    render(<ControlsPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "START" }));
      fireEvent.click(screen.getByRole("button", { name: "STOP / ABORT" }));
    });

    expect(await screen.findByText(/START failed: HTTP 503 \(start\)/)).toBeInTheDocument();
    expect(await screen.findByText(/ABORT failed: HTTP 503 \(abort\)/)).toBeInTheDocument();
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
