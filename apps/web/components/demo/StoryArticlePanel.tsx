"use client";

import { motion } from "framer-motion";
import { BookOpen, Clock3, X } from "lucide-react";

import type { DemoArticle } from "@/lib/demo-data";

interface StoryArticlePanelProps {
  article: DemoArticle;
  onClose: () => void;
}

export function StoryArticlePanel({ article, onClose }: StoryArticlePanelProps) {
  return (
    <motion.aside
      initial={{ opacity: 0, x: 36 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 36 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="demo-article-panel"
      aria-label={article.title}
    >
      <div className="demo-article-grain" />
      <header className="demo-article-header">
        <div>
          <p className="demo-article-eyebrow">{article.eyebrow}</p>
          <h2>{article.title}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭文章">
          <X aria-hidden="true" />
        </button>
      </header>

      <div className="demo-article-meta">
        <span><BookOpen aria-hidden="true" /> 已收入手记</span>
        <span><Clock3 aria-hidden="true" /> {article.readTime}</span>
      </div>

      <p className="demo-article-summary">{article.summary}</p>

      <article className="demo-article-body">
        {article.content.map((block, index) => {
          if (block.type === "quote") {
            return <blockquote key={`${block.type}-${index}`}>{block.text}</blockquote>;
          }
          if (block.type === "note") {
            return (
              <section key={`${block.type}-${index}`} className="demo-article-note">
                <span>{block.label}</span>
                <p>{block.text}</p>
              </section>
            );
          }
          return <p key={`${block.type}-${index}`}>{block.text}</p>;
        })}
      </article>

      <footer className="demo-article-footer">
        <span>DEMO / 本地静态内容</span>
        <span>ESC 关闭</span>
      </footer>
    </motion.aside>
  );
}
