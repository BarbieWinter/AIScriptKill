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

function tabbableElements(scope: HTMLElement) {
  const candidates = Array.from(scope.querySelectorAll<HTMLElement>(
    'button, a[href], input, textarea, select, [tabindex]:not([tabindex="-1"])',
  )).filter(
    (element) =>
      !element.matches(":disabled")
      && element.tabIndex >= 0
      && element.getClientRects().length > 0,
  );

  return candidates.filter((element, index) => {
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
    const checked = group.find((radio) => radio.checked);
    return checked ? element === checked : element === group[0] && index === candidates.indexOf(group[0]);
  });
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
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const fallbackFocus = fallbackFocusRef?.current;
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      const previousFocus = previousFocusRef.current;
      previousFocusRef.current = null;
      const focusTarget = previousFocus?.isConnected && !previousFocus.matches(":disabled")
        ? previousFocus
        : fallbackFocus;
      if (focusTarget?.isConnected) focusTarget.focus();
    };
  }, [fallbackFocusRef, open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const root = rootRef.current;
      const sheet = sheetRef.current;
      if (!root || !sheet) return;
      const nestedScope = root.querySelector<HTMLElement>('[data-sheet-focus-scope="active"]');
      const focusScope = nestedScope ?? sheet;

      if (event.key === "Escape") {
        event.preventDefault();
        const nestedDismiss = nestedScope?.querySelector<HTMLElement>("[data-sheet-dismiss]");
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

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const activeElement = document.activeElement;
      if (!focusScope.contains(activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
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

  if (!open) return null;

  return (
    <div ref={rootRef}>
      {/* 遮罩层 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 面板 */}
      <motion.div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
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
          {banner}
          {children}
        </div>
      </motion.div>
      {overlay}
    </div>
  );
}
