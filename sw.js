// Offline cache so the installed app starts without the local web server.
var C='parquet-pivot-v3';
var ASSETS=['./app.html','./manifest.json','./icon-192.png','./icon-512.png','./lib/duckdb-api.js','./lib/duckdb-assets.js'];
self.addEventListener('install',function(e){e.waitUntil(caches.open(C).then(function(c){return c.addAll(ASSETS)}).then(function(){return self.skipWaiting()}))});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.filter(function(k){return k!==C}).map(function(k){return caches.delete(k)}))}).then(function(){return self.clients.claim()}))});
self.addEventListener('fetch',function(e){
  var r=e.request;if(r.method!=='GET'||new URL(r.url).origin!==location.origin||/\/api\//.test(r.url))return;
  var heavy=/\/lib\//.test(r.url);
  if(heavy){ // big engine files: cache first
    e.respondWith(caches.match(r).then(function(m){return m||fetch(r).then(function(x){var cp=x.clone();caches.open(C).then(function(c){c.put(r,cp)});return x})}));
  }else{ // app shell: network first so edits show up, cache as fallback (offline)
    e.respondWith(fetch(r).then(function(x){var cp=x.clone();caches.open(C).then(function(c){c.put(r,cp)});return x}).catch(function(){return caches.match(r,{ignoreSearch:true}).then(function(m){return m||caches.match('./app.html')})}));
  }
});
