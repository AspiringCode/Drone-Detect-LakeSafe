import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AccessibleDialog } from "./AccessibleDialog";

it("starts with neutral focus, contains Tab, closes on Escape and restores focus", () => {
  const trigger = document.createElement("button"); document.body.append(trigger); trigger.focus();
  const close = vi.fn();
  const view = render(<AccessibleDialog title="Review changes" onClose={close}><button>Apply</button><button>Cancel</button></AccessibleDialog>);
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveFocus();
  fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
  expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  fireEvent.keyDown(dialog, { key: "Escape" }); expect(close).toHaveBeenCalledOnce();
  view.unmount(); expect(trigger).toHaveFocus(); trigger.remove();
});
