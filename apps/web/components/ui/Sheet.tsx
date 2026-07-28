/**
 * Sheet/Drawer 组件
 * 桌面端: 右侧滑出面板 (Sheet)
 * 手机端: 底部弹出面板 (Drawer)
 * 支持拖拽关闭（手机端）
 */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { cn } from "@/lib/utils";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  side?: "right" | "bottom";
  className?: string;
  modal?: boolean;
}

const FOCUSABLE_SELECTOR = [
  "button",
  "a[href]",
  "input",
  "textarea",
  "select",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function sheetFocusRoots(root: HTMLElement) {
  return [
    root,
    ...Array.from(document.querySelectorAll<HTMLElement>("[data-sheet-focus-portal]"))
      .filter((portal) => !root.contains(portal)),
  ];
}

function focusableElements(root: HTMLElement) {
  const focusRoots = sheetFocusRoots(root);
  const elements = focusRoots.flatMap((focusRoot) => (
    Array.from(focusRoot.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
  )).filter(
    (element) => !element.matches(":disabled") && element.getClientRects().length > 0,
  );
  return elements.filter((element) => {
    if (!(element instanceof HTMLInputElement) || element.type !== "radio" || !element.name) {
      return true;
    }
    const group = elements.filter((candidate): candidate is HTMLInputElement => (
      candidate instanceof HTMLInputElement
      && candidate.type === "radio"
      && candidate.name === element.name
      && candidate.form === element.form
    ));
    return element === (group.find((candidate) => candidate.checked) ?? group[0]);
  });
}

function restoreFallbackFocus() {
  const fallback = document.querySelector<HTMLElement>("[data-sheet-focus-fallback]")
    ?? document.querySelector<HTMLElement>("main, [role=\"main\"]");
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
  side = "right",
  className,
  modal = true,
}: SheetProps) {
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
        if (previousFocus?.isConnected && triggerStillMatches) {
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
          restoreFallbackFocus();
        }
      });
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const sheet = sheetRef.current;
      if (!sheet) return;
      const focusable = focusableElements(sheet);
      if (focusable.length === 0) {
        event.preventDefault();
        sheet.focus();
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
      const sheet = sheetRef.current;
      const target = event.target;
      if (!sheet || !(target instanceof HTMLElement)) return;
      if (sheetFocusRoots(sheet).some((focusRoot) => focusRoot.contains(target))) return;
      (focusableElements(sheet)[0] ?? sheet).focus();
    };
    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("focusin", handleFocusIn, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.removeEventListener("focusin", handleFocusIn, true);
    };
  }, [open, onClose]);

  // 锁定背景滚动
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

  // 判断是否为手机端（通过媒体查询，运行时判断）
  const isMobile =
    typeof window !== "undefined" && window.innerWidth < 768;
  const effectiveSide = isMobile ? "bottom" : side;

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* 遮罩层 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* 面板 */}
          <motion.div
            ref={sheetRef}
            role="dialog"
            aria-modal={modal ? "true" : undefined}
            aria-labelledby={titleId}
            tabIndex={-1}
            className={cn(
              "fixed z-50 bg-[var(--panel-bg)] border-[var(--border)] shadow-2xl",
              // 右侧滑出
              effectiveSide === "right" &&
                "right-0 top-0 h-full w-full border-l md:w-[480px]",
              // 底部弹出
              effectiveSide === "bottom" &&
                "bottom-0 left-0 right-0 h-[85vh] rounded-t-2xl border-t overflow-hidden",
              className
            )}
            initial={
              effectiveSide === "right"
                ? { x: "100%" }
                : { y: "100%" }
            }
            animate={
              effectiveSide === "right"
                ? { x: 0 }
                : { y: 0 }
            }
            exit={
              effectiveSide === "right"
                ? { x: "100%" }
                : { y: "100%" }
            }
            transition={{ type: "spring", damping: 25, stiffness: 250 }}
            drag={effectiveSide === "bottom" ? "y" : false}
            dragConstraints={{ top: 0, bottom: 150 }}
            dragElastic={0.2}
            onDragEnd={(_, info) => {
              if (info.offset.y > 100) onClose();
            }}
          >
            {/* 手机端拖拽手柄 */}
            {effectiveSide === "bottom" && (
              <div className="flex justify-center pt-2 pb-1">
                <div className="h-1 w-10 rounded-full bg-[var(--muted)]" />
              </div>
            )}

            {/* 标题栏 */}
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

            {/* 内容 */}
            <div className="min-h-0 overflow-y-auto" style={{ height: "calc(100% - 52px)" }}>
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
