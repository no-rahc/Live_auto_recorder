import { expect, test, type Page } from '@playwright/test';
import { broadcast, mockConsoleApi } from './fixtures';

async function labelPreview(page:Page,baseline=false) {
  await page.evaluate(isBaseline=>{
    const label=document.createElement('div');
    label.setAttribute('data-preview-label','synthetic');
    label.textContent=(isBaseline?'BASELINE V1 · ':'')+'SYNTHETIC SAMPLE · 합성 예시 데이터';
    Object.assign(label.style,{position:'fixed',bottom:'8px',right:'8px',zIndex:'2147483647',maxWidth:'calc(100vw - 16px)',padding:'6px 10px',background:'#172b4d',color:'#fff',borderRadius:'6px',font:'600 11px/1.4 sans-serif',pointerEvents:'none'});
    document.body.appendChild(label);
  },baseline);
}
async function measureLayout(page:Page) {
  return page.evaluate(()=>({
    viewport:window.innerWidth,
    documentWidth:document.documentElement.scrollWidth,
    overflowing:Array.from(document.querySelectorAll('body *')).filter(element=>{
      const style=getComputedStyle(element);const rect=element.getBoundingClientRect();
      return style.display!=='none'&&style.visibility!=='hidden'&&rect.width>0&&rect.right>window.innerWidth+1;
    }).map(element=>({tag:element.tagName,id:element.id,className:element.className.toString(),right:element.getBoundingClientRect().right,width:element.getBoundingClientRect().width})).slice(0,30),
  }));
}

for(const viewport of [{name:'desktop',width:1440,height:1050},{name:'mobile',width:360,height:800}]) {
  for(const screen of [{name:'dashboard',path:'/',heading:'녹화 관제 보드'}, {name:'library',path:'/broadcasts',heading:'방송 보관함'}, {name:'jobs',path:'/jobs',heading:'작업 상태'}, {name:'broadcast-detail',path:'/broadcasts/broadcast-1',heading:broadcast.title}]) {
    test(`@preview ${screen.name} ${viewport.name}: actual v1 shell with synthetic sample data`,async({page},testInfo)=>{
      await page.setViewportSize(viewport);
      await mockConsoleApi(page);
      const errors:string[]=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(screen.path);
      await expect(page.getByRole('heading',{name:screen.heading,exact:true,level:1})).toBeVisible();
      await expect(page.locator('body')).toHaveClass(/lar-sidebar-v3/);
      await expect(page.locator('#root .loading')).toHaveCount(0);
      if(screen.name==='dashboard') {
        await expect(page.locator('#ch-list')).toContainText('초록 스튜디오');
        await expect(page.locator('#cpu-percent')).toHaveText('18');
        await expect(page.locator('#mem-percent')).toHaveText('39');
      } else await expect(page.locator('#root.library-workspace .updated').first()).toContainText('2026');
      await page.evaluate(async()=>{await document.fonts.ready;});
      await labelPreview(page);
      const filename=`synthetic-${screen.name}-${viewport.name}.png`;
      const path=testInfo.outputPath(filename);
      await page.screenshot({path,fullPage:true,animations:'disabled'});
      await testInfo.attach(filename,{path,contentType:'image/png'});
      const layout=await measureLayout(page);
      await testInfo.attach('layout-diagnostics',{body:JSON.stringify(layout,null,2),contentType:'application/json'});
      await testInfo.attach('preview-context',{body:'Rendered production Jinja templates, original v1 app/console assets, and built embedded library bundle. All displayed API data are synthetic fixtures, not a connected installation or deployment. The SYNTHETIC SAMPLE corner label is added only by the screenshot test.',contentType:'text/plain'});
      if(screen.name==='dashboard'&&viewport.name==='mobile') {
        await page.goto('/?baseline=1');
        await expect(page.locator('#ch-list')).toContainText('초록 스튜디오');
        await expect(page.locator('#cpu-percent')).toHaveText('18');
        await expect(page.locator('#mem-percent')).toHaveText('39');
        await page.evaluate(async()=>{await document.fonts.ready;});
        await labelPreview(page,true);
        const baseline=await measureLayout(page);
        const baselinePath=testInfo.outputPath('synthetic-baseline-v1-dashboard-mobile.png');
        await page.screenshot({path:baselinePath,fullPage:true,animations:'disabled'});
        await testInfo.attach('synthetic-baseline-v1-dashboard-mobile.png',{path:baselinePath,contentType:'image/png'});
        await testInfo.attach('baseline-layout-comparison',{body:JSON.stringify({baseRef:process.env.UI_BASELINE_REF||'HEAD',baseline,current:layout},null,2),contentType:'application/json'});
      }
      expect(layout.documentWidth,`${screen.path}: ${JSON.stringify(layout)}`).toBeLessThanOrEqual(layout.viewport);
      expect(errors).toEqual([]);
    });
  }
}
