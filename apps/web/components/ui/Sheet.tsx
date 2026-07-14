/**
 * Sheet/Drawer 组件
 * 桌面端: 右侧滑出面板 (Sheet)
 * 手机端: 底部弹出面板 (Drawer)
 * 支持拖拽关闭（手机端）
 */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  side?: "right" | "bottom";
  className?: string;
}

export function Sheet({
  open,
  onClose,
  title,
  children,
  side = "right",
  className,
}: SheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null);

  // ESC 键关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
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
              <h2 className="text-lg font-bold">{title}</h2>
              <button
                onClick={onClose}
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
