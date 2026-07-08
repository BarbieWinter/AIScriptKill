import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Tailwind CSS 类名合并工具
 * 合并冲突类名，后者覆盖前者
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
