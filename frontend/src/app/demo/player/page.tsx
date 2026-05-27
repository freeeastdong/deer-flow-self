"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
  ListMusic,
  ChevronDown,
  ChevronUp,
  Music,
  Repeat,
  Repeat1,
  Shuffle,
  X,
  Plus,
  GripHorizontal,
} from "lucide-react";

// ============================================================
// DeerFlow Workspace 悬浮迷你播放器 Demo
// 访问路径：http://localhost:3000/demo/player
// ============================================================

type Track = {
  id: string;
  name: string;
  url: string;
  duration: number;
};

type LoopMode = "all" | "one" | "shuffle";

export default function PlayerDemoPage() {
  return (
    <div className="relative h-screen w-full bg-[#0a0a0a] text-white overflow-hidden">
      {/* 模拟 Workspace 背景内容 */}
      <MockWorkspace />

      {/* 悬浮迷你播放器 */}
      <MiniPlayer />
    </div>
  );
}

/* ============================================================
   模拟 Workspace 背景（让 demo 更有真实感）
   ============================================================ */
function MockWorkspace() {
  return (
    <div className="flex h-full w-full">
      {/* 侧边栏 */}
      <div className="w-64 h-full border-r border-white/5 bg-[#0f0f0f] p-4 hidden md:block">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-blue-500" />
          <span className="font-bold text-lg">DeerFlow</span>
        </div>
        <div className="space-y-2">
          {["Chats", "Agents", "Skills", "Applications"].map((item) => (
            <div
              key={item}
              className="px-3 py-2 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/5 transition-colors text-sm"
            >
              {item}
            </div>
          ))}
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col">
        <div className="h-16 border-b border-white/5 flex items-center px-6 justify-between">
          <span className="text-white/60 text-sm">Workspace / Chats</span>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-white/10" />
          </div>
        </div>
        <div className="flex-1 p-8 overflow-auto">
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="h-32 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-center">
              <span className="text-white/20 text-sm">Chat Area</span>
            </div>
            <div className="h-64 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-center">
              <span className="text-white/20 text-sm">
                右下角悬浮播放器即为本 Demo 要展示的效果
              </span>
            </div>
            <div className="h-48 rounded-2xl bg-white/[0.02] border border-white/5" />
            <div className="h-48 rounded-2xl bg-white/[0.02] border border-white/5" />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   悬浮迷你播放器组件
   ============================================================ */
function MiniPlayer() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  const [tracks, setTracks] = useState<Track[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [isMuted, setIsMuted] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [showPlaylist, setShowPlaylist] = useState(false);
  const [loopMode, setLoopMode] = useState<LoopMode>("all");

  const currentTrack = tracks[currentIndex];

  // 格式化时间 mm:ss
  const formatTime = (t: number) => {
    if (!isFinite(t) || isNaN(t)) return "0:00";
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  // 添加本地文件
  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;

      const newTracks: Track[] = files.map((file) => ({
        id: Math.random().toString(36).slice(2),
        name: file.name.replace(/\.[^/.]+$/, ""),
        url: URL.createObjectURL(file),
        duration: 0,
      }));

      setTracks((prev) => {
        const combined = [...prev, ...newTracks];
        // 如果是第一首歌，自动开始播放
        if (prev.length === 0 && combined.length > 0) {
          setTimeout(() => setIsPlaying(true), 100);
        }
        return combined;
      });

      // 清空 input 允许重复选同一文件
      e.target.value = "";
    },
    []
  );

  // 播放/暂停
  const togglePlay = useCallback(() => {
    if (!currentTrack) return;
    setIsPlaying((p) => !p);
  }, [currentTrack]);

  // 播放指定索引
  const playIndex = useCallback((index: number) => {
    setCurrentIndex(index);
    setIsPlaying(true);
  }, []);

  // 下一首
  const playNext = useCallback(() => {
    if (tracks.length === 0) return;
    if (loopMode === "shuffle") {
      const next = Math.floor(Math.random() * tracks.length);
      setCurrentIndex(next);
    } else {
      setCurrentIndex((i) => (i + 1) % tracks.length);
    }
    setIsPlaying(true);
  }, [tracks.length, loopMode]);

  // 上一首
  const playPrev = useCallback(() => {
    if (tracks.length === 0) return;
    setCurrentIndex((i) => (i - 1 + tracks.length) % tracks.length);
    setIsPlaying(true);
  }, [tracks.length]);

  // 切换循环模式
  const cycleLoopMode = useCallback(() => {
    setLoopMode((m) => (m === "all" ? "one" : m === "one" ? "shuffle" : "all"));
  }, []);

  // 进度条点击跳转
  const handleSeek = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!audioRef.current || !progressRef.current || !duration) return;
      const rect = progressRef.current.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      audioRef.current.currentTime = ratio * duration;
      setCurrentTime(ratio * duration);
    },
    [duration]
  );

  // 音量控制
  const handleVolumeChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = parseFloat(e.target.value);
      setVolume(v);
      setIsMuted(v === 0);
      if (audioRef.current) audioRef.current.volume = v;
    },
    []
  );

  // 删除曲目
  const removeTrack = useCallback(
    (index: number) => {
      setTracks((prev) => {
        const track = prev[index];
        if (track) URL.revokeObjectURL(track.url);
        const next = prev.filter((_, i) => i !== index);
        if (index === currentIndex) {
          setIsPlaying(false);
          setCurrentTime(0);
          if (next.length > 0) {
            setCurrentIndex(Math.min(index, next.length - 1));
          }
        } else if (index < currentIndex) {
          setCurrentIndex((i) => i - 1);
        }
        return next;
      });
    },
    [currentIndex]
  );

  // Audio 事件监听
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
    const onLoadedMetadata = () => setDuration(audio.duration || 0);
    const onEnded = () => {
      if (loopMode === "one") {
        audio.currentTime = 0;
        audio.play();
      } else {
        playNext();
      }
    };

    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("ended", onEnded);

    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("ended", onEnded);
    };
  }, [loopMode, playNext]);

  // 播放/暂停控制
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !currentTrack) return;
    if (audio.src !== currentTrack.url) {
      audio.src = currentTrack.url;
      audio.load();
    }
    if (isPlaying) {
      audio.play().catch(() => setIsPlaying(false));
    } else {
      audio.pause();
    }
  }, [isPlaying, currentTrack]);

  // 静音切换
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.muted = isMuted;
    }
  }, [isMuted]);

  // 组件卸载时清理 URL
  useEffect(() => {
    return () => {
      tracks.forEach((t) => URL.revokeObjectURL(t.url));
    };
  }, []);

  const progressPercent = duration ? (currentTime / duration) * 100 : 0;

  return (
    <>
      <audio ref={audioRef} preload="metadata" />

      {/* 文件选择器（隐藏） */}
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleFileSelect}
      />

      <motion.div
        className="fixed bottom-4 right-4 z-50 flex flex-col items-end cursor-grab active:cursor-grabbing"
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.5 }}
        drag
        dragMomentum={false}
        dragElastic={0}
        whileDrag={{ scale: 1.02 }}
        dragConstraints={{ left: -window.innerWidth + 340, right: 0, top: -window.innerHeight + 420, bottom: 0 }}
      >
        <AnimatePresence>
          {/* 展开面板 */}
          {isExpanded && (
            <motion.div
              key="panel"
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.95 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
              className="mb-3 w-80 rounded-2xl border border-white/10 bg-[#0f0f0f]/90 backdrop-blur-xl shadow-2xl shadow-black/50 overflow-hidden"
            >
              {/* 拖拽手柄 */}
              <div className="flex justify-center pt-2 pb-1">
                <GripHorizontal className="size-4 text-white/20" />
              </div>

              {/* 专辑封面区 */}
              <div className="relative p-5 pt-2 pb-3">
                <div className="flex items-center gap-4">
                  <div className="relative size-16 shrink-0 rounded-xl overflow-hidden bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-white/10 flex items-center justify-center">
                    {currentTrack ? (
                      <Music className="size-7 text-purple-300/60" />
                    ) : (
                      <Music className="size-7 text-white/20" />
                    )}
                    {isPlaying && (
                      <div className="absolute inset-0 flex items-end justify-center gap-0.5 pb-2">
                        {[0, 1, 2, 3].map((i) => (
                          <motion.div
                            key={i}
                            className="w-1 bg-purple-400/60 rounded-full"
                            animate={{
                              height: [4, 14, 6, 18, 4],
                            }}
                            transition={{
                              duration: 1.2,
                              repeat: Infinity,
                              delay: i * 0.15,
                              ease: "easeInOut",
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-white/90 truncate">
                      {currentTrack?.name || "未选择音乐"}
                    </div>
                    <div className="text-xs text-white/30 mt-0.5 truncate">
                      {currentTrack
                        ? `${formatTime(currentTime)} / ${formatTime(duration)}`
                        : "点击 + 添加本地音乐"}
                    </div>
                  </div>
                </div>

                {/* 进度条 */}
                <div
                  ref={progressRef}
                  className="mt-4 h-1 rounded-full bg-white/10 cursor-pointer group"
                  onClick={handleSeek}
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-purple-400 to-blue-400 relative"
                    style={{ width: `${progressPercent}%` }}
                  >
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white shadow opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>
              </div>

              {/* 控制按钮区 */}
              <div className="px-5 pb-3 flex items-center justify-between">
                <div className="flex items-center gap-1">
                  <button
                    onClick={cycleLoopMode}
                    className="p-2 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/5 transition-colors"
                    title="循环模式"
                  >
                    {loopMode === "all" && <Repeat className="size-4" />}
                    {loopMode === "one" && <Repeat1 className="size-4" />}
                    {loopMode === "shuffle" && <Shuffle className="size-4" />}
                  </button>
                  <button
                    onClick={() => setShowPlaylist((s) => !s)}
                    className={`p-2 rounded-lg transition-colors ${
                      showPlaylist
                        ? "text-purple-300 bg-purple-500/10"
                        : "text-white/30 hover:text-white/70 hover:bg-white/5"
                    }`}
                    title="播放列表"
                  >
                    <ListMusic className="size-4" />
                  </button>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={playPrev}
                    disabled={tracks.length === 0}
                    className="p-2 rounded-lg text-white/40 hover:text-white/90 hover:bg-white/5 transition-colors disabled:opacity-20"
                  >
                    <SkipBack className="size-4" />
                  </button>
                  <button
                    onClick={togglePlay}
                    disabled={!currentTrack}
                    className="p-2.5 rounded-full bg-white text-black hover:bg-white/90 transition-colors disabled:opacity-30"
                  >
                    {isPlaying ? (
                      <Pause className="size-4 fill-current" />
                    ) : (
                      <Play className="size-4 fill-current ml-0.5" />
                    )}
                  </button>
                  <button
                    onClick={playNext}
                    disabled={tracks.length === 0}
                    className="p-2 rounded-lg text-white/40 hover:text-white/90 hover:bg-white/5 transition-colors disabled:opacity-20"
                  >
                    <SkipForward className="size-4" />
                  </button>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setIsMuted((m) => !m)}
                    className="p-2 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/5 transition-colors"
                  >
                    {isMuted || volume === 0 ? (
                      <VolumeX className="size-4" />
                    ) : (
                      <Volume2 className="size-4" />
                    )}
                  </button>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={isMuted ? 0 : volume}
                    onChange={handleVolumeChange}
                    onPointerDown={(e) => e.stopPropagation()}
                    className="w-16 h-1 accent-purple-400 cursor-pointer"
                  />
                </div>
              </div>

              {/* 播放列表 */}
              <AnimatePresence>
                {showPlaylist && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden border-t border-white/5"
                  >
                    <div className="max-h-48 overflow-auto py-2">
                      {tracks.length === 0 ? (
                        <div className="px-5 py-4 text-center text-xs text-white/20">
                          播放列表为空，点击下方 + 添加音乐
                        </div>
                      ) : (
                        tracks.map((track, i) => (
                          <div
                            key={track.id}
                            onClick={() => playIndex(i)}
                            className={`flex items-center gap-3 px-5 py-2 cursor-pointer transition-colors group ${
                              i === currentIndex
                                ? "bg-white/5 text-purple-300"
                                : "text-white/40 hover:text-white/70 hover:bg-white/[0.02]"
                            }`}
                          >
                            <span className="text-[10px] w-4 text-center opacity-30">
                              {i === currentIndex && isPlaying ? (
                                <span className="inline-block animate-pulse">▶</span>
                              ) : (
                                i + 1
                              )}
                            </span>
                            <span className="text-xs truncate flex-1">
                              {track.name}
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                removeTrack(i);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/10 transition-opacity"
                            >
                              <X className="size-3" />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* 底部操作栏 */}
              <div className="px-4 py-2.5 border-t border-white/5 flex items-center justify-between bg-white/[0.02]">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-white/40 hover:text-white/80 hover:bg-white/5 transition-colors"
                >
                  <Plus className="size-3.5" />
                  添加音乐
                </button>
                <button
                  onClick={() => setIsExpanded(false)}
                  className="p-1.5 rounded-lg text-white/20 hover:text-white/60 hover:bg-white/5 transition-colors"
                >
                  <ChevronDown className="size-4" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 迷你条（收起状态） */}
        {!isExpanded && (
          <motion.button
            layout
            onClick={() => setIsExpanded(true)}
            className="flex items-center gap-3 pl-3 pr-4 py-2.5 rounded-full border border-white/10 bg-[#0f0f0f]/90 backdrop-blur-xl shadow-xl shadow-black/40 hover:border-white/20 transition-colors"
          >
            <div className="relative size-9 rounded-lg overflow-hidden bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-white/10 flex items-center justify-center shrink-0">
              {currentTrack ? (
                <Music className="size-4 text-purple-300/60" />
              ) : (
                <Music className="size-4 text-white/20" />
              )}
              {isPlaying && (
                <div className="absolute inset-0 flex items-end justify-center gap-[2px] pb-1.5">
                  {[0, 1, 2].map((i) => (
                    <motion.div
                      key={i}
                      className="w-[3px] bg-purple-400/70 rounded-full"
                      animate={{ height: [3, 10, 4, 12, 3] }}
                      transition={{
                        duration: 1,
                        repeat: Infinity,
                        delay: i * 0.12,
                        ease: "easeInOut",
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
            <div className="text-left min-w-0">
              <div className="text-xs font-medium text-white/80 truncate max-w-[120px]">
                {currentTrack?.name || "迷你播放器"}
              </div>
              <div className="text-[10px] text-white/30">
                {currentTrack
                  ? isPlaying
                    ? "正在播放"
                    : "已暂停"
                  : "点击展开"}
              </div>
            </div>
            <div className="flex items-center gap-1 ml-1">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  togglePlay();
                }}
                disabled={!currentTrack}
                className="p-1.5 rounded-full bg-white text-black hover:bg-white/90 transition-colors disabled:opacity-30"
              >
                {isPlaying ? (
                  <Pause className="size-3 fill-current" />
                ) : (
                  <Play className="size-3 fill-current ml-[1px]" />
                )}
              </button>
            </div>
          </motion.button>
        )}
      </motion.div>
    </>
  );
}
