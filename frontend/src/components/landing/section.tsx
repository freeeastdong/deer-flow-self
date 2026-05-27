"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/utils";

export function Section({
  className,
  title,
  subtitle,
  children,
}: {
  className?: string;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <motion.section
      className={cn("mx-auto flex flex-col py-16", className)}
      initial={{ opacity: 0, y: 60 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.7, ease: "easeOut" }}
    >
      <header className="flex flex-col items-center justify-between">
        <div className="mb-4 bg-linear-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-center text-5xl font-bold text-transparent">
          {title}
        </div>
        {subtitle && (
          <div className="text-muted-foreground text-center text-xl">
            {subtitle}
          </div>
        )}
      </header>
      <main className="mt-4">{children}</main>
    </motion.section>
  );
}
