import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef } from "react";

export function useOrientation() {
  const ref = useRef<HTMLElement | null>(null);
  useGSAP(() => { const media = gsap.matchMedia(); media.add("(prefers-reduced-motion: no-preference)", () => { if (ref.current) gsap.fromTo(ref.current, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.32, ease: "power2.out" }); }); return () => media.revert(); }, { scope: ref });
  return ref;
}
