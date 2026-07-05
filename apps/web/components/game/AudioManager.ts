/**
 * AudioManager - Howler.js 5 层音频系统
 *
 * 层级 0: Ambient (环境音)   → 始终循环，低音量 0.2
 * 层级 1: BGM (场景音乐)    → 按场景切换，中音量 0.35
 * 层级 2: Story (剧情音频)  → 单次播放，高音量 0.7
 * 层级 3: Voice (语音/TTS)  → 单次播放，中音量 0.5
 * 层级 4: SFX (音效)        → 瞬间播放，中低音量 0.4
 *
 * 每个层级独立控制音量/播放状态
 */

"use client";

import { Howl } from "howler";

interface AudioLayer {
  howl: Howl | null;
  volume: number;
  state: "idle" | "playing" | "paused";
}

class AudioManagerClass {
  private layers: AudioLayer[] = [
    { howl: null, volume: 0.2, state: "idle" },  // 0: Ambient
    { howl: null, volume: 0.35, state: "idle" }, // 1: BGM
    { howl: null, volume: 0.7, state: "idle" },  // 2: Story
    { howl: null, volume: 0.5, state: "idle" },  // 3: Voice
    { howl: null, volume: 0.4, state: "idle" },  // 4: SFX
  ];

  private masterVolume = 0.8;
  private onStateChange?: (layer: number, state: string) => void;

  constructor() {}

  setOnStateChange(cb: (layer: number, state: string) => void) {
    this.onStateChange = cb;
  }

  /** 设置主音量 */
  setMasterVolume(v: number) {
    this.masterVolume = Math.max(0, Math.min(1, v));
    this.layers.forEach((layer) => {
      layer.howl?.volume(layer.volume * this.masterVolume);
    });
  }

  /** 设置指定层级音量 */
  setLayerVolume(layerIdx: number, v: number) {
    if (layerIdx < 0 || layerIdx >= this.layers.length) return;
    const layer = this.layers[layerIdx];
    layer.volume = Math.max(0, Math.min(1, v));
    layer.howl?.volume(layer.volume * this.masterVolume);
  }

  /** 播放或切换 BGM（淡入淡出过渡） */
  crossfadeBGM(assetUrl: string, fadeDuration = 2) {
    const bgmLayer = this.layers[1];

    // 停止当前 BGM
    if (bgmLayer.howl) {
      const oldHowl = bgmLayer.howl;
      const oldVol = bgmLayer.volume * this.masterVolume;
      // 淡出
      const fadeSteps = 20;
      const interval = (fadeDuration * 1000) / fadeSteps;
      let step = 0;
      const fadeOut = setInterval(() => {
        step++;
        const vol = oldVol * (1 - step / fadeSteps);
        oldHowl.volume(Math.max(0, vol));
        if (step >= fadeSteps) {
          clearInterval(fadeOut);
          oldHowl.stop();
          oldHowl.unload();
        }
      }, interval);
    }

    // 播放新 BGM
    const howl = new Howl({
      src: [assetUrl],
      loop: true,
      volume: 0, // 从静音开始淡入
      onload: () => {
        // 淡入
        const targetVol = bgmLayer.volume * this.masterVolume;
        const fadeSteps = 20;
        const interval = (fadeDuration * 1000) / fadeSteps;
        let step = 0;
        const fadeIn = setInterval(() => {
          step++;
          howl.volume(targetVol * (step / fadeSteps));
          if (step >= fadeSteps) {
            clearInterval(fadeIn);
            this.onStateChange?.(1, "playing");
          }
        }, interval);
      },
    });

    howl.play();
    bgmLayer.howl = howl;
    bgmLayer.state = "playing";
  }

  /** 播放剧情音频（单次） */
  playStory(assetUrl: string, onEnd?: () => void) {
    const storyLayer = this.layers[2];

    // 停止之前的剧情音频
    if (storyLayer.howl) {
      storyLayer.howl.stop();
      storyLayer.howl.unload();
    }

    const howl = new Howl({
      src: [assetUrl],
      loop: false,
      volume: storyLayer.volume * this.masterVolume,
      onplay: () => {
        this.onStateChange?.(2, "playing");
      },
      onend: () => {
        this.onStateChange?.(2, "idle");
        onEnd?.();
      },
    });

    howl.play();
    storyLayer.howl = howl;
    storyLayer.state = "playing";
  }

  /** 播放音效 */
  playSFX(assetUrl: string) {
    const sfxLayer = this.layers[4];
    const howl = new Howl({
      src: [assetUrl],
      loop: false,
      volume: sfxLayer.volume * this.masterVolume,
    });
    howl.play();
  }

  /** 暂停所有 */
  pauseAll() {
    this.layers.forEach((layer) => {
      if (layer.howl && layer.state === "playing") {
        layer.howl.pause();
        layer.state = "paused";
      }
    });
  }

  /** 恢复所有 */
  resumeAll() {
    this.layers.forEach((layer) => {
      if (layer.howl && layer.state === "paused") {
        layer.howl.play();
        layer.state = "playing";
      }
    });
  }

  /** 停止所有 */
  stopAll() {
    this.layers.forEach((layer) => {
      layer.howl?.stop();
      layer.howl?.unload();
      layer.howl = null;
      layer.state = "idle";
    });
  }

  /** 获取当前播放曲目信息 */
  getCurrentTrack() {
    return this.layers[1].howl ? "BGM 播放中" : null;
  }
}

export const audioManager = new AudioManagerClass();
