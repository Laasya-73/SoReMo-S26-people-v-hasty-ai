<script>
  import MetricBenchmarkCard from "../components/MetricBenchmarkCard.svelte";

  export let studioData = null;
  export let canRun = false;
  export let onDownloadMarkdown = () => {};
  export let onDownloadPdf = () => {};

  const fmtWeight = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0";
    return n.toFixed(2).replace(/\.?0+$/, "");
  };
</script>

<h2>Impact Scenario Studio</h2>
{#if studioData}
  <p><b>County:</b> {studioData.countyName}</p>
  <p><b>Base scenario:</b> {studioData.scenario}</p>

  <section class="summary">
    <p><b>Baseline pressure:</b> {studioData.baseline.score}</p>
    <p><b>Projected pressure:</b> {studioData.projected.score}</p>
    <p><b>Pressure delta:</b> {studioData.delta >= 0 ? "+" : ""}{studioData.delta}</p>
    <p><b>Heat context:</b> Index {studioData.heatStressIndex} | FEMA heat-wave risk {studioData.heatWaveRisk} | NOAA CDD {studioData.heatCdd} | NOAA summer Tmax {studioData.heatSummerTmax}</p>
    {#if studioData.baselineHeatFeedback !== null}
      <p><b>Heat feedback proxy:</b> {studioData.baselineHeatFeedback} -> {studioData.projectedHeatFeedback}
        (delta {studioData.heatFeedbackDelta >= 0 ? "+" : ""}{studioData.heatFeedbackDelta})</p>
    {/if}
    <p><b>Grid carbon intensity:</b> {studioData.gridCarbonIntensity}</p>
    <p><b>Estimated CO2 for 100 MW load:</b> {studioData.gridCO2LoadEstimate}</p>
    {#if studioData.baselineCarbonExposure !== null}
      <p><b>Carbon exposure proxy:</b> {studioData.baselineCarbonExposure} -> {studioData.projectedCarbonExposure}
        (delta {studioData.carbonExposureDelta >= 0 ? "+" : ""}{studioData.carbonExposureDelta})</p>
    {/if}
    <p><b>Standing shift:</b> {studioData.standingShift}</p>
  </section>

  {#if studioData.dataQuality}
    <section class="block quality">
      <h3>Data Quality + Confidence</h3>
      <p class="hint"><b>{studioData.dataQuality.confidence}</b> confidence: {studioData.dataQuality.available}/{studioData.dataQuality.total} indicators available ({studioData.dataQuality.coveragePct}% coverage).</p>
      <div class="quality-track">
        <span style={`width:${studioData.dataQuality.coveragePct}%`}></span>
      </div>
      {#if studioData.watchAlert}
        <p class="alert"><b>Watchlist alert:</b> {studioData.watchAlert.reasons.join("; ")}</p>
      {/if}
    </section>
  {/if}

  {#if studioData.peerComparison}
    <section class="block">
      <h3>Peer County Comparison</h3>
      <p class="hint">Pressure compared with demographically similar counties.</p>
      <p><b>County pressure:</b> {studioData.peerComparison.targetPressure} | <b>Peer average:</b> {studioData.peerComparison.peerAvgPressure}
      (delta {studioData.peerComparison.deltaVsPeers >= 0 ? "+" : ""}{studioData.peerComparison.deltaVsPeers})</p>
      <div class="peer-grid">
        {#each studioData.peerComparison.peers || [] as peer}
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
    <h3>Statewide Position Comparison</h3>
    <p class="hint">Both scores are benchmarked against all Illinois counties to show if the simulation moves this county up or down statewide.</p>
    <div class="bench-grid">
      {#each studioData.benchmarkCards || [] as item}
        <MetricBenchmarkCard {item} />
      {/each}
    </div>
  </section>

  <section class="block formula">
    <h3>Pressure Formula Breakdown</h3>
    <p class="equation">{studioData.pressureFormula?.equation}</p>
    <p class="hint">{studioData.pressureFormula?.explainer}</p>
    <div class="weight-note">
      <p><b>Why these multipliers?</b></p>
      <ul>
        {#each studioData.pressureFormula?.baseline?.rationale || [] as row}
          <li><b>{row.weight}</b> for {row.label.toLowerCase()}: {row.text}</li>
        {/each}
      </ul>
    </div>
    <div class="compare-grid">
      <div class="formula-table">
        <h4>Baseline Contributions</h4>
        <div class="stacked-bar">
          {#each studioData.pressureFormula?.baseline?.items || [] as row}
            <span style={`width:${row.sharePct}%;background:${row.color}`} title={`${row.label}: ${row.points} (${row.sharePct}%)`}></span>
          {/each}
        </div>
        {#each studioData.pressureFormula?.baseline?.items || [] as row}
          <div class="formula-row">
            <span>{row.label}</span>
            <span>{row.count} x {fmtWeight(row.weight)} = <b>{row.points}</b></span>
          </div>
        {/each}
        <p class="total">Total: <b>{studioData.pressureFormula?.baseline?.total}</b></p>
      </div>
      <div class="formula-table">
        <h4>Projected Contributions</h4>
        <div class="stacked-bar">
          {#each studioData.pressureFormula?.projected?.items || [] as row}
            <span style={`width:${row.sharePct}%;background:${row.color}`} title={`${row.label}: ${row.points} (${row.sharePct}%)`}></span>
          {/each}
        </div>
        {#each studioData.pressureFormula?.projected?.items || [] as row}
          <div class="formula-row">
            <span>{row.label}</span>
            <span>{row.count} x {fmtWeight(row.weight)} = <b>{row.points}</b></span>
          </div>
        {/each}
        <p class="total">Total: <b>{studioData.pressureFormula?.projected?.total}</b></p>
      </div>
    </div>
  </section>

  <div class="row">
    <button on:click={onDownloadMarkdown}>Download Note (.md)</button>
    <button on:click={onDownloadPdf}>Download Note (.pdf)</button>
  </div>
{:else if canRun}
  <p>Set controls and click Run Simulation.</p>
{:else}
  <p>No county options are available for this scenario and filter setup.</p>
{/if}

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

  .equation {
    margin: 4px 0 6px;
    color: #133b64;
    font-weight: 700;
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
  }

  .weight-note li {
    margin: 4px 0;
    color: #35597f;
    font-size: 12px;
  }

  .compare-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(240px, 1fr));
    gap: 10px;
    min-width: 0;
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

  .formula-table {
    border: 1px solid #d2e0f2;
    border-radius: 10px;
    background: #f9fcff;
    padding: 10px;
  }

  .stacked-bar {
    height: 12px;
    border-radius: 999px;
    overflow: hidden;
    border: 1px solid #cedcf0;
    background: #e8f0fb;
    display: flex;
    margin-bottom: 8px;
  }

  .stacked-bar span {
    min-width: 2px;
    height: 100%;
  }

  h4 {
    margin: 0 0 8px;
    color: #173f6b;
    font-size: 15px;
  }

  .formula-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 0;
    border-top: 1px solid #e1ebf8;
    color: #2a4e75;
    font-size: 13px;
  }

  .formula-row:first-of-type {
    border-top: 0;
  }

  .total {
    margin: 8px 0 0;
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
  }

  @media (max-width: 1024px) {
    .bench-grid {
      grid-template-columns: 1fr;
    }

    .compare-grid {
      grid-template-columns: 1fr;
    }

    .peer-grid {
      grid-template-columns: 1fr;
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

    .formula-row {
      font-size: 12px;
      gap: 6px;
    }

    h4 {
      font-size: 14px;
    }

    .row {
      gap: 8px;
    }
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

    .formula-row {
      font-size: 11.5px;
    }

    .row button {
      padding: 8px 10px;
    }
  }
</style>
