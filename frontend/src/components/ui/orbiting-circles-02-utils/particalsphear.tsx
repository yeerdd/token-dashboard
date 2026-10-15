"use client";

import React from "react";

export default function ParticleSphereAnimation() {
  return (
    <div className="relative w-full h-full rounded-full border border-emerald-500/30 flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-400 to-emerald-600 opacity-20 blur-xl animate-pulse"></div>
      <div className="absolute inset-0 rounded-full border-[0.5px] border-emerald-400/20" style={{ transform: 'rotateX(60deg)' }}></div>
      <div className="absolute inset-0 rounded-full border-[0.5px] border-emerald-400/20" style={{ transform: 'rotateY(60deg)' }}></div>
    </div>
  );
}
