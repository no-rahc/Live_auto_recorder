const { test, expect } = require('@playwright/test');

const cssAssets = [
  '/templates/static/css/style.css',
  '/templates/static/css/app-v3.css',
  '/templates/static/css/dashboard-glance-v1.css',
  '/templates/static/css/dashboard-channel-modal-v1.css',
  '/templates/static/css/recording-density-v1.css',
  '/templates/static/css/operations-v2.css',
  '/templates/static/css/operations-platform-v3.css',
  '/templates/static/css/ui-polish-v1.css',
  '/templates/static/css/config-workspace-v1.css',
  '/templates/static/css/config-safety-v1.css',
  '/templates/static/css/config-overview-v2.css',
  '/templates/static/css/project-ui-audit-v1.css',
  '/templates/static/css/project-ui-audit-fixes-v1.css',
  '/templates/static/css/operations-controls-v1.css',
  '/templates/static/css/ui-refinement-v1.css',
  '/templates/static/css/ui-consolidated-v1.css',
  '/templates/static/css/tds-colors-v1.css',
];

test('system status cards use one UI typeface for labels and primary values', async ({ page }) => {
  await page.setContent(`
    <body class="page-index">
      <section class="dash-sys-grid">
        <div class="card dash-storage">
          <header class="card-head">
            <div class="eyebrow" id="storage-label">녹화 저장소</div>
            <span class="chip" id="storage-path">/app/chzzk</span>
          </header>
          <div class="stor-num">
            <span class="stor-used" id="storage-used">426.85 GB</span>
            <span class="stor-sep">/</span>
            <span class="stor-total">10.83 TB</span>
            <span class="stor-pct">3.9%</span>
          </div>
        </div>
        <div class="card dash-meters">
          <div class="dash-meter" id="tile-cpu">
            <div class="dash-meter-top">
              <span class="dash-meter-label" id="cpu-label">CPU</span>
              <span class="dash-meter-val" id="cpu-value">8<small>%</small></span>
            </div>
          </div>
          <div class="dash-meter" id="tile-mem">
            <div class="dash-meter-top">
              <span class="dash-meter-label" id="memory-label">메모리</span>
              <span class="dash-meter-val" id="memory-value">31<small>%</small></span>
            </div>
          </div>
          <div class="dash-meter" id="tile-net">
            <div class="dash-meter-top">
              <span class="dash-meter-label" id="network-label">네트워크</span>
              <span class="dash-meter-val dash-net-val mono" id="network-value">↑ 0.00 MB/s · ↓ 0.00 MB/s</span>
            </div>
          </div>
        </div>
      </section>
    </body>
  `);

  for (const url of cssAssets) await page.addStyleTag({ url });
  await page.evaluate(() => document.fonts.ready);

  const styles = await page.evaluate(() => {
    const read = (id) => {
      const css = getComputedStyle(document.getElementById(id));
      return {
        fontFamily: css.fontFamily,
        letterSpacing: css.letterSpacing,
        fontVariantNumeric: css.fontVariantNumeric,
      };
    };
    return {
      storageLabel: read('storage-label'),
      cpuLabel: read('cpu-label'),
      memoryLabel: read('memory-label'),
      networkLabel: read('network-label'),
      storageUsed: read('storage-used'),
      cpuValue: read('cpu-value'),
      memoryValue: read('memory-value'),
      networkValue: read('network-value'),
    };
  });

  expect(styles.storageLabel.fontFamily).toBe(styles.cpuLabel.fontFamily);
  expect(styles.memoryLabel.fontFamily).toBe(styles.cpuLabel.fontFamily);
  expect(styles.networkLabel.fontFamily).toBe(styles.cpuLabel.fontFamily);
  expect(styles.storageLabel.letterSpacing).toBe(styles.cpuLabel.letterSpacing);

  expect(styles.storageUsed.fontFamily).toBe(styles.cpuValue.fontFamily);
  expect(styles.memoryValue.fontFamily).toBe(styles.cpuValue.fontFamily);
  expect(styles.networkValue.fontFamily).toBe(styles.cpuValue.fontFamily);
  expect(styles.storageUsed.fontVariantNumeric).toContain('tabular-nums');
  expect(styles.networkValue.fontVariantNumeric).toContain('tabular-nums');
});
