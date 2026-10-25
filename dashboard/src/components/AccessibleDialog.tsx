import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function AccessibleDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose); closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    const background = Array.from(document.body.children).filter((node) => !node.contains(dialog)) as HTMLElement[];
    const prior = background.map((node) => node.inert);
    background.forEach((node) => { node.inert = true; });
    dialog.focus();
    const contain = (event: FocusEvent) => { if (!dialog.contains(event.target as Node)) dialog.focus(); };
    document.addEventListener("focusin", contain);
    return () => { document.removeEventListener("focusin", contain); background.forEach((node, index) => { node.inert = prior[index]; }); if (previous?.isConnected) previous.focus(); };
  }, []);
  return createPortal(<div className="modal-backdrop"><div ref={ref} className="modal-card" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} onKeyDown={(event) => {
    if (event.key === "Escape") { event.preventDefault(); closeRef.current(); }
    if (event.key !== "Tab") return;
    const controls = Array.from(ref.current!.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'));
    const first = controls[0], last = controls[controls.length - 1];
    if (!first) { event.preventDefault(); ref.current!.focus(); }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }}><h2 id={titleId}>{title}</h2>{children}</div></div>, document.body);
}
