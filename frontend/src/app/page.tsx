"use client";

import React, { useEffect, useState } from "react";
import { Activity, Calendar, Sun, TrendingUp, Zap, RefreshCw, Plus, ArrowDown, Filter, Download, Search } from "lucide-react";
import OrbitingCirclesGlobeDemo from "@/components/ui/orbiting-circles-02";
import ReactECharts from "echarts-for-react";

export default function DashboardPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    fetch("http://localhost:8712/api/data")
      .then(r => r.json())
      .then(d => setData(d))
      .catch(e => console.error(e));
  }, []);

  return (
    <div className="min-h-screen relative pb-20 font-sans bg-[#f8f9fa] text-[#0c0c0e]">
      
      {/* Background with Orbiting Circles */}
      <div className="absolute top-0 left-0 right-0 h-[400px] overflow-hidden -z-10 bg-white/50 border-b border-zinc-200/50">
        <div className="absolute left-1/2 top-[-250px] h-[550px] w-[800px] -translate-x-1/2 rounded-full bg-emerald-300/[0.08] blur-[120px]"></div>
        <div className="absolute bottom-0 w-full">
           <OrbitingCirclesGlobeDemo />
        </div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#f8f9fa] pointer-events-none"></div>
      </div>

      <div className="max-w-[1600px] mx-auto p-4 sm:p-6 lg:p-8 pt-12 relative z-10">
        {/* Header */}
        <header className="rounded-2xl border border-white/60 bg-white/70 backdrop-blur-xl shadow-[0_12px_45px_rgba(0,0,0,0.07)] p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
          <div className="flex items-center gap-4">
            <div className="size-10 rounded-xl bg-gradient-to-br from-zinc-900 to-zinc-700 flex items-center justify-center text-white shadow-lg">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">Token 消耗实时看板</h1>
              <p className="text-sm text-zinc-500 font-medium tracking-tight">Unified AI Usage Intelligence</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/15 bg-emerald-500/[0.07] px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
              <span className="relative flex size-1.5">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-40"></span>
                <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500"></span>
              </span>
              LIVE
            </span>
            <div className="h-10 px-4 inline-flex items-center rounded-xl bg-white/75 border border-zinc-200 text-sm font-medium text-zinc-900 cursor-default">
              {data?.scope || "Workspace"}
            </div>
            
            <button className="flex w-10 h-10 items-center justify-center rounded-xl border border-zinc-200 bg-white/70 text-zinc-500 hover:bg-white hover:text-zinc-900 hover:shadow-sm transition-all">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button className="flex h-10 items-center justify-center gap-2 rounded-xl border border-transparent bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-800 transition-all">
              <Plus className="w-4 h-4" /> 手动上报
            </button>
          </div>
        </header>

        {/* Metric Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 mb-8">
          
          {/* Today */}
          <div className="relative overflow-hidden rounded-[20px] border border-zinc-200/60 bg-white/80 backdrop-blur-xl shadow-sm hover:shadow-md transition-all p-5 flex flex-col min-h-[184px]">
            <div className="flex items-start justify-between gap-4">
              <span className="text-[13px] font-medium text-zinc-500">今日消耗 TOKENS</span>
              <span className="flex size-9 items-center justify-center rounded-xl border border-emerald-500/10 bg-emerald-500/[0.06] text-emerald-600">
                <Sun className="w-4 h-4" />
              </span>
            </div>
            <div className="mt-auto">
              <div className="font-semibold tabular-nums text-[42px] leading-none tracking-[-0.055em] text-zinc-950 flex items-baseline gap-1">
                {data ? ((data.stats.today.input + data.stats.today.output)/1000).toFixed(1) : "0.0"}
                <span className="text-2xl text-zinc-400 font-medium">K</span>
              </div>
              <p className="mt-3 text-xs leading-5 text-zinc-400">in + out + cache · 仅真实 token</p>
            </div>
          </div>

          {/* Week */}
          <div className="relative overflow-hidden rounded-[20px] border border-zinc-200/60 bg-white/80 backdrop-blur-xl shadow-sm hover:shadow-md transition-all p-5 flex flex-col min-h-[184px]">
            <div className="flex items-start justify-between gap-4">
              <span className="text-[13px] font-medium text-zinc-500">本周消耗 TOKENS</span>
              <span className="flex size-9 items-center justify-center rounded-xl border border-zinc-200 bg-white text-zinc-600">
                <Calendar className="w-4 h-4" />
              </span>
            </div>
            <div className="mt-auto">
              <div className="font-semibold tabular-nums text-[42px] leading-none tracking-[-0.055em] text-zinc-950 flex items-baseline gap-1">
                {data ? ((data.stats.week.input + data.stats.week.output)/1000).toFixed(1) : "0.0"}
                <span className="text-2xl text-zinc-400 font-medium">K</span>
              </div>
              <p className="mt-3 text-xs leading-5 text-zinc-400">近 7 日累计 · 无价格估算</p>
            </div>
          </div>

          {/* Total */}
          <div className="relative overflow-hidden rounded-[20px] border border-zinc-200/60 bg-white/80 backdrop-blur-xl shadow-sm hover:shadow-md transition-all p-5 flex flex-col min-h-[184px]">
            <div className="flex items-start justify-between gap-4">
              <span className="text-[13px] font-medium text-zinc-500">累计消耗 TOKENS</span>
              <span className="flex size-9 items-center justify-center rounded-xl border border-zinc-200 bg-white text-zinc-600">
                <TrendingUp className="w-4 h-4" />
              </span>
            </div>
            <div className="mt-auto">
              <div className="font-semibold tabular-nums text-[42px] leading-none tracking-[-0.055em] text-zinc-950 flex items-baseline gap-1">
                {data ? ((data.stats.all.input + data.stats.all.output)/1000).toFixed(1) : "0.0"}
                <span className="text-2xl text-zinc-400 font-medium">K</span>
              </div>
              <p className="mt-3 text-xs leading-5 text-zinc-400">全部历史 · 源端真实用量</p>
            </div>
          </div>

          {/* Cache */}
          <div className="relative overflow-hidden rounded-[20px] border border-zinc-200/60 bg-white/80 backdrop-blur-xl shadow-sm hover:shadow-md transition-all p-5 flex flex-col min-h-[184px]">
            <div className="flex items-start justify-between gap-4">
              <span className="text-[13px] font-medium text-zinc-500">缓存与推理 TOKENS</span>
              <span className="flex size-9 items-center justify-center rounded-xl border border-emerald-500/10 bg-emerald-500/[0.06] text-emerald-600">
                <Zap className="w-4 h-4" />
              </span>
            </div>
            <div className="mt-auto">
              <div className="font-semibold tabular-nums text-[28px] leading-none tracking-[-0.03em] text-zinc-950">
                {data ? `${(data.stats.all.cache / 1000).toFixed(1)}K` : "无缓存"}
              </div>
              <div className="flex items-center gap-4 mt-3">
                 <div className="text-xs text-zinc-400">缓存占比 <span className="text-emerald-600 font-medium ml-1">{data?.stats?.all?.hit_rate || 0}%</span></div>
                 <div className="text-xs text-zinc-400 bg-zinc-100 px-2 py-0.5 rounded">理 {data?.stats?.all?.reasoning || 0}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Charts & Details Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <div className="relative overflow-hidden rounded-[20px] border border-zinc-200/60 bg-white/80 backdrop-blur-xl shadow-sm p-5">
            <h3 className="font-medium text-sm text-zinc-500 mb-6">24 小时消耗趋势 <span className="text-xs font-normal text-zinc-400 ml-2">输入 / 输出 堆叠分布</span></h3>
            <div className="w-full h-[280px] bg-zinc-50 rounded-xl flex items-center justify-center text-zinc-400 text-sm">
              [ 24小时趋势 ECharts 区域 ]
            </div>
          </div>
          <div className="relative overflow-hidden rounded-[20px] border border-zinc-200/60 bg-white/80 backdrop-blur-xl shadow-sm p-5">
            <h3 className="font-medium text-sm text-zinc-500 mb-6">7 天消耗分布 <span className="text-xs font-normal text-zinc-400 ml-2">每日 Token 总用量</span></h3>
            <div className="w-full h-[280px] bg-zinc-50 rounded-xl flex items-center justify-center text-zinc-400 text-sm">
              [ 7天分布 ECharts 区域 ]
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
