const fs = require('fs');
const {openBrowser} = require('/home/nitin/remotion/renderer/node_modules/@remotion/renderer');
const {screenshot} = require('/home/nitin/remotion/renderer/node_modules/@remotion/renderer/dist/puppeteer-screenshot');
const root = '/home/nitin/manim';
const targetJob = process.argv[2];
(async()=>{
  const browserExecutable=fs.existsSync('/usr/bin/google-chrome')?'/usr/bin/google-chrome':'/home/nitin/.cache/ms-playwright/chromium-1148/chrome-linux/chrome';
  const browser = await openBrowser('chrome',{browserExecutable,chromeMode:'chrome-for-testing',logLevel:'error'});
  try {
    const page = await browser.newPage({context:null,logLevel:'error',indent:false,pageIndex:0,onBrowserLog:null,onLog:()=>{}});
    await page.setViewport({width:1280,height:1000,deviceScaleFactor:1});
    await page.goto({url:'http://10.8.0.2:18610',timeout:20000});
    const token=fs.readFileSync(root+'/api-data/api-token','utf8').trim();
    await page.evaluate(async(value)=>{
      document.querySelector('#token').value=value;
      await document.querySelector('#login').onclick();
    },token);
    await page.evaluate(async(jobId)=>{
      if(jobId){selected=jobId;await showJob();return;}
      const button=document.querySelector('.job-title');
      if(button)button.click();
      await new Promise(resolve=>setTimeout(resolve,1200));
    },targetJob);
    const state=await page.evaluate(()=>({studioVisible:!document.querySelector('#studio').classList.contains('hidden'),
      loginError:document.querySelector('#login-error').textContent,
      jobCount:document.querySelectorAll('.job').length,
      stage:document.querySelector('#current-stage').textContent,jobId:selected,
      health:document.querySelector('#health').textContent,
      downloads:[...document.querySelectorAll('#downloads a')].map(a=>a.textContent),
      tokenRows:[...document.querySelectorAll('#usage-rows tr')].map(row=>row.textContent),
      insecureContext:!window.isSecureContext,submissionKeyLength:submissionKey().length,
      mp4Support:document.createElement('video').canPlayType('video/mp4; codecs="avc1.640028"'),
      horizontalOverflow:document.documentElement.scrollWidth>window.innerWidth}));
    if(!state.studioVisible||state.loginError||state.jobCount<1||state.submissionKeyLength!==32||state.horizontalOverflow)
      throw new Error(JSON.stringify(state));
    if(state.stage==='Silent video is ready'){
      state.video=await page.evaluate(async()=>{
        const video=document.querySelector('#video');
        if(video.classList.contains('hidden')||!video.getAttribute('src'))throw new Error('Ready video is missing');
        if(video.error)throw new Error('Video load error: '+video.error.code+' '+video.error.message);
        if(video.readyState<1)await new Promise((resolve,reject)=>{
          const timer=setTimeout(()=>reject(new Error('Video metadata timeout')),10000);
          video.addEventListener('loadedmetadata',()=>{clearTimeout(timer);resolve()},{once:true});
          video.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('Video cannot load'))},{once:true});
        });
        video.muted=true;
        video.currentTime=4;
        await video.play();
        await new Promise(resolve=>setTimeout(resolve,400));
        video.pause();
        if(video.currentTime<=4||video.videoWidth!==1920)throw new Error('Video playback did not advance');
        return {duration:video.duration,width:video.videoWidth,height:video.videoHeight,
                playbackAdvanced:true,currentTime:video.currentTime};
      });
    }
    await screenshot({page,type:'png',path:root+'/artifacts/api-browser.png',omitBackground:false,width:1280,height:1000,scale:1});
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    state.mobileHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
    if(state.mobileHorizontalOverflow)throw new Error('Mobile page overflows horizontally');
    fs.writeFileSync(root+'/artifacts/api-browser-validation.json',JSON.stringify(state,null,2)+'\n');
    if(targetJob)fs.writeFileSync(root+'/artifacts/api-browser-validation-'+targetJob+'.json',JSON.stringify(state,null,2)+'\n');
    console.log(JSON.stringify(state));
  } finally {await browser.close({silent:true});}
})().catch(error=>{console.error(error.message);process.exitCode=1});
