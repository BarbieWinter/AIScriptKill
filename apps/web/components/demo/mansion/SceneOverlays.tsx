"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, X } from "lucide-react";
import type { ReactNode } from "react";

import {
  demoArticles,
  demoRooms,
  type DemoArticle,
  type DemoPoint,
} from "@/lib/demo-data";

import { pointToMapStyle, rectToMapStyle } from "./mapProjection";

function SceneOverlay({
  children,
  className,
  eyebrow,
  onClose,
  open,
  title,
}: {
  children: ReactNode;
  className: string;
  eyebrow: string;
  onClose: () => void;
  open: boolean;
  title: string;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="demo-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.section
            className={className}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div><span>{eyebrow}</span><h2>{title}</h2></div>
              <button type="button" aria-label="关闭" onClick={onClose}><X /></button>
            </header>
            {children}
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** 全屏弹层：手记列表 */
export function JournalOverlay({
  open,
  onClose,
  onSelectArticle,
}: {
  open: boolean;
  onClose: () => void;
  onSelectArticle: (article: DemoArticle) => void;
}) {
  return (
    <SceneOverlay
      open={open}
      onClose={onClose}
      className="demo-journal"
      eyebrow="静态数据组件"
      title="已发现的手记"
    >
      <div className="demo-journal-list">
        {demoArticles.map((article, index) => (
          <button type="button" key={article.id} onClick={() => onSelectArticle(article)}>
            <span>0{index + 1}</span>
            <div><strong>{article.title}</strong><p>{article.summary}</p></div>
            <ChevronRight />
          </button>
        ))}
      </div>
    </SceneOverlay>
  );
}

/** 全屏弹层：区域概览地图 */
export function MapOverlay({
  open,
  onClose,
  player,
}: {
  open: boolean;
  onClose: () => void;
  player: DemoPoint;
}) {
  return (
    <SceneOverlay
      open={open}
      onClose={onClose}
      className="demo-map-panel"
      eyebrow="区域概览"
      title="旧剧场一层"
    >
      <div className="demo-mini-map">
        {demoRooms.map((room) => (
          <div key={room.id} className="mini-room" style={rectToMapStyle(room.bounds)}>
            {room.name}
          </div>
        ))}
        <span style={pointToMapStyle(player)} />
      </div>
      <p>这是用于确认空间比例与操作方式的通用封闭舞台，不包含任务或后端状态。</p>
    </SceneOverlay>
  );
}
