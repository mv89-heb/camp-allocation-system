const CACHE='camp-field-v4';
const SHELL=['/static/field.html','/static/field-report.html','/static/manifest.json'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('camp-field-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const u=new URL(event.request.url);
  if(u.origin!==location.origin||event.request.method!=='GET')return;
  event.respondWith(fetch(event.request).then(r=>{
    const copy=r.clone();
    if(r.ok)caches.open(CACHE).then(c=>c.put(event.request,copy));
    return r;
  }).catch(()=>caches.match(event.request).then(r=>r||caches.match('/static/field-report.html'))));
});
