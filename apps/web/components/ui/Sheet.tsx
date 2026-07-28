/**
 * Sheet/Drawer 组件
 * 桌面端: 右侧滑出面板 (Sheet)
 * 手机端: 底部弹出面板 (Drawer)
 * 支持拖拽关闭（手机端）
 */

"use client";

import { motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useId, useRef, type RefObject } from "react";
import { cn } from "@/lib/utils";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  banner?: React.ReactNode;
  overlay?: React.ReactNode;
  side?: "right" | "bottom";
  className?: string;
  fallbackFocusRef?: RefObject<HTMLElement | null>;
}

const FOCUSABLE_SELECTOR = [
  "button",
  "a[href]",
  "input",
  "textarea",
  "select",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function tabbableElements(scope: HTMLElement) {
  const candidates = Array.from(
    scope.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter(
    (element) =>
      !element.matches(":disabled")
      && element.tabIndex >= 0
      && element.getClientRects().length > 0,
  );

  return candidates.filter((element) => {
    if (!(element instanceof HTMLInputElement) || element.type !== "radio" || !element.name) {
      return true;
    }
    const group = candidates.filter(
      (candidate): candidate is HTMLInputElement =>
        candidate instanceof HTMLInputElement
        && candidate.type === "radio"
        && candidate.name === element.name
        && candidate.form === element.form,
    );
    return element === (group.find((radio) => radio.checked) ?? group[0]);
  });
}

function activeFocusScope(root: HTMLElement, sheet: HTMLElement) {
  return root.querySelector<HTMLElement>('[data-sheet-focus-scope="active"]') ?? sheet;
}

function isTopmostSheet(root: HTMLElement) {
  const roots = Array.from(document.querySelectorAll<HTMLElement>("[data-sheet-root]"))
    .filter((candidate) => candidate.getClientRects().length > 0);
  return roots.at(-1) === root;
}

function fallbackPageFocus(explicitFallback: HTMLElement | null) {
  const fallback = explicitFallback?.isConnected
    ? explicitFallback
    : document.querySelector<HTMLElement>("[data-sheet-focus-fallback]")
      ?? document.querySelector<HTMLElement>('main, [role="main"]');
  if (fallback?.isConnected) {
    if (!fallback.hasAttribute("tabindex")) fallback.tabIndex = -1;
    fallback.focus();
    return;
  }
  document.body.tabIndex = -1;
  document.body.focus();
}

export function Sheet({
  open,
  onClose,
  title,
  children,
  banner,
  overlay,
  side = "right",
  className,
  fallbackFocusRef,
}: SheetProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const previousFocusKeyRef = useRef<string | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    previousFocusKeyRef.current = previousFocusRef.current?.getAttribute("data-sheet-trigger") ?? null;
    const fallbackFocus = fallbackFocusRef?.current ?? null;
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      const previousFocus = previousFocusRef.current;
      const previousFocusKey = previousFocusKeyRef.current;
      previousFocusRef.current = null;
      previousFocusKeyRef.current = null;
      window.requestAnimationFrame(() => {
        const triggerStillMatches = previousFocusKey === null
          || previousFocus?.getAttribute("data-sheet-trigger") === previousFocusKey;
        if (
          previousFocus?.isConnected
          && triggerStillMatches
          && !previousFocus.matches(":disabled")
          && previousFocus.getClientRects().length > 0
        ) {
          previousFocus.focus();
          return;
        }
        const replacementTrigger = previousFocusKey === null
          ? null
          : Array.from(document.querySelectorAll<HTMLElement>("[data-sheet-trigger]"))
            .find((element) => (
              element.getAttribute("data-sheet-trigger") === previousFocusKey
              && !element.matches(":disabled")
              && element.getClientRects().length > 0
            ));
        if (replacementTrigger) {
          replacementTrigger.focus();
        } else {
          fallbackPageFocus(fallbackFocus);
        }
      });
    };
  }, [fallbackFocusRef, open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const root = rootRef.current;
      const sheet = sheetRef.current;
      if (!root || !sheet || !isTopmostSheet(root)) return;
      const focusScope = activeFocusScope(root, sheet);

      if (event.key === "Escape") {
        event.preventDefault();
        const nestedDismiss = focusScope === sheet
          ? null
          : focusScope.querySelector<HTMLElement>("[data-sheet-dismiss]");
        if (nestedDismiss) nestedDismiss.click();
        else onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = tabbableElements(focusScope);
      if (focusable.length === 0) {
        event.preventDefault();
        focusScope.focus();
        return;
      }

      const activeIndex = focusable.indexOf(document.activeElement as HTMLElement);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (activeIndex < 0) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && activeIndex === 0) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeIndex === focusable.length - 1) {
        event.preventDefault();
        first.focus();
      }
    };
    const handleFocusIn = (event: FocusEvent) => {
      const root = rootRef.current;
      const sheet = sheetRef.current;
      const target = event.target;
      if (!root || !sheet || !(target instanceof HTMLElement) || !isTopmostSheet(root)) return;
      const focusScope = activeFocusScope(root, sheet);
      if (focusScope.contains(target)) return;
      (tabbableElements(focusScope)[0] ?? focusScope).focus();
    };
    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("focusin", handleFocusIn, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.removeEventListener("focusin", handleFocusIn, true);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const isMobile = typeof window !== "undefined" && window.innerWidth < 768;
  const effectiveSide = isMobile ? "bottom" : side;

  if (!open) return null;

  return (
    <div ref={rootRef} data-sheet-root>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      <motion.div
        ref={sheetRef}
        role="dialog"
        aria-modal={overlay ? undefined : "true"}
        aria-hidden={overlay ? "true" : undefined}
        aria-labelledby={titleId}
        inert={overlay ? true : undefined}
        tabIndex={-1}
        className={cn(
          "fixed z-50 border-[var(--border)] bg-[var(--panel-bg)] shadow-2xl",
          effectiveSide === "right"
            && "right-0 top-0 h-full w-full border-l md:w-[480px]",
          effectiveSide === "bottom"
            && "bottom-0 left-0 right-0 h-[85vh] overflow-hidden rounded-t-2xl border-t",
          className,
        )}
        initial={effectiveSide === "right" ? { x: "100%" } : { y: "100%" }}
        animate={effectiveSide === "right" ? { x: 0 } : { y: 0 }}
        transition={{ type: "spring", damping: 25, stiffness: 250 }}
        drag={effectiveSide === "bottom" ? "y" : false}
        dragConstraints={{ top: 0, bottom: 150 }}
        dragElastic={0.2}
        onDragEnd={(_, info) => {
          if (info.offset.y > 100) onClose();
        }}
      >
        {effectiveSide === "bottom" && (
          <div className="flex justify-center pb-1 pt-2">
            <div className="h-1 w-10 rounded-full bg-[var(--muted)]" />
          </div>
        )}

        <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
          <h2 id={titleId} className="text-lg font-bold">{title}</h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-lg p-1.5 transition-colors hover:bg-[var(--accent)]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 overflow-y-auto" style={{ height: "calc(100% - 52px)" }}>
          {banner}
          {children}
        </div>
      </motion.div>
      {overlay}
    </div>
  );
}
