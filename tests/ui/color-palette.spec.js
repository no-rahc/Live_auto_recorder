const { test, expect } = require('@playwright/test');

function pickBox(box) {
  return box && {
    x: box.x,
    y: box.y,
    width: box.width,
    height: box.height,
  };
}

test.describe('blue neutral color theme', () => {
  test('changes palette without changing component geometry', async ({ page }) => {
    await page.goto('/tests/ui/fixtures/config.html');

    const selectors = ['#configForm', '.config-section', '#autoRecordingMode'];
    const before = {};
    for (const selector of selectors) {
      before[selector] = pickBox(await page.locator(selector).first().boundingBox());
    }

    await page.addStyleTag({ url: '/templates/static/css/tds-colors-v1.css' });

    const palette = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      return {
        primary: style.getPropertyValue('--lar-orange').trim().toLowerCase(),
        primaryHover: style.getPropertyValue('--lar-orange-hover').trim().toLowerCase(),
        background: style.getPropertyValue('--lar-bg').trim().toLowerCase(),
        surface: style.getPropertyValue('--lar-surface').trim().toLowerCase(),
        text: style.getPropertyValue('--lar-text').trim().toLowerCase(),
        muted: style.getPropertyValue('--lar-muted').trim().toLowerCase(),
        line: style.getPropertyValue('--lar-line').trim().toLowerCase(),
        success: style.getPropertyValue('--lar-success').trim().toLowerCase(),
        danger: style.getPropertyValue('--lar-danger').trim().toLowerCase(),
      };
    });

    expect(palette).toEqual({
      primary: '#3182f6',
      primaryHover: '#2272eb',
      background: '#f2f4f6',
      surface: '#ffffff',
      text: '#191f28',
      muted: '#8b95a1',
      line: '#e5e8eb',
      success: '#03b26c',
      danger: '#f04452',
    });

    for (const selector of selectors) {
      const after = pickBox(await page.locator(selector).first().boundingBox());
      expect(after).not.toBeNull();
      expect(before[selector]).not.toBeNull();
      expect(Math.abs(after.x - before[selector].x)).toBeLessThan(0.1);
      expect(Math.abs(after.y - before[selector].y)).toBeLessThan(0.1);
      expect(Math.abs(after.width - before[selector].width)).toBeLessThan(0.1);
      expect(Math.abs(after.height - before[selector].height)).toBeLessThan(0.1);
    }
  });
});
