<script>
  export let item = null;

  function bandClass(band) {
    const b = String(band || "").toLowerCase();
    if (b.includes("very high")) return "very-high";
    if (b.includes("high")) return "high";
    if (b.includes("moderate")) return "moderate";
    if (b.includes("low")) return "low";
    return "unknown";
  }

  $: pct = Number.isFinite(Number(item?.percentile)) ? Math.max(0, Math.min(100, Number(item.percentile))) : 0;
</script>

{#if item}
  <article class="metric-card">
    <header>
      <h4>{item.metricLabel}</h4>
      <span class={`band ${bandClass(item.band)}`}>{item.band}</span>
    </header>
    <p class="value">{item.valueLabel}</p>
    <p class="meta">{Number.isFinite(item.percentile) ? `${item.percentile}th percentile of ${item.count} counties` : "Context unavailable"}</p>
    <div class="track">
      <div class="fill" style={`width:${pct}%`}></div>
      <div class="marker" style={`left:${pct}%`}></div>
    </div>
    <div class="range">
      <small>Min {item.minLabel}</small>
      <small>Median {item.medianLabel}</small>
      <small>Max {item.maxLabel}</small>
    </div>
  </article>
{/if}

<style>
  .metric-card {
    border: 1px solid #c9daef;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.95);
    padding: 12px;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  h4 {
    margin: 0;
    color: #173d68;
    font-size: 16px;
  }

  .value {
    margin: 8px 0 0;
    color: #112e4f;
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.01em;
  }

  .meta {
    margin: 4px 0 10px;
    font-size: 12px;
    color: #45688f;
  }

  .track {
    position: relative;
    height: 10px;
    border-radius: 999px;
    background: #e3edf9;
    overflow: hidden;
  }

  .fill {
    height: 100%;
    background: linear-gradient(90deg, #19b48a 0%, #f2bd43 50%, #dc4a5f 100%);
  }

  .marker {
    position: absolute;
    top: -3px;
    width: 2px;
    height: 16px;
    background: #0d2946;
    transform: translateX(-1px);
  }

  .range {
    margin-top: 8px;
    display: flex;
    justify-content: space-between;
    gap: 6px;
    color: #486d95;
  }

  .range small {
    font-size: 11px;
    white-space: nowrap;
  }

  .band {
    font-size: 11px;
    font-weight: 700;
    border-radius: 999px;
    padding: 3px 8px;
    border: 1px solid transparent;
  }

  .band.very-high {
    color: #8f1f32;
    background: #ffe8ed;
    border-color: #f4b0bf;
  }

  .band.high {
    color: #9a5202;
    background: #fff1dc;
    border-color: #f3cc95;
  }

  .band.moderate {
    color: #6d5c08;
    background: #fff8d5;
    border-color: #ecd885;
  }

  .band.low {
    color: #0e6358;
    background: #e6f8f2;
    border-color: #aee0d2;
  }

  .band.unknown {
    color: #4c6585;
    background: #eaf2fb;
    border-color: #c6d7eb;
  }
</style>
