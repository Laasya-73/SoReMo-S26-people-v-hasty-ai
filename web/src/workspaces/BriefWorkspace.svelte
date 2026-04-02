<script>
  import MetricBenchmarkCard from "../components/MetricBenchmarkCard.svelte";

  export let briefData = null;
  export let briefFocus = "Balanced overview";
  export let canGenerate = false;
  export let onDownloadPdf = () => {};

  const fmtWeight = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0";
    return n.toFixed(2).replace(/\.?0+$/, "");
  };

  const bandClass = (band) => {
    const b = String(band || "").toLowerCase();
    if (b.includes("very high") || b.includes("rising")) return "danger";
    if (b.includes("high")) return "warn";
    if (b.includes("moderate") || b.includes("stable")) return "mid";
    if (b.includes("low") || b.includes("falling")) return "safe";
    return "muted";
  };
</script>

<div class="brief-export-root" data-brief-export>
  <h2>County Intelligence Briefing</h2>
  {#if briefData}
    <p><b>County:</b> {briefData.countyName}</p>
    <p><b>Scenario:</b> {briefData.scenario}</p>

  <section class="summary">
    <p><b>Active pressure:</b> {briefData.active.score} from {briefData.active.total} records.</p>
    <p><b>Current vs planned pressure:</b> {briefData.current.score} vs {briefData.planned.score} (delta {briefData.delta >= 0 ? "+" : ""}{briefData.delta}).</p>
    <p><b>Poverty:</b> {briefData.poverty} | <b>Minority:</b> {briefData.minority} | <b>AQI P90:</b> {briefData.aqi}.</p>
    <p><b>Heat context:</b> Index {briefData.heatStressIndex} | FEMA heat-wave risk {briefData.heatWaveRisk} | NOAA CDD {briefData.heatCdd} | NOAA summer Tmax {briefData.heatSummerTmax}.</p>
    <p><b>Grid mix:</b> Clean {briefData.gridCleanShare} | Fossil {briefData.gridFossilShare} | Carbon intensity {briefData.gridCarbonIntensity}.</p>
    <p><b>Estimated CO2 for 100 MW load:</b> {briefData.gridCO2LoadEstimate} (regional proxy).</p>
    <p><b>Focus lens:</b> {briefFocus}.</p>
  </section>

  {#if briefData.dataQuality}
    <section class="block quality">
      <h3>Data Quality + Confidence</h3>
      <p class="hint">
        <b>{briefData.dataQuality.confidence}</b> confidence: {briefData.dataQuality.available}/{briefData.dataQuality.total} indicators available
        ({briefData.dataQuality.coveragePct}% coverage).
      </p>
      <div class="quality-track">
        <span style={`width:${briefData.dataQuality.coveragePct}%`}></span>
      </div>
      {#if briefData.dataQuality.missing > 0}
        <p class="mini">Missing/placeholder indicators: {briefData.dataQuality.missingLabels.slice(0, 5).join(", ")}{briefData.dataQuality.missing > 5 ? "..." : ""}</p>
      {/if}
      {#if briefData.watchAlert}
        <p class="alert"><b>Watchlist alert:</b> {briefData.watchAlert.reasons.join("; ")}</p>
      {/if}
    </section>
  {/if}

  {#if briefData.peerComparison}
    <section class="block">
      <h3>Peer County Comparison</h3>
      <p class="hint">Compared against demographically and burden-profile similar Illinois counties.</p>
      <p><b>County pressure:</b> {briefData.peerComparison.targetPressure} | <b>Peer average:</b> {briefData.peerComparison.peerAvgPressure}
      (delta {briefData.peerComparison.deltaVsPeers >= 0 ? "+" : ""}{briefData.peerComparison.deltaVsPeers})</p>
      <div class="peer-grid">
        {#each briefData.peerComparison.peers || [] as peer}
          <div class="peer-card">
            <b>{peer.name}</b>
            <small>Pressure: {peer.pressure}</small>
            <small>Similarity distance: {peer.distance.toFixed(2)}</small>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <section class="block">
    <h3>{briefData.focusLens?.title || "Focus Lens"}</h3>
    <p class="hint">{briefData.focusLens?.summary}</p>
    <div class="focus-panels">
      <div>
        <h4>Decision Prompts</h4>
        <ul class="action-list">
          {#each briefData.focusLens?.actions || [] as line, idx}
            <li>
              <span class="idx">{idx + 1}</span>
              <span>{line}</span>
            </li>
          {/each}
        </ul>
      </div>
    </div>

    <div class="signals-section">
      <h4>Key Signals</h4>
      <div class="signal-grid">
        {#each briefData.focusLens?.insights || [] as item}
          <article class="signal-card">
            <div class="signal-top">
              <b>{item.metric}</b>
              <span class={`chip ${bandClass(item.band)}`}>{item.band}</span>
            </div>
            <div class="signal-value">{item.value}</div>
            {#if Number.isFinite(item.percentile)}
              <small>{item.percentile}th percentile statewide</small>
            {:else}
              <small>Scenario trend signal</small>
            {/if}
          </article>
        {/each}
      </div>
    </div>
  </section>

  <section class="block">
    <h3>Statewide Benchmark View</h3>
    <p class="hint">Each metric is compared against all Illinois counties. The percentile bar shows where this county stands statewide.</p>
    <div class="bench-grid">
      {#each briefData.benchmarks || [] as item}
        <MetricBenchmarkCard {item} />
      {/each}
    </div>
  </section>

  <section class="block formula">
    <h3>How Pressure Score Is Calculated</h3>
    <p class="equation">{briefData.pressureFormula?.equation}</p>
    <p class="hint">{briefData.pressureFormula?.explainer}</p>
    <div class="weight-note">
      <p><b>Why these multipliers?</b></p>
      <ul>
        {#each briefData.pressureFormula?.rationale || [] as row}
          <li><b>{row.weight}</b> for {row.label.toLowerCase()}: {row.text}</li>
        {/each}
      </ul>
    </div>
    <div class="stacked-wrap">
      <div class="stacked-bar">
        {#each briefData.pressureFormula?.items || [] as row}
          <span style={`width:${row.sharePct}%;background:${row.color}`} title={`${row.label}: ${row.points} (${row.sharePct}%)`}></span>
        {/each}
      </div>
      <div class="stacked-legend">
        {#each briefData.pressureFormula?.items || [] as row}
          <small><i style={`background:${row.color}`}></i>{row.label}: {row.sharePct}%</small>
        {/each}
      </div>
    </div>
    <div class="formula-table">
      {#each briefData.pressureFormula?.items || [] as row}
        <div class="formula-row">
          <div class="left">
            <b>{row.label}</b>
            <small>{row.help}</small>
          </div>
          <div class="right">{row.count} x {fmtWeight(row.weight)} = <b>{row.points}</b></div>
        </div>
      {/each}
    </div>
    <p class="total">Active scenario total pressure score: <b>{briefData.pressureFormula?.total}</b></p>
  </section>

    <div class="row" data-pdf-exclude>
      <button on:click={onDownloadPdf}>Download Brief (.pdf)</button>
    </div>
  {:else if canGenerate}
    <p>Select settings and click Generate County Brief.</p>
  {:else}
    <p>No county options are currently available for this filter setup.</p>
  {/if}
</div>

<style>
  h2 {
    margin: 0 0 8px;
    font-size: clamp(32px, 4vw, 46px);
    letter-spacing: -0.02em;
    color: #13365c;
  }

  .summary {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px 14px;
  }

  .summary p {
    margin: 6px 0;
    color: #24476f;
  }

  .block {
    margin-top: 12px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid #cadef6;
    border-radius: 12px;
    padding: 12px;
  }

  .block h3 {
    margin: 0 0 6px;
    color: #173d68;
    font-size: 22px;
    letter-spacing: -0.01em;
  }

  .hint {
    margin: 0 0 10px;
    color: #476b91;
    font-size: 13px;
  }

  .quality-track {
    height: 10px;
    border-radius: 999px;
    background: #e3edf9;
    overflow: hidden;
    border: 1px solid #cedcf0;
  }

  .quality-track span {
    display: block;
    height: 100%;
    background: linear-gradient(90deg, #f2c25b 0%, #2aa67f 100%);
  }

  .mini {
    margin: 8px 0 0;
    color: #4b6d92;
    font-size: 12px;
  }

  .alert {
    margin: 8px 0 0;
    color: #8b4a00;
    background: #fff4dd;
    border: 1px solid #f2d8a4;
    border-radius: 8px;
    padding: 6px 8px;
    font-size: 12px;
  }

  .bench-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(220px, 1fr));
    gap: 10px;
    min-width: 0;
  }

  .focus-panels {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .signals-section {
    margin-top: 10px;
  }

  .signal-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(220px, 1fr));
    gap: 10px;
    min-width: 0;
  }

  .signal-card {
    border: 1px solid #d6e4f5;
    border-radius: 10px;
    padding: 10px;
    background: #f8fbff;
  }

  .signal-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .signal-top b {
    color: #1a426f;
    font-size: 13px;
  }

  .signal-value {
    margin-top: 4px;
    font-size: 24px;
    font-weight: 800;
    color: #112f51;
    letter-spacing: -0.01em;
  }

  .signal-card small {
    display: block;
    margin-top: 2px;
    color: #4a6d92;
    font-size: 11px;
  }

  h4 {
    margin: 0 0 6px;
    color: #1a426f;
    font-size: 14px;
  }

  ul {
    margin: 0;
    padding-left: 18px;
    background: #f7fbff;
    border: 1px solid #d6e4f5;
    border-radius: 10px;
    padding-top: 8px;
    padding-bottom: 8px;
  }

  li {
    margin: 6px 0;
    color: #30557d;
    font-size: 13px;
  }

  .action-list {
    list-style: none;
    padding: 8px;
  }

  .action-list li {
    display: grid;
    grid-template-columns: 22px 1fr;
    gap: 8px;
    margin: 8px 0;
    align-items: start;
  }

  .idx {
    width: 20px;
    height: 20px;
    border-radius: 999px;
    background: #e7f1ff;
    border: 1px solid #c4daf5;
    color: #1f568f;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    line-height: 1;
  }

  .chip {
    font-size: 11px;
    font-weight: 700;
    border-radius: 999px;
    padding: 2px 8px;
    border: 1px solid transparent;
  }

  .chip.danger {
    color: #8f1f32;
    background: #ffe8ed;
    border-color: #f4b0bf;
  }

  .chip.warn {
    color: #955104;
    background: #fff0d8;
    border-color: #f2cb93;
  }

  .chip.mid {
    color: #6e5d10;
    background: #fff7d2;
    border-color: #e6d47e;
  }

  .chip.safe {
    color: #0f675b;
    background: #e7f8f1;
    border-color: #acdfcf;
  }

  .chip.muted {
    color: #4c6585;
    background: #eaf2fb;
    border-color: #c6d7eb;
  }

  .equation {
    margin: 4px 0 6px;
    color: #133b64;
    font-weight: 700;
  }

  .peer-grid {
    margin-top: 8px;
    display: grid;
    grid-template-columns: repeat(3, minmax(170px, 1fr));
    gap: 8px;
    min-width: 0;
  }

  .peer-card {
    border: 1px solid #d6e4f5;
    border-radius: 10px;
    padding: 8px;
    background: #f8fbff;
    display: grid;
    gap: 3px;
  }

  .peer-card b {
    color: #173f6b;
    font-size: 13px;
  }

  .peer-card small {
    color: #3c6189;
    font-size: 11px;
  }

  .weight-note {
    margin-bottom: 10px;
    padding: 8px 10px;
    border: 1px dashed #bfd3ec;
    border-radius: 10px;
    background: #f7fbff;
  }

  .weight-note p {
    margin: 0 0 4px;
    color: #163d67;
  }

  .weight-note ul {
    margin: 0;
    padding-left: 18px;
    background: transparent;
    border: 0;
  }

  .weight-note li {
    margin: 4px 0;
    color: #35597f;
    font-size: 12px;
  }

  .formula-table {
    border: 1px solid #d2e0f2;
    border-radius: 10px;
    overflow: hidden;
    background: #f9fcff;
  }

  .stacked-wrap {
    margin-bottom: 10px;
  }

  .stacked-bar {
    height: 14px;
    border-radius: 999px;
    overflow: hidden;
    border: 1px solid #cedcf0;
    background: #e8f0fb;
    display: flex;
  }

  .stacked-bar span {
    height: 100%;
    min-width: 2px;
  }

  .stacked-legend {
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .stacked-legend small {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: #3f6289;
    font-size: 11px;
  }

  .stacked-legend i {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    display: inline-block;
  }

  .formula-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px;
    border-top: 1px solid #e1ebf8;
  }

  .formula-row:first-child {
    border-top: 0;
  }

  .left {
    display: grid;
    gap: 2px;
  }

  .left small {
    color: #4d7096;
    font-size: 11px;
  }

  .right {
    color: #173f6b;
    font-weight: 600;
    white-space: nowrap;
  }

  .total {
    margin: 10px 0 0;
    color: #173f6b;
  }

  .row {
    margin-top: 12px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .row button {
    padding: 9px 12px;
    border: 1px solid #1464c9;
    background: linear-gradient(135deg, #1976d2 0%, #144ea2 100%);
    color: #fff;
    border-radius: 10px;
    cursor: pointer;
    font-weight: 700;
  }

  @media (max-width: 1440px) {
    .peer-grid {
      grid-template-columns: repeat(2, minmax(160px, 1fr));
    }
  }

  @media (max-width: 1366px) {
    .formula-row {
      flex-direction: column;
      align-items: flex-start;
    }

    .right {
      white-space: normal;
    }
  }

  @media (max-width: 1024px) {
    .bench-grid {
      grid-template-columns: 1fr;
    }

    .focus-panels {
      grid-template-columns: 1fr;
    }

    .signal-grid {
      grid-template-columns: 1fr;
    }

    .peer-grid {
      grid-template-columns: 1fr;
    }

    .formula-row {
      flex-direction: column;
      align-items: flex-start;
    }
  }

  @media (max-width: 768px) {
    .summary,
    .block {
      padding: 10px;
      border-radius: 10px;
    }

    h2 {
      letter-spacing: -0.01em;
    }

    .signal-value {
      font-size: 21px;
    }

    .row button {
      width: 100%;
      text-align: center;
    }
  }

  @media (max-width: 430px) {
    h2 {
      font-size: 28px;
    }

    .block h3 {
      font-size: 20px;
    }

    .hint {
      font-size: 12.5px;
    }

    .signal-card {
      padding: 8px;
    }

    .signal-value {
      font-size: 19px;
    }

    .action-list li {
      grid-template-columns: 1fr;
      gap: 4px;
    }

    .formula-row {
      gap: 8px;
      padding: 8px;
    }

    .idx {
      width: 18px;
      height: 18px;
    }
  }

  .brief-export-root {
    width: 100%;
    min-width: 0;
  }

  @media (max-width: 390px) {
    h2 {
      font-size: 26px;
    }

    .summary,
    .block {
      padding: 8px;
    }

    .block h3 {
      font-size: 18px;
    }

    li {
      font-size: 12.5px;
    }

    .row button {
      padding: 8px 10px;
    }
  }
</style>
