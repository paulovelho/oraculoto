<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Frequency } from '@/api'
import { formatBall, formatDecimal, formatInt } from '@/lib/format'
import { fairBand } from '@/lib/stats'
import type { BallRules } from '@/lib/statsQuery'

// Two views of the same counts. "map": a 10-per-row grid (like the ball picker) shaded from faded
// to full green by how often each ball came out; balls outside the fair band get a gold ring.
// "bars": 60 bars in ball order, the fair-draw expectation as a line and its exact binomial band
// behind them (docs/web.md §5: hand-written SVG, never a number without its baseline).
const props = withDefaults(defineProps<{ data: Frequency; rules: BallRules; view?: 'map' | 'bars' }>(), {
  view: 'map',
})

const HEIGHT = 240
const M = { top: 12, right: 8, bottom: 24, left: 36 }

const box = ref<HTMLElement | null>(null)
const width = ref(640)
let observer: ResizeObserver | null = null
onMounted(() => {
  if (!box.value) return
  observer = new ResizeObserver(([entry]) => {
    if (entry) width.value = Math.max(280, Math.floor(entry.contentRect.width))
  })
  observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

const pool = computed(() => props.rules.ball_max - props.rules.ball_min + 1)
const byBall = computed(() => [...props.data.items].sort((a, b) => a.ball - b.ball))
const band = computed(() => fairBand(props.data.window.draws, props.rules.balls_drawn, pool.value))

function niceStep(raw: number): number {
  const mag = 10 ** Math.floor(Math.log10(raw))
  const f = raw / mag
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * mag
}

const chart = computed(() => {
  const top = Math.max(1, band.value.high, ...byBall.value.map((i) => i.times))
  const step = niceStep(top / 4)
  const yMax = Math.ceil((top * 1.05) / step) * step
  const plotW = width.value - M.left - M.right
  const plotH = HEIGHT - M.top - M.bottom
  const slot = plotW / byBall.value.length
  const y = (v: number) => M.top + plotH - (v / yMax) * plotH
  const ticks: number[] = []
  for (let v = 0; v <= yMax + 1e-9; v += step) ticks.push(v)
  const labelEvery = width.value < 480 ? 10 : 5
  return {
    y,
    slot,
    plotW,
    ticks,
    bars: byBall.value.map((item, i) => ({
      ...item,
      x: M.left + i * slot + slot * 0.15,
      w: Math.max(1, slot * 0.7),
      y: y(item.times),
      h: y(0) - y(item.times),
      label: item.ball === props.rules.ball_min || item.ball % labelEvery === 0,
    })),
  }
})

const outside = computed(
  () => props.data.items.filter((i) => i.times < band.value.low || i.times > band.value.high).length,
)
const outsideExpected = computed(() => pool.value * band.value.outside)

const hover = ref<number | null>(null)
function pick(event: PointerEvent) {
  const svg = event.currentTarget as SVGSVGElement
  const x = event.clientX - svg.getBoundingClientRect().left - M.left
  const i = Math.floor(x / chart.value.slot)
  hover.value = i >= 0 && i < byBall.value.length ? i : null
}
const hovered = computed(() => (hover.value === null ? null : byBall.value[hover.value] ?? null))

// Shade relative to this window's least and most drawn ball, so the scale always uses the full
// range. 18% green is the floor: lighter than that disappears into the page.
const range = computed(() => {
  const times = byBall.value.map((i) => i.times)
  return { min: Math.min(...times), max: Math.max(...times) }
})
const cells = computed(() => {
  const { min, max } = range.value
  return byBall.value.map((item) => {
    const t = max === min ? 1 : (item.times - min) / (max - min)
    return {
      ...item,
      shade: Math.round(18 + t * 82),
      out: item.times < band.value.low || item.times > band.value.high,
    }
  })
})
const LEGEND_STEPS = [18, 38, 59, 79, 100]

const most = computed(() => props.data.items.slice(0, 5))
const least = computed(() => props.data.items.slice(-5).reverse())

const showAll = ref(false)
const ranking = computed(() =>
  props.data.items.map((item, i) => ({ ...item, rank: i + 1, diff: item.times - props.data.expected })),
)
function signed(v: number): string {
  return (v > 0 ? '+' : v < 0 ? '−' : '') + formatDecimal(Math.abs(v), 1)
}
</script>

<template>
  <div class="freq">
    <p class="readout" aria-live="polite">
      <template v-if="hovered">
        Bola <strong>{{ formatBall(hovered.ball) }}</strong>: {{ formatInt(hovered.times) }}
        {{ hovered.times === 1 ? 'vez' : 'vezes' }} · esperado {{ formatDecimal(data.expected) }}
      </template>
      <template v-else>
        Esperado num sorteio honesto: <strong>{{ formatDecimal(data.expected) }}</strong> vezes por bola
        (faixa do acaso: {{ formatInt(band.low) }} a {{ formatInt(band.high) }})
      </template>
    </p>

    <template v-if="view === 'map'">
      <div class="heat" role="img" :aria-label="`Mapa de frequência das ${cells.length} bolas`" @pointerleave="hover = null">
        <div
          v-for="(c, i) in cells"
          :key="c.ball"
          class="heat-cell"
          :class="{ 'heat-cell--out': c.out, 'heat-cell--on': hover === i }"
          :style="{ '--shade': `${c.shade}%` }"
          :title="`${formatBall(c.ball)}: ${formatInt(c.times)}×`"
          @pointerenter="hover = i"
          @pointerdown="hover = i"
        >
          {{ formatBall(c.ball) }}
        </div>
      </div>
      <p class="hint legend">
        menos ({{ formatInt(range.min) }}×)
        <span v-for="st in LEGEND_STEPS" :key="st" class="swatch" :style="{ '--shade': `${st}%` }"></span>
        mais ({{ formatInt(range.max) }}×) ·
        <span class="swatch swatch--out"></span> fora da faixa do acaso ({{ formatInt(band.low) }} a
        {{ formatInt(band.high) }}). {{ outside }} {{ outside === 1 ? 'bola fica' : 'bolas ficam' }} fora; o acaso,
        sozinho, deixaria em média {{ formatDecimal(outsideExpected, 1) }}.
      </p>
    </template>

    <div v-show="view === 'bars'" ref="box" class="box">
      <svg
        :width="width"
        :height="HEIGHT"
        role="img"
        :aria-label="`Frequência das ${byBall.length} bolas; esperado ${formatDecimal(data.expected)} vezes cada`"
        @pointermove="pick"
        @pointerdown="pick"
        @pointerleave="hover = null"
      >
        <rect
          class="band"
          :x="M.left"
          :width="chart.plotW"
          :y="chart.y(band.high + 0.5)"
          :height="chart.y(Math.max(0, band.low - 0.5)) - chart.y(band.high + 0.5)"
        />
        <g class="grid">
          <g v-for="t in chart.ticks" :key="t">
            <line :x1="M.left" :x2="width - M.right" :y1="chart.y(t)" :y2="chart.y(t)" />
            <text :x="M.left - 6" :y="chart.y(t)" dy="0.32em" text-anchor="end">{{ formatInt(t) }}</text>
          </g>
        </g>
        <g>
          <rect
            v-for="(b, i) in chart.bars"
            :key="b.ball"
            class="bar"
            :class="{ 'bar--on': hover === i }"
            :x="b.x"
            :y="b.y"
            :width="b.w"
            :height="b.h"
            rx="1.5"
          />
        </g>
        <line class="expected" :x1="M.left" :x2="width - M.right" :y1="chart.y(data.expected)" :y2="chart.y(data.expected)" />
        <g class="xlabels">
          <template v-for="b in chart.bars" :key="b.ball">
            <text v-if="b.label" :x="b.x + b.w / 2" :y="HEIGHT - 6" text-anchor="middle">{{ b.ball }}</text>
          </template>
        </g>
      </svg>
    </div>

    <p v-if="view === 'bars'" class="hint legend">
      <span class="key key--line"></span> esperado
      <span class="key key--band"></span> faixa onde cada bola cai com ~95% de chance num sorteio honesto.
      {{ outside }} {{ outside === 1 ? 'bola fica' : 'bolas ficam' }} fora; o acaso, sozinho, deixaria em média
      {{ formatDecimal(outsideExpected, 1) }}.
    </p>

    <div class="extremes">
      <div>
        <h3>Mais sorteadas</h3>
        <ol>
          <li v-for="i in most" :key="i.ball"><strong>{{ formatBall(i.ball) }}</strong> {{ formatInt(i.times) }}×</li>
        </ol>
      </div>
      <div>
        <h3>Menos sorteadas</h3>
        <ol>
          <li v-for="i in least" :key="i.ball"><strong>{{ formatBall(i.ball) }}</strong> {{ formatInt(i.times) }}×</li>
        </ol>
      </div>
    </div>
    <p class="hint">
      <button type="button" class="link" @click="showAll = !showAll">
        {{ showAll ? 'Esconder a tabela' : `Ver as ${ranking.length} bolas` }}
      </button>
    </p>
    <div v-if="showAll" class="scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th scope="col" class="num">#</th>
            <th scope="col">Bola</th>
            <th scope="col" class="num">Vezes</th>
            <th scope="col" class="num">vs. esperado</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in ranking" :key="r.ball">
            <td class="num muted">{{ r.rank }}</td>
            <th scope="row">{{ formatBall(r.ball) }}</th>
            <td class="num">{{ formatInt(r.times) }}</td>
            <td class="num" :class="{ gold: r.times < band.low || r.times > band.high }">{{ signed(r.diff) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.freq {
  display: grid;
  gap: 0.75rem;
}
.box {
  width: 100%;
  overflow: hidden;
}
svg {
  display: block;
  touch-action: pan-y;
}
.readout {
  min-height: 1.5em;
  font-size: 0.9rem;
}
.band {
  fill: color-mix(in srgb, var(--gold) 12%, transparent);
}
.grid line {
  stroke: var(--border);
  stroke-width: 1;
}
.grid text,
.xlabels text {
  fill: var(--text-muted);
  font-size: 11px;
}
.bar {
  fill: var(--green);
}
.bar--on {
  fill: var(--gold);
}
.expected {
  stroke: var(--gold);
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
}
.legend {
  line-height: 1.7;
}
.key {
  display: inline-block;
  width: 1.2em;
  vertical-align: middle;
  margin-left: 0.3em;
}
.key--line {
  border-top: 2px dashed var(--gold);
}
.key--band {
  height: 0.8em;
  background: color-mix(in srgb, var(--gold) 25%, transparent);
}
.extremes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 1rem;
}
h3 {
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 0.35rem;
}
.heat {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.35rem;
  width: 100%;
  max-width: 34rem;
  margin-inline: auto;
}
.heat-cell {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  min-width: 0;
  font-weight: 700;
  font-size: 0.9rem;
  color: #fff;
  background: color-mix(in srgb, var(--green) var(--shade), var(--surface-2));
  border: 2px solid transparent;
  border-radius: 6px;
  cursor: default;
  user-select: none;
}
.heat-cell--out {
  border-color: var(--gold);
}
.heat-cell--on {
  outline: 2px solid var(--text);
  outline-offset: 1px;
}
.swatch {
  display: inline-block;
  width: 0.9em;
  height: 0.9em;
  vertical-align: middle;
  margin: 0 0.1em;
  border-radius: 3px;
  background: color-mix(in srgb, var(--green) var(--shade), var(--surface-2));
}
.swatch--out {
  background: transparent;
  border: 2px solid var(--gold);
}
.scroll {
  overflow-x: auto;
}
.link {
  padding: 0;
  font: inherit;
  color: var(--gold);
  background: none;
  border: 0;
  text-decoration: underline;
  cursor: pointer;
}
.gold {
  color: var(--gold);
}
@media (max-width: 380px) {
  .heat-cell {
    font-size: 0.75rem;
  }
}
ol {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
