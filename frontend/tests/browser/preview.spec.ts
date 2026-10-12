import { expect, test } from '@playwright/test';
import { broadcast, mockConsoleApi } from './fixtures';

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
      if(screen.name==='dashboard') await expect(page.locator('#ch-list')).toContainText('초록 스튜디오');
      else await expect(page.locator('#root.library-workspace .updated').first()).toContainText('2026');
      await page.evaluate(async()=>{await document.fonts.ready;});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),screen.path).toBe(true);
      expect(errors).toEqual([]);
      await page.evaluate(()=>{
        const label=document.createElement('div');
        label.setAttribute('data-preview-label','synthetic');
        label.textContent='SYNTHETIC SAMPLE · 합성 예시 데이터';
        Object.assign(label.style,{position:'fixed',bottom:'8px',right:'8px',zIndex:'2147483647',maxWidth:'calc(100vw - 16px)',padding:'6px 10px',background:'#172b4d',color:'#fff',borderRadius:'6px',font:'600 11px/1.4 sans-serif',pointerEvents:'none'});
        document.body.appendChild(label);
      });
      const filename=`synthetic-${screen.name}-${viewport.name}.png`;
      const path=testInfo.outputPath(filename);
      await page.screenshot({path,fullPage:true,animations:'disabled'});
      await testInfo.attach(filename,{path,contentType:'image/png'});
      await testInfo.attach('preview-context',{body:'Rendered production Jinja templates, original v1 app/console assets, and built embedded library bundle. All displayed API data are synthetic fixtures, not a connected installation or deployment. The SYNTHETIC SAMPLE corner label is added only by the screenshot test.',contentType:'text/plain'});
    });
  }
}
