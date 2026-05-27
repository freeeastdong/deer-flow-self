"use client";

const skills = [
  "Deep Research",
  "Vibe Coding",
  "Generate Images",
  "Generate Videos",
  "Generate Slides",
  "Generate Songs",
  "Data Analysis",
  "Webpage Generation",
  "Podcast Creation",
  "Email Organization",
  "Agent Orchestration",
  "Sandbox Execution",
];

const items = [...skills, ...skills];

function SkillTag({
  label,
  variant = "primary",
}: {
  label: string;
  variant?: "primary" | "secondary";
}) {
  const isPrimary = variant === "primary";
  return (
    <span
      className={`
        inline-flex items-center whitespace-nowrap rounded-full px-5 py-2 text-sm
        border backdrop-blur-sm transition-colors select-none
        ${
          isPrimary
            ? "border-white/10 bg-white/5 text-white/80 hover:bg-white/10"
            : "border-purple-500/20 bg-purple-500/5 text-purple-200/80 hover:bg-purple-500/10"
        }
      `}
    >
      {label}
    </span>
  );
}

export function MarqueeSkillsSection() {
  return (
    <section className="relative py-16 overflow-hidden border-y border-white/5">
      {/* 左侧渐变遮罩 */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-24 z-10 bg-gradient-to-r from-[#0a0a0a] to-transparent" />
      {/* 右侧渐变遮罩 */}
      <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-24 z-10 bg-gradient-to-l from-[#0a0a0a] to-transparent" />

      <div className="mb-6 text-center">
        <p className="text-xs uppercase tracking-widest text-white/30">
          Agent Skills
        </p>
      </div>

      {/* 第一行：向左滚动 */}
      <div className="relative flex overflow-hidden mb-4">
        <div
          className="flex shrink-0 gap-4 pr-4"
          style={{ animation: "marquee-left 30s linear infinite" }}
        >
          {items.map((skill, i) => (
            <SkillTag key={`a-${i}`} label={skill} />
          ))}
        </div>
      </div>

      {/* 第二行：向右滚动（反向） */}
      <div className="relative flex overflow-hidden">
        <div
          className="flex shrink-0 gap-4 pr-4"
          style={{ animation: "marquee-right 35s linear infinite" }}
        >
          {[...items].reverse().map((skill, i) => (
            <SkillTag key={`b-${i}`} label={skill} variant="secondary" />
          ))}
        </div>
      </div>
    </section>
  );
}
