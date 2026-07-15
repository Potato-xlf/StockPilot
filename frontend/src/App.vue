<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const apiBase = import.meta.env.VITE_API_BASE_URL || ''
const loading = ref(true)
const error = ref('')
const overview = ref(null)
const quality = ref(null)
const universe = ref(null)
const sectors = ref([])
const syncRuns = ref({ data_runs: [], sector_runs: [] })
const sectorType = ref('industry')
const lastUpdated = ref('')
const sectorChart = ref(null)
let chart

async function get(path) {
  const response = await fetch(`${apiBase}${path}`)
  if (!response.ok) throw new Error(`${path} 请求失败（${response.status}）`)
  return response.json()
}

async function loadData() {
  loading.value = true; error.value = ''
  try {
    const [market, q, u, s, runs] = await Promise.all([
      get('/api/v1/market/overview'), get('/api/v1/data-quality/status'),
      get('/api/v1/universe/status'), get(`/api/v1/sectors/ranking?sector_type=${sectorType.value}&limit=10`),
      get('/api/v1/sync/runs?limit=8')
    ])
    overview.value = market; quality.value = q; universe.value = u; sectors.value = s.items || []; syncRuns.value = runs
    lastUpdated.value = new Date().toLocaleString('zh-CN', { hour12: false })
    await nextTick(); renderChart()
  } catch (e) { error.value = e.message || '数据加载失败' }
  finally { loading.value = false }
}

function renderChart() {
  if (!sectorChart.value || !sectors.value.length) return
  chart?.dispose(); chart = echarts.init(sectorChart.value)
  chart.setOption({
    grid: { left: 48, right: 18, top: 12, bottom: 28 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', axisLabel: { color: '#718096', formatter: '{value}%' } },
    yAxis: { type: 'category', inverse: true, data: sectors.value.map(x => x.name), axisLabel: { color: '#344054' } },
    series: [{ type: 'bar', barWidth: 14, data: sectors.value.map(x => ({ value: x.pct_change ?? 0, itemStyle: { color: (x.pct_change ?? 0) >= 0 ? '#ef6b73' : '#2fb48a' } })) }]
  })
}
watch(sectorType, loadData)
onMounted(loadData)

const statusLabel = computed(() => quality.value?.status === 'ok' ? '数据正常' : quality.value?.status === 'warning' ? '需要关注' : '数据异常')
const money = computed(() => overview.value?.total_amount == null ? '--' : `${(overview.value.total_amount / 1e8).toFixed(2)} 亿`)
const pct = (x) => x == null ? '--' : `${x >= 0 ? '+' : ''}${Number(x).toFixed(2)}%`
const date = (x) => x ? String(x).slice(0, 10) : '--'
</script>

<template>
  <main class="shell">
    <header class="topbar"><div><div class="brand">Stock<span>Pilot</span></div><div class="subtitle">A股市场数据驾驶舱</div></div><div class="actions"><span v-if="lastUpdated">更新于 {{ lastUpdated }}</span><button @click="loadData" :disabled="loading">{{ loading ? '加载中…' : '刷新数据' }}</button></div></header>
    <div v-if="error" class="alert">{{ error }} <button @click="loadData">重试</button></div>
    <section class="hero"><div><p class="eyebrow">MARKET OVERVIEW · {{ date(overview?.as_of) }}</p><h1>今天的市场表现</h1><p class="muted">基于当前已纳入管理的股票池统计，数据仅供研究参考。</p></div><div class="quality-pill" :class="quality?.status">● {{ statusLabel }}</div></section>
    <section class="metrics">
      <div class="metric"><span>上涨家数</span><strong class="up">{{ overview?.advancers ?? '--' }}</strong><small>下跌 {{ overview?.decliners ?? '--' }}</small></div>
      <div class="metric"><span>下跌家数</span><strong class="down">{{ overview?.decliners ?? '--' }}</strong><small>平盘 {{ overview?.unchanged ?? '--' }}</small></div>
      <div class="metric"><span>平均涨跌幅</span><strong :class="(overview?.average_pct_change ?? 0) >= 0 ? 'up' : 'down'">{{ pct(overview?.average_pct_change) }}</strong><small>涨跌比 {{ overview?.advance_decline_ratio?.toFixed(2) ?? '--' }}</small></div>
      <div class="metric"><span>成交额</span><strong>{{ money }}</strong><small>覆盖率 {{ overview?.amount_coverage_pct?.toFixed(1) ?? '--' }}%</small></div>
    </section>
    <section class="grid two"><article class="card"><div class="card-title"><div><h2>板块强弱排行</h2><p>按涨跌幅展示前 10 个板块</p></div><select v-model="sectorType"><option value="industry">行业</option><option value="concept">概念</option></select></div><div ref="sectorChart" class="chart"></div><div v-if="!sectors.length && !loading" class="empty">暂无板块数据</div></article><article class="card"><div class="card-title"><div><h2>数据质量</h2><p>行情数据覆盖与完整性</p></div><span class="tag" :class="quality?.status">{{ statusLabel }}</span></div><div class="quality-row"><span>行情覆盖</span><b>{{ quality?.coverage_pct?.toFixed(1) ?? '--' }}%</b></div><div class="progress"><i :style="{ width: `${quality?.coverage_pct || 0}%` }"></i></div><dl class="details"><div><dt>管理股票</dt><dd>{{ quality?.managed_stocks ?? '--' }}</dd></div><div><dt>已报价股票</dt><dd>{{ quality?.quoted_stocks ?? '--' }}</dd></div><div><dt>异常 OHLC</dt><dd>{{ quality?.invalid_ohlc_rows ?? '--' }}</dd></div><div><dt>成交额覆盖</dt><dd>{{ quality?.amount_coverage_pct?.toFixed(1) ?? '--' }}%</dd></div></dl><p class="message">{{ quality?.message || '等待数据加载…' }}</p></article></section>
    <section class="grid two lower"><article class="card"><div class="card-title"><div><h2>股票池</h2><p>当前纳入行情管理的范围</p></div></div><div class="universe"><strong>{{ universe?.total_listed_stocks ?? '--' }}</strong><span>上市股票</span><strong>{{ universe?.quote_enabled_stocks ?? '--' }}</strong><span>行情启用</span></div><div class="exchange" v-if="universe?.exchange_counts"><span v-for="(n, name) in universe.exchange_counts" :key="name">{{ name }} <b>{{ n }}</b></span></div></article><article class="card"><div class="card-title"><div><h2>最近同步任务</h2><p>数据流水线运行状态</p></div></div><div class="runs"><div v-for="run in [...syncRuns.data_runs, ...syncRuns.sector_runs].slice(0, 5)" :key="`${run.job_type || run.sector_type}-${run.id}`" class="run"><i :class="run.status"></i><span>{{ run.job_type || `${run.sector_type}板块` }}</span><b>{{ run.status }}</b><time>{{ date(run.finished_at || run.started_at) }}</time></div><div v-if="!syncRuns.data_runs.length && !syncRuns.sector_runs.length" class="empty">暂无同步记录</div></div></article></section>
    <footer>StockPilot 0.1 · 数据来源：AKShare · 仅供研究，不构成投资建议</footer>
  </main>
</template>
